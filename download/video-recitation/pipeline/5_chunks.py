#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÉTAPE 5 — Rendu par MORCEAUX (contourne le gel des processus de fond)
=====================================================================
Le sandbox gèle les processus nohup entre les appels d'outils : un rendu
de 80 min ne peut pas tenir dans un seul appel. On découpe donc :

  1. --morcean x --nb N  : rend le morceau x/N de la vidéo (audio t0→t1),
     avec concat de pages rogné + ASS décalé/rogné sur [t0, t1] ;
  2. --concat final      : assemble les morceaux (copie de flux, instantané).

Usage :
  python3 pipeline/5_chunks.py --config config_darsi.json --dars dars1 \
          --morcean 0 --nb 9
  python3 pipeline/5_chunks.py --config config_darsi.json --dars dars1 --concat
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "video4", Path(__file__).parent / "4_video.py")
v4 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v4)

from commun import (charger_json, charger_config, chemin_projet,
                    duree_media, sauver_json)  # noqa: E402

DUREE_MORCEAU = 540.0        # 9 min d'audio par morceau


def construire_fenetres(timing, p1, p2, duree):
    """Fenêtres d'affichage des pages (logique identique à 4_video.main)."""
    mots = [m for m in timing['mots'] if p1 <= m['page'] <= p2]
    par_page = {}
    for m in mots:
        if (m.get('etat') in ('whisper', 'interpole')
                and m.get('debut') is not None):
            par_page.setdefault(m['page'], []).append(m['debut'])
    if not par_page:
        raise SystemExit("Aucun mot du livre détecté comme lu — étape 3 ?")
    nums = sorted(par_page)
    fen = []
    for idx, p in enumerate(nums):
        d0 = 0.0 if idx == 0 else max(0.0, min(par_page[p]) - 0.4)
        d1 = min(par_page[nums[idx + 1]]) if idx + 1 < len(nums) else duree
        if d1 <= d0:
            d1 = d0 + 1.0
        fen.append([p, d0, d1])
    for k in range(len(fen) - 1):          # contiguïté obligatoire
        fen[k][2] = fen[k + 1][1]
    return fen, mots


def rendre_morceau(cfg, travail, dars_nom, fenetres, mots, pages_info,
                   cheikh, audio, dpi, t0, t1, dossier, idx):
    """Rend UN morceau [t0, t1] -> dossier/morceau_XXX.mp4."""
    v = cfg['video']
    dossier.mkdir(parents=True, exist_ok=True)
    dest = dossier / f"morceau_{idx:03d}.mp4"
    if dest.exists() and dest.stat().st_size > 100000:
        print(f"morceau {idx} déjà rendu -> {dest}")
        return dest

    # fenêtres intersectantes, rognées, durées relatives
    w = [(p, max(d0, t0), min(d1, t1)) for p, d0, d1 in fenetres
         if d1 > t0 + 0.01 and d0 < t1 - 0.01]
    if not w:
        w = [(fenetres[0][0], t0, t1)]

    dossier_fonds = Path(travail) / 'fonds' / dars_nom
    lst = dossier / f"morceau_{idx:03d}_pages.txt"
    lignes = ['ffconcat version 1.0']
    entete, evs = None, []
    for p, d0, d1 in w:
        fp = dossier_fonds / f"fond_p{p:03d}.png"
        fp.parent.mkdir(parents=True, exist_ok=True)
        pj = pages_info[p]
        transfo = v4.composer_fond(cfg, cheikh, Path(travail) / pj['image'], fp)
        dur = max(0.5, d1 - d0)
        lignes.append(f"file '{fp}'")
        lignes.append(f"duration {dur:.3f}")
        mp = [m for m in mots if m['page'] == p]
        ent, ev = v4.generer_ass(cfg, mp, transfo, dpi, 'mot',
                                 decalage=-t0, tmin=d0, tmax=d1)
        entete = ent
        evs += ev
    lignes.append(f"file '{fp}'")                 # répétition finale requise
    lst.write_text('\n'.join(lignes) + '\n', encoding='utf-8')

    ass = dossier / f"morceau_{idx:03d}.ass"
    ass.write_text(entete + "\n".join(evs) + "\n", encoding='utf-8')
    print(f"morceau {idx}: t={t0:.0f}→{t1:.0f}s, {len(w)} pages, "
          f"{len(evs)} événements ASS")

    duree = t1 - t0
    cmd = ['ffmpeg', '-nostdin', '-y', '-hide_banner', '-loglevel', 'error',
           '-stats',
           '-f', 'concat', '-safe', '0', '-i', str(lst),
           '-ss', f'{t0:.3f}', '-t', f'{duree:.3f}', '-i', str(audio),
           '-map', '0:v', '-map', '1:a',
           '-vf', f"fps={v.get('fps', 25)},ass={ass},format=yuv420p",
           '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
           '-c:a', 'aac', '-b:a', '160k',
           '-t', f'{duree:.3f}',
           '-movflags', '+faststart', str(dest)]
    subprocess.run(cmd, check=True)
    return dest


