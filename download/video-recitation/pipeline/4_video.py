#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÉTAPE 4 — Montage de la vidéo
=============================
  GAUCHE : image du cheikh (fixe, recadrée plein cadre)
  DROITE : la page RÉELLE du livre (rendu PNG de l'étape 1)
  PAR-DESSUS : rectangle surligneur semi-transparent qui suit le mot
               (mode « mot ») ou la ligne (mode « ligne ») pendant la
               récitation.

Le surlignage est un fichier ASS (dessins vectoriels) incrusté par ffmpeg :
précis à la milliseconde, sans re-rendu des frames en Python.

Sortie : sortie/<dars>.mp4   (1920x1080, H.264 + AAC — prêt pour YouTube)
"""
import argparse
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

from commun import (charger_json, charger_config, chemin_projet,
                    fmt_ass, duree_media)


# ----------------------------------------------------------------- fond ---
def composer_fond(cfg, image_cheikh, image_page, chemin_sortie):
    """Assemble 1920x1080 : cheikh à gauche + page réelle à droite.
    Renvoie la transformation (pt PDF -> pixels écran)."""
    v = cfg['video']
    W, H = v['largeur'], v['hauteur']
    LW = v['panneau_cheikh']['largeur']

    fond = Image.new('RGB', (W, H), tuple(v.get('fond', [24, 24, 28])))

    # --- panneau cheikh : recadrage « cover » centré
    img = Image.open(image_cheikh).convert('RGB')
    s = max(LW / img.width, H / img.height)
    img = img.resize((round(img.width * s), round(img.height * s)),
                     Image.LANCZOS)
    x = (img.width - LW) // 2
    y = (img.height - H) // 2
    fond.paste(img.crop((x, y, x + LW, y + H)), (0, 0))

    # --- panneau page : papier clair + séparateur doré
    RW = W - LW
    papier = tuple(v.get('papier', [246, 242, 233]))
    fond.paste(Image.new('RGB', (RW, H), papier), (LW, 0))
    fond.paste(Image.new('RGB', (4, H), tuple(v.get('separation',
                                                      [203, 164, 74]))),
               (LW - 2, 0))

    # --- la page réelle : ajustée dans le panneau avec marges
    pg = Image.open(image_page).convert('RGB')
    marges = v.get('marge', {})
    mx = marges.get('cote', 36)
    my = marges.get('haut', 36)
    dispo_w, dispo_h = RW - 2 * mx, H - 2 * my
    s2 = min(dispo_w / pg.width, dispo_h / pg.height)
    pw, ph = round(pg.width * s2), round(pg.height * s2)
    pg2 = pg.resize((pw, ph), Image.LANCZOS)
    pg2 = ImageOps.expand(pg2, border=1, fill=(180, 172, 150))
    ox = LW + (RW - pg2.width) // 2
    oy = (H - pg2.height) // 2
    fond.paste(pg2, (ox, oy))

    fond.save(chemin_sortie)
    # +1 : on vise l'intérieur du cadre de 1 px
    return {'s': s2, 'ox': ox + 1, 'oy': oy + 1}


# ------------------------------------------------------------------ ASS ---
def generer_ass(cfg, mots, transfo, dpi, mode, chemin_ass=None):
    """Construit les événements du surligneur.
    Seuls les mots des passages LU dans le livre (états 'whisper' et
    'interpole' produits par l'étape 3) sont surlignés — jamais les
    explications somali ni l'arabe hors livre ('hors_lecture').
    Si chemin_ass est fourni : écrit un fichier complet.
    Renvoie (entete, evenements) — evenements = texte brut des Dialogue.
    """
    v = cfg['video']
    s_cfg = v.get('surlignage', {})
    opacite = s_cfg.get('opacite', 0.45)
    alpha = max(0, min(255, round(255 * (1 - opacite))))
    r, g, b = s_cfg.get('couleur', [255, 235, 59])
    primaire = f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"
    pad = s_cfg.get('pad', 5)

    ratio = dpi / 72.0

    def rect_ecran(x0, y0, x1, y1):
        X0 = round(transfo['ox'] + x0 * ratio * transfo['s']) - pad
        Y0 = round(transfo['oy'] + y0 * ratio * transfo['s']) - pad
        X1 = round(transfo['ox'] + x1 * ratio * transfo['s']) + pad
        Y1 = round(transfo['oy'] + y1 * ratio * transfo['s']) + pad
        if X1 - X0 < 16:
            X1 = X0 + 16
        if Y1 - Y0 < 22:
            Y1 = Y0 + 22
        return X0, Y0, X1, Y1

    # ---- cibles à surligner ------------------------------------------------
    actif = lambda m: (m.get('etat') in ('whisper', 'interpole')
                       and m.get('debut') is not None)
    cibles = []
    if mode == 'mot':
        cibles = [m for m in mots if actif(m)]
    else:  # mode « ligne » : la ligne entière reste surlignée tant qu'on la lit
        groupes = {}
        for m in mots:
            if m.get('etat') == 'hors_texte':
                continue
            groupes.setdefault((m['page'], m.get('ligne', 0)), []).append(m)
        for (page, ligne), ms in groupes.items():
            t = [m for m in ms if actif(m)]
            if not t:
                continue
            cibles.append({
                'page': page, 'ligne': ligne,
                'x0': min(m['x0'] for m in ms),
                'y0': min(m['y0'] for m in ms),
                'x1': max(m['x1'] for m in ms),
                'y1': max(m['y1'] for m in ms),
                'debut': min(m['debut'] for m in t),
                'fin': max(m['fin'] for m in t)})
        cibles.sort(key=lambda c: c['debut'])
        for a, b in zip(cibles, cibles[1:]):
            if b['debut'] - a['fin'] < 3.0:
                a['fin'] = b['debut']      # surlignage continu ligne à ligne

    entete = f"""[Script Info]
; Surligneur karaoke — généré par 4_video.py
ScriptType: v4.00+
PlayResX: {v['largeur']}
PlayResY: {v['hauteur']}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: hl,Amiri,20,{primaire},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    evenements = []
    for c in cibles:
        X0, Y0, X1, Y1 = rect_ecran(c['x0'], c['y0'], c['x1'], c['y1'])
        dessin = f"m {X0} {Y0} l {X1} {Y0} l {X1} {Y1} l {X0} {Y1}"
        texte = "{\\an7\\pos(0,0)\\fad(25,25)\\p1}" + dessin + "{\\p0}"
        evenements.append(
            f"Dialogue: 0,{fmt_ass(c['debut'])},{fmt_ass(c['fin'])},"
            f"hl,,0,0,0,,{texte}")

    if chemin_ass:
        Path(chemin_ass).write_text(entete + "\n".join(evenements) + "\n",
                                    encoding='utf-8')
    return entete, evenements


# --------------------------------------------------------------- ffmpeg ---
def rendre_video(fenetres, fonds, audio, chemin_ass, sortie, cfg, duree=None):
    """Rendu par DEMUXEUR CONCAT : chaque page est une image affichée
    pendant sa fenêtre (le surligneur ASS passe par-dessus).
    Bien plus rapide que N entrées -loop pour un long dars."""
    v = cfg['video']
    lst = Path(sortie).parent / (Path(sortie).stem + '_concat.txt')
    lignes = ['ffconcat version 1.0']
    for (p, d0, d1), f in zip(fenetres, fonds):
        dur = max(0.5, d1 - d0)
        lignes.append(f"file '{f}'")
        lignes.append(f"duration {dur:.3f}")
    lignes.append(f"file '{fonds[-1]}'")       # répétition finale requise
    lst.write_text('\n'.join(lignes) + '\n', encoding='utf-8')

    # -nostdin : EMPÊCHE ffmpeg de lire l'entrée standard (sinon il bloque
    # la session qui l'appelle — bug sournois et classique)
    cmd = ['ffmpeg', '-nostdin', '-y', '-hide_banner', '-loglevel', 'error',
           '-stats',
           '-f', 'concat', '-safe', '0', '-i', str(lst),
           '-i', str(audio),
           '-map', '0:v', '-map', '1:a',
           # fps D'ABORD (normalise les timestamps du concat, sinon ass ne
           # verrait qu'une frame par page), puis le surligneur ASS
           '-vf', f"fps={v.get('fps', 25)},ass={chemin_ass},"
                  f"format=yuv420p",
           '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
           '-c:a', 'aac', '-b:a', '160k',
           '-movflags', '+faststart']
    if duree:
        cmd += ['-t', f'{duree + 0.5:.3f}']   # garde anti-boucle infinie
    cmd.append(str(sortie))
    subprocess.run(cmd, check=True)


# ----------------------------------------------------------------- main ---
def main():
    ap = argparse.ArgumentParser(description="Montage vidéo (étape 4)")
    ap.add_argument('--config', default='config.json')
    ap.add_argument('--dars', required=True)
    ap.add_argument('--mode', choices=['mot', 'ligne'], default=None,
                    help="surlignage mot à mot (défaut) ou ligne par ligne")
    ap.add_argument('--travail', default=None)
    ap.add_argument('--sortie', default=None)
    ap.add_argument('--max', type=float, default=None,
                    help='test : rend seulement les N premières secondes')
    args = ap.parse_args()

    cfg = charger_config(args.config)
    travail = chemin_projet(cfg, args.travail or cfg.get('travail', 'travail'))
    dars = cfg['darses'][args.dars]
    mode = args.mode or dars.get('mode') or \
        cfg['video'].get('surlignage', {}).get('mode', 'mot')

    pages = charger_json(Path(travail) / 'pages.json')
    timing = charger_json(Path(travail) / args.dars / 'timing.json')
    audio = chemin_projet(cfg, dars['audio'])
    cheikh = chemin_projet(cfg, cfg['entree']['cheikh'])
    duree = duree_media(audio)
    if not duree:
        duree = timing.get('duree', 0.0)

    p1, p2 = dars['pages']
    mots = [m for m in timing['mots'] if p1 <= m['page'] <= p2]
    if not mots:
        raise SystemExit(f"Aucun mot calé pour « {args.dars} » — lancez les "
                         f"étapes 1→3 d'abord.")
    if args.max:
        duree = min(duree, args.max)
        mots = [m for m in mots
                if m.get('debut') is None or m['debut'] < duree]

    # ---- fenêtres d'affichage de chaque page -----------------------------
    # basées sur les mots effectivement LUS (runs actifs) : pendant les
    # explications somali / hors livre, la page courante reste affichée
    # sans surlignage.
    par_page = {}
    for m in mots:
        if (m.get('etat') in ('whisper', 'interpole')
                and m.get('debut') is not None):
            par_page.setdefault(m['page'], []).append(m['debut'])
    if not par_page:
        raise SystemExit("Aucun mot du livre n'a été détecté comme lu — "
                         "vérifiez l'étape 3.")
    nums = sorted(par_page)
    fenetres = []
    for idx, p in enumerate(nums):
        d0 = 0.0 if idx == 0 else max(0.0, min(par_page[p]) - 0.4)
        d1 = min(par_page[nums[idx + 1]]) if idx + 1 < len(nums) else duree
        if d1 <= d0:
            d1 = d0 + 1.0
        fenetres.append((p, d0, d1))
    # CONTIGUÏTÉ obligatoire pour le démuxeur concat : la fin d'une fenêtre
    # = le début de la suivante (sinon les chevauchements s'accumulent et
    # les pages s'affichent en retard par rapport au surligneur ASS).
    for k in range(len(fenetres) - 1):
        p, d0, _d1 = fenetres[k]
        fenetres[k] = (p, d0, fenetres[k + 1][1])

    # ---- fonds composés + transformations -------------------------------
    dossier_fonds = Path(travail) / 'fonds' / args.dars
    dossier_fonds.mkdir(parents=True, exist_ok=True)
    infos_pages = {p['numero']: p for p in pages['pages']}
    fonds, transfos = [], {}
    for p, d0, d1 in fenetres:
        pj = infos_pages[p]
        fond_path = dossier_fonds / f"fond_p{p:03d}.png"
        transfos[p] = composer_fond(cfg, cheikh,
                                    Path(travail) / pj['image'], fond_path)
        fonds.append(fond_path)
        print(f"  page {p}: affichée de {d0:.1f}s à {d1:.1f}s")

    # ---- surligneur ASS --------------------------------------------------
    chemin_ass = Path(travail) / args.dars / 'surlignage.ass'
    entete, evenements = None, []
    for p, _d0, _d1 in fenetres:
        mots_page = [m for m in mots if m['page'] == p]
        ent, ev = generer_ass(cfg, mots_page, transfos[p], pages['dpi'], mode)
        entete = ent
        evenements += ev
    chemin_ass.write_text(entete + "\n".join(evenements) + "\n",
                          encoding='utf-8')
    print(f"surligneur : {len(evenements)} événements ({mode}) -> {chemin_ass}")

    # ---- rendu ffmpeg ----------------------------------------------------
    dossier_sortie = chemin_projet(cfg, cfg.get('sortie', 'sortie'))
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    sortie = Path(args.sortie) if args.sortie else \
        dossier_sortie / f"{args.dars}.mp4"
    print(f"rendu ffmpeg -> {sortie}")
    rendre_video(fenetres, fonds, audio, chemin_ass, sortie, cfg, duree)
    print(f"OK -> {sortie}")


if __name__ == '__main__':
    main()
