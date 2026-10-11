#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÉTAPE 4b — Rendu par MORCEAUX (robuste aux sessions à budget de temps)
======================================================================
Le rendu direct d'un dars de 46-80 min dépasse le temps d'une session.
On découpe la timeline en morceaux encodés SÉPARÉMENT puis assemblés :

  1. mêmes fenêtres / fonds / cibles que l'étape 4 (fonctions réutilisées) ;
  2. chaque morceau [A, B) rend UNE image de fond (celle de la fenêtre
     active en A) + le surligneur ASS limité à [A, B) (temps relatifs) ;
     pas d'audio dans les morceaux ;
  3. toutes les bornes sont QUANTIFIÉES à la trame (multiple de 1/25 s)
     et le nb de trames est imposé par -frames:v → durée EXACTE de chaque
     morceau → concat sans dérive de synchronisation ;
  4. concat -c copy des morceaux (vidéo seule), puis mux de l'audio
     ORIGINAL en une seule pièce (aucune coupure audio, aucun gap AAC).

Reprise : un morceau déjà rendu (fichier + taille > 0) est sauté ;
relancer la commande continue. --budget borne le temps d'une session.
"""
import argparse
import importlib.util
import subprocess
import time
from pathlib import Path

from commun import charger_config, chemin_projet, charger_json, duree_media

FPS_DEF = 25


def charger_module_4video():
    """Importe 4_video.py (nom commençant par un chiffre → importlib)."""
    chemin = Path(__file__).parent / '4_video.py'
    spec = importlib.util.spec_from_file_location('video4', chemin)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def quantifier(t, fps):
    """Borne alignée sur la grille des trames (pas de dérive au concat)."""
    return round(t * fps) / fps


def rendre_morceau(fond, chemin_ass, n_frames, sortie_part, cfg):
    """Encode un morceau : 1 image × n_frames trames + ASS (pas d'audio)."""
    lst = sortie_part.with_suffix('.txt')
    lignes = ['ffconcat version 1.0',
              f"file '{fond}'", 'duration 99999',
              f"file '{fond}'"]
    lst.write_text('\n'.join(lignes) + '\n', encoding='utf-8')
    v = cfg['video']
    cmd = ['ffmpeg', '-nostdin', '-y', '-hide_banner', '-loglevel', 'error',
           '-f', 'concat', '-safe', '0', '-i', str(lst),
           '-vf', f"fps={v.get('fps', FPS_DEF)},ass={chemin_ass},"
                  f"format=yuv420p",
           '-frames:v', str(n_frames),
           '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
           '-an', str(sortie_part)]
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser(
        description="Rendu par morceaux + concat (étape 4b)")
    ap.add_argument('--config', default='config.json')
    ap.add_argument('--dars', required=True)
    ap.add_argument('--mode', choices=['mot', 'ligne'], default=None)
    ap.add_argument('--travail', default=None)
    ap.add_argument('--sortie', default=None)
    ap.add_argument('--taille', type=float, default=420.0,
                    help="durée cible d'un morceau (s)")
    ap.add_argument('--budget', type=float, default=480.0,
                    help="budget de traitement par invocation (s)")
    ap.add_argument('--sans-final', action='store_true',
                    help="rend les morceaux manquants sans faire le concat")
    args = ap.parse_args()

    v4 = charger_module_4video()
    cfg = charger_config(args.config)
    travail = chemin_projet(cfg, args.travail or cfg.get('travail', 'travail'))
    dars = cfg['darses'][args.dars]
    mode = args.mode or dars.get('mode') or \
        cfg['video'].get('surlignage', {}).get('mode', 'mot')

    pages = charger_json(Path(travail) / 'pages.json')
    timing = charger_json(Path(travail) / args.dars / 'timing.json')
    audio = chemin_projet(cfg, dars['audio'])
    cheikh = chemin_projet(cfg, cfg['entree']['cheikh'])
    duree = duree_media(audio) or timing.get('duree', 0.0)
    fps = cfg['video'].get('fps', FPS_DEF)

    p1, p2 = dars['pages']
    mots = [m for m in timing['mots'] if p1 <= m['page'] <= p2]
    if not mots:
        raise SystemExit("Aucun mot calé — lancez les étapes 1→3 d'abord.")

    # ---- fenêtres de pages (identiques à l'étape 4) ----------------------
    par_page = {}
    for m in mots:
        if (m.get('etat') in ('whisper', 'interpole')
                and m.get('debut') is not None):
            par_page.setdefault(m['page'], []).append(m['debut'])
    if not par_page:
        raise SystemExit("Aucun mot du livre détecté comme lu — étape 3 ?")
    nums = sorted(par_page)
    fenetres = []
    for idx, p in enumerate(nums):
        d0 = 0.0 if idx == 0 else max(0.0, min(par_page[p]) - 0.4)
        d1 = min(par_page[nums[idx + 1]]) if idx + 1 < len(nums) else duree
        if d1 <= d0:
            d1 = d0 + 1.0
        fenetres.append([p, d0, d1])
    for k in range(len(fenetres) - 1):
        fenetres[k][2] = fenetres[k + 1][1]

    # ---- fonds + transfos --------------------------------------------------
    infos_pages = {p['numero']: p for p in pages['pages']}
    dossier_fonds = Path(travail) / 'fonds' / args.dars
    dossier_fonds.mkdir(parents=True, exist_ok=True)
    fonds, transfos = {}, {}
    for p, d0, d1 in fenetres:
        pj = infos_pages[p]
        fond_path = dossier_fonds / f"fond_p{p:03d}.png"
        transfos[p] = v4.composer_fond(cfg, cheikh,
                                       Path(travail) / pj['image'], fond_path)
        fonds[p] = fond_path
        print(f"  page {p}: affichée de {d0:.1f}s à {d1:.1f}s")

    # ---- cibles ASS (clampées aux fenêtres, temps absolus) ----------------
    cibles_totales = []
    for p, d0, d1 in fenetres:
        mots_page = [m for m in mots if m['page'] == p]
        cibles_totales += v4.calculer_cibles(cfg, mots_page, transfos[p],
                                             pages['dpi'], mode, (d0, d1))
    print(f"surligneur : {len(cibles_totales)} cibles ({mode})")

    # ---- découpe en morceaux (bornes = trames exactes) ---------------------
    # chaque morceau est ENTIÈREMENT DANS une fenêtre de page (une seule
    # image de fond) : les bornes de fenêtres sont toujours des bornes.
    total_frames = int(round(quantifier(duree, fps) * fps))
    bornes = {0, total_frames}
    for p, d0, d1 in fenetres:
        bornes.add(int(round(quantifier(d0, fps) * fps)))
        bornes.add(int(round(quantifier(min(d1, duree), fps) * fps)))
    taille_frames = int(round(args.taille * fps))
    for p, d0, d1 in fenetres:
        a = int(round(quantifier(d0, fps) * fps))
        b = int(round(quantifier(min(d1, duree), fps) * fps))
        n_sous = max(1, int((b - a) // taille_frames))
        for k in range(1, n_sous + 1):
            f = a + int(round((b - a) * k / (n_sous + 1)))
            if 0 < f < total_frames:
                bornes.add(f)
    bornes = sorted(b for b in bornes if 0 <= b <= total_frames)

    dossier_parts = Path(travail) / args.dars / 'parts'
    dossier_parts.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    rendus = 0
    for k, (fa, fb) in enumerate(zip(bornes, bornes[1:])):
        if fb <= fa:
            continue
        part = dossier_parts / f"part_{fa:06d}.mp4"
        if part.exists() and part.stat().st_size > 0:
            continue
        A, B = fa / fps, fb / fps
        # image de fond : fenêtre active en A
        fen = next(f for f in fenetres if f[1] - 1e-6 <= A < f[2] - 1e-6)
        # cibles du morceau, temps relatifs au morceau
        loc = []
        for c in cibles_totales:
            d0 = max(c['debut'], A)
            d1 = min(c['fin'], B)
            if d1 - d0 > 0.02:
                loc.append(dict(c, debut=d0 - A, fin=d1 - A))
        ass_chunk = dossier_parts / f"part_{fa:06d}.ass"
        v4.ecrire_ass(loc, cfg, ass_chunk)
        rendre_morceau(fonds[fen[0]], ass_chunk, fb - fa, part, cfg)
        rendus += 1
        print(f"  morceau {fa / fps:8.2f}s → {fb / fps:8.2f}s "
              f"({(fb - fa) / fps:6.1f}s, page {fen[0]}) OK "
              f"[{time.time() - t0:.0f}s]")
        if time.time() - t0 > args.budget:
            print(f"⏸ budget atteint — relancez ({rendus} morceaux cette "
                  f"session)")
            return

    # ---- assemblage final --------------------------------------------------
    if args.sans_final:
        print("morceaux tous prêts (--sans-final : pas d'assemblage)")
        return
    dossier_sortie = chemin_projet(cfg, cfg.get('sortie', 'sortie'))
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    sortie = Path(args.sortie) if args.sortie else \
        dossier_sortie / f"{args.dars}.mp4"

    lst_parts = dossier_parts / 'assemblage.txt'
    lignes = ['ffconcat version 1.0']
    manquants = 0
    for fa, fb in zip(bornes, bornes[1:]):
        if fb <= fa:
            continue
        part = dossier_parts / f"part_{fa:06d}.mp4"
        if not (part.exists() and part.stat().st_size > 0):
            manquants += 1
            continue
        lignes.append(f"file '{part}'")
        lignes.append(f"duration {(fb - fa) / fps:.6f}")
    if manquants:
        raise SystemExit(f"{manquants} morceau(x) manquant(s) — relancez.")
    lst_parts.write_text('\n'.join(lignes) + '\n', encoding='utf-8')

    video_seule = dossier_parts / 'video_seule.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-hide_banner',
                    '-loglevel', 'error',
                    '-f', 'concat', '-safe', '0', '-i', str(lst_parts),
                    '-c', 'copy', str(video_seule)], check=True)

    print("mux audio original ->", sortie)
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-hide_banner',
                    '-loglevel', 'error',
                    '-i', str(video_seule), '-i', str(audio),
                    '-map', '0:v', '-map', '1:a',
                    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '160k',
                    '-movflags', '+faststart', str(sortie)], check=True)
    print(f"OK -> {sortie}")


if __name__ == '__main__':
    main()