def main():
    ap = argparse.ArgumentParser(description="Rendu par morceaux (étape 5)")
    ap.add_argument('--config', default='config.json')
    ap.add_argument('--dars', required=True)
    ap.add_argument('--morcean', type=int, default=None)
    ap.add_argument('--nb', type=int, default=None,
                    help="nb total de morceaux (calcule t0/t1)")
    ap.add_argument('--concat', action='store_true',
                    help="assemble les morceaux en vidéo finale")
    args = ap.parse_args()

    cfg = charger_config(args.config)
    travail = chemin_projet(cfg, cfg.get('travail', 'travail'))
    dars = cfg['darses'][args.dars]
    audio = chemin_projet(cfg, dars['audio'])
    duree = duree_media(audio)
    p1, p2 = dars['pages']

    pages = charger_json(Path(travail) / 'pages.json')
    timing = charger_json(Path(travail) / args.dars / 'timing.json')
    fenetres, mots = construire_fenetres(timing, p1, p2, duree)
    pages_info = {p['numero']: p for p in pages['pages']}
    cheikh = chemin_projet(cfg, cfg['entree']['cheikh'])
    dpi = pages['dpi']

    dossier = chemin_projet(cfg, cfg.get('sortie', 'sortie')) / 'chunks' \
        / args.dars

    if args.concat:
        morceaux = sorted(dossier.glob('morceau_*.mp4'))
        if not morceaux:
            raise SystemExit("aucun morceau rendu")
        lst = dossier / 'liste.txt'
        lst.write_text('\n'.join(
            [f"file '{m}'" for m in morceaux]) + '\n', encoding='utf-8')
        dossier_sortie = chemin_projet(cfg, cfg.get('sortie', 'sortie'))
        sortie = dossier_sortie / f"{args.dars}.mp4"
        subprocess.run(['ffmpeg', '-nostdin', '-y', '-hide_banner',
                        '-loglevel', 'error',
                        '-f', 'concat', '-safe', '0', '-i', str(lst),
                        '-c', 'copy', '-movflags', '+faststart',
                        str(sortie)], check=True)
        print(f"OK -> {sortie} ({len(morceaux)} morceaux)")
        return

    if args.morcean is None or args.nb is None:
        # sans argument : rend le PREMIER morceau non rendu
        nb = max(1, round(duree / DUREE_MORCEAU + 0.499))
        for k in range(nb):
            t0, t1 = k * DUREE_MORCEAU, min((k + 1) * DUREE_MORCEAU, duree)
            dest = dossier / f"morceau_{k:03d}.mp4"
            if not (dest.exists() and dest.stat().st_size > 100000):
                print(f"prochain morceau non rendu : {k}/{nb - 1}")
                rendre_morceau(cfg, travail, args.dars, fenetres, mots,
                               pages_info, cheikh, audio, dpi,
                               t0, t1, dossier, k)
                return
        print("tous les morceaux sont déjà rendus — lancez --concat")
        return

    k = args.morcean
    nb = args.nb
    pas = duree / nb
    t0, t1 = k * pas, min((k + 1) * pas, duree)
    rendre_morceau(cfg, travail, args.dars, fenetres, mots, pages_info,
                   cheikh, audio, dpi, t0, t1, dossier, k)


if __name__ == '__main__':
    main()
