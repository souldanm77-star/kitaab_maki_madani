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
import csv
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

from commun import (charger_json, charger_config, chemin_projet,
                    fmt_ass, duree_media)


# --------------------------------------------- stabilité des sessions ---
# L'aligneur produit des appariements mots-audio PARFAITS isolément mais
# imparfaits collectivement : hésitations entre deux pages (le même audio
# existe à deux endroits du livre), versets et formules RÉCITÉS DE MÉMOIRE
# qui « matchent » une page lointaine, citations du titre du livre...
# Or l'utilisateur a valié la règle des 3 états : surligner UNIQUEMENT la
# vraie lecture posée du livre. D'où ce post-traitement RENDU :
#   1. les mots lus sont groupés en « visites » (même page, trous <= 20 s)
#      puis en « sessions » (chaînage de visites, trous <= 8 s) ;
#   2. chaque session désigne sa page DOMINANTE (la visite la plus riche) ;
#   3. une session est ÉCARTÉE si sa visite dominante est RAPIDE (>= 4 mots
#      à <= 0,55 s/mot : formule récitée de mémoire), MINUSCULE (< 3 mots :
#      bruit) ou NI substantielle (>= 8 mots ou >= 6 s) NI accompagnée
#      (autre session de la même page à ±180 s : lecture fragmentée réelle) ;
#   4. une session non forte survit si elle RELAIE une session voisine forte
#      de la même page (fragments d'une même lecture posée) ;
#   5. les mots des visites non dominantes d'une session sont écartés
#      (le rectangle serait affiché sur une autre page que la sienne) ;
#   6. les fenêtres de pages suivent l'ORDRE CHRONOLOGIQUE des sessions :
#      une relecture d'une page antérieure réaffiche cette page (bug v3 :
#      fenêtres triées par NUMÉRO de page -> durées négatives et pages en
#      retard pour tout dars non linéaire).
GAP_VISITE = 20.0   # s — trou dans une même page -> nouvelle visite
GAP_SESSION = 8.0   # s — visites quelconques chaînées en session
ZONE_TROU = 600.0   # s — sessions de même page rapprochées = même cluster
ZONE_SESSIONS = 3   # un cluster de lecture compte >= 3 sessions...
ZONE_MOTS = 8       # ...totalisant >= 8 mots...
ZONE_DENSITE = 3.0  # ...à >= 3 mots/min (lecture fragmentée réelle)
FAST_PACE = 0.55    # s/mot (débuts) : rythme de récitation de mémoire
SUB_N = 8           # substantielle : >= SUB_N mots...
SUB_N_SPAN = 6      # ...ou >= 6 mots sur >= 6 s (débuts)
SUB_SPAN = 6.0


def stabiliser_sessions(mots, trace=False):
    """Filtre les mots lus et renvoie (mots_gardés, sessions).
    sessions : [{'page', 'debut', 'fin', 'mots'}, ...] triées par temps,
    une entrée par session confirmée (page dominante uniquement)."""
    lus = sorted([m for m in mots
                  if m.get('etat') in ('whisper', 'interpole')
                  and m.get('debut') is not None],
                 key=lambda m: m['debut'])

    # ---- 1) visites : même page, petits trous seulement -----------------
    visites = []
    for m in lus:
        fin_m = max(m.get('fin') or m['debut'], m['debut'])
        if visites and visites[-1]['page'] == m['page'] \
                and m['debut'] - visites[-1]['fin'] <= GAP_VISITE:
            v = visites[-1]
            v['fin'] = max(v['fin'], fin_m)
            v['fin_parole'] = m['debut']      # début du dernier mot :
            v['mots'].append(m)               # les fins Whisper sont gonflées
        else:
            visites.append({'page': m['page'], 'debut': m['debut'],
                            'fin': fin_m, 'fin_parole': m['debut'],
                            'mots': [m]})

    # ---- 2) sessions : chaînage de visites (page quelconque) ------------
    sessions = []
    for v in visites:
        if sessions and v['debut'] - sessions[-1]['fin'] <= GAP_SESSION:
            sessions[-1]['fin'] = max(sessions[-1]['fin'], v['fin'])
            sessions[-1]['visites'].append(v)
        else:
            sessions.append({'debut': v['debut'], 'fin': v['fin'],
                             'visites': [v]})

    # ---- 3) page dominante de chaque session -----------------------------
    for s in sessions:
        s['dom'] = max(
            s['visites'],
            key=lambda v: (len(v['mots']),
                           sum(m.get('confiance', 0) for m in v['mots'])
                           / len(v['mots'])))
        s['page'] = s['dom']['page']

    # ---- 4) écarte récitations de mémoire, bruit et îlots isolés ---------
    # rapide        : >= 4 mots enchaînés à <= 0,55 s/mot -> formule récitée
    # minuscule     : < 3 mots -> bruit d'appariement
    # substantielle : >= 8 mots, ou >= 6 mots posés sur >= 6 s
    # zone          : cluster de >= 3 sessions de la même page (trous
    #                 <= 600 s) totalisant >= 8 mots à >= 3 mots/min -> le
    #                 cheikh lit cette page par fragments entrecoupés
    #                 d'explications ; TOUTES les sessions du cluster sont
    #                 légitimes (même les rapides : son débit réel compresse
    #                 les horodatages Whisper)
    # une session survit si elle est forte, ou si elle relaie (voisine
    # immédiate vivante, même page) une session forte de cette page.
    def profil(s):
        d = s['dom']
        n = len(d['mots'])
        span = max(0.001, d['fin_parole'] - d['debut'])
        return n, span, span / n

    # clusters de lectures par page + zones
    zone = [False] * len(sessions)
    par_page = {}
    for i, s in enumerate(sessions):
        par_page.setdefault(s['page'], []).append(i)
    for page, idxs in par_page.items():
        clusters, courant = [], [idxs[0]]
        for i in idxs[1:]:
            if sessions[i]['debut'] - sessions[courant[-1]]['fin'] <= ZONE_TROU:
                courant.append(i)
            else:
                clusters.append(courant)
                courant = [i]
        clusters.append(courant)
        for cl in clusters:
            if len(cl) < ZONE_SESSIONS:
                continue
            nb_mots = sum(len(sessions[i]['dom']['mots']) for i in cl)
            if nb_mots < ZONE_MOTS:
                continue
            duree = sessions[cl[-1]]['fin'] - sessions[cl[0]]['debut']
            if duree <= 0:
                continue
            if nb_mots / duree * 60.0 >= ZONE_DENSITE:
                for i in cl:
                    zone[i] = True

    def forte(i):
        s = sessions[i]
        n, span, pace = profil(s)
        if n < 3:
            return False                        # bruit
        if zone[i]:
            return True                         # fragment d'une zone de lecture
        if n >= 4 and pace <= FAST_PACE:
            return False                        # récité de mémoire, isolé
        return n >= SUB_N or (n >= SUB_N_SPAN and span >= SUB_SPAN)

    vivants = [True] * len(sessions)
    change = True
    while change:
        change = False
        idx = [i for i in range(len(sessions)) if vivants[i]]
        for k, i in enumerate(idx):
            if forte(i):
                continue
            voisins = []
            if k > 0:
                voisins.append(idx[k - 1])
            if k + 1 < len(idx):
                voisins.append(idx[k + 1])
            # relais d'une lecture posée de la MÊME page -> on garde
            if any(sessions[v]['page'] == sessions[i]['page'] and forte(v)
                   for v in voisins):
                if trace:
                    print(f"    [trace] session {sessions[i]['debut']:.1f}-"
                          f"{sessions[i]['fin']:.1f} "
                          f"p{sessions[i]['page']} gardée (relais)")
                continue
            vivants[i] = False
            change = True
            if trace:
                print(f"    [trace] session {sessions[i]['debut']:.1f}-"
                      f"{sessions[i]['fin']:.1f} "
                      f"p{sessions[i]['page']} écartée (faible/rapide)")

    # ---- 5) sortie -------------------------------------------------------
    mots_gardes, finales = [], []
    for i, s in enumerate(sessions):
        if vivants[i]:
            mots_gardes.extend(s['dom']['mots'])
        finales.append({'page': s['page'], 'debut': s['debut'],
                        'fin': s['fin'], 'mots': s['dom']['mots'],
                        'vivante': bool(vivants[i]),
                        'visites': [{'page': v['page'], 'debut': v['debut'],
                                     'fin': v['fin'], 'n': len(v['mots'])}
                                    for v in s['visites']]})
    mots_gardes.sort(key=lambda m: m['debut'])
    return mots_gardes, finales


def exporter_csv(dossier_sortie, dars, mots_gardes):
    """Ré-exporte le CSV de synchronisation depuis les mots RÉELLEMENT
    surlignés (l'aligner exporte avant stabilisation)."""
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    chemin = dossier_sortie / f"{dars}_synchronisation.csv"
    with open(chemin, 'w', encoding='utf-8', newline='') as f:
        wc = csv.writer(f, delimiter=';')
        wc.writerow(['mot', 'debut', 'fin', 'page', 'position', 'texte'])
        for m in mots_gardes:
            wc.writerow([m.get('norme', m['texte']), f"{m['debut']:.3f}",
                         f"{m['fin']:.3f}", m['page'], m['position'],
                         m['texte']])
    return chemin


# ----------------------------------------------------------------- fond ---
def composer_fond(cfg, image_cheikh, image_page, chemin_sortie, cache=False):
    """Assemble 1920x1080 : cheikh à gauche + page réelle à droite.
    Renvoie la transformation (pt PDF -> pixels écran).
    cache=True : si le fond existe déjà (composition déterministe), seuls
    les chiffres de la transformation sont recalculés (rendu segmenté)."""
    v = cfg['video']
    W, H = v['largeur'], v['hauteur']
    LW = v['panneau_cheikh']['largeur']
    RW = W - LW

    # --- transformation (déterministe, calculée avant toute composition)
    pg = Image.open(image_page).convert('RGB')
    marges = v.get('marge', {})
    mx = marges.get('cote', 36)
    my = marges.get('haut', 36)
    s2 = min((RW - 2 * mx) / pg.width, (H - 2 * my) / pg.height)
    pw, ph = round(pg.width * s2), round(pg.height * s2)
    ox = LW + (RW - (pw + 2)) // 2          # +2 : cadre de 1 px
    oy = (H - (ph + 2)) // 2
    transfo = {'s': s2, 'ox': ox + 1, 'oy': oy + 1}   # vise l'intérieur

    if cache and Path(chemin_sortie).exists():
        return transfo

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
    papier = tuple(v.get('papier', [246, 242, 233]))
    fond.paste(Image.new('RGB', (RW, H), papier), (LW, 0))
    fond.paste(Image.new('RGB', (4, H), tuple(v.get('separation',
                                                      [203, 164, 74]))),
               (LW - 2, 0))

    # --- la page réelle : ajustée dans le panneau avec marges
    pg2 = pg.resize((pw, ph), Image.LANCZOS)
    pg2 = ImageOps.expand(pg2, border=1, fill=(180, 172, 150))
    fond.paste(pg2, (ox, oy))

    fond.save(chemin_sortie)
    return transfo


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
def rendre_video(fenetres, fonds, audio, chemin_ass, sortie, cfg,
                 duree=None, debut=None, fin=None):
    """Rendu par DEMUXEUR CONCAT : chaque page est une image affichée
    pendant sa fenêtre (le surligneur ASS passe par-dessus).
    Bien plus rapide que N entrées -loop pour un long dars.
    Si debut/fin sont fournis (rendu segmenté) : fenetres/fonds sont déjà
    recadrés sur [debut, fin), l'ASS est déjà décalé à 0, et seul l'AUDIO
    est compensé par un seek d'entrée (-ss debut)."""
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
           '-f', 'concat', '-safe', '0', '-i', str(lst)]
    if debut is not None:
        # seek d'entrée AUDIO : l'option s'applique à l'entrée suivante
        cmd += ['-ss', f'{debut:.3f}']
    cmd += ['-i', str(audio),
            '-map', '0:v', '-map', '1:a',
            # fps D'ABORD (normalise les timestamps du concat, sinon ass ne
            # verrait qu'une frame par page), puis le surligneur ASS
            '-vf', f"fps={v.get('fps', 25)},ass={chemin_ass},"
                   f"format=yuv420p",
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
            '-c:a', 'aac', '-b:a', '160k',
            '-movflags', '+faststart']
    if debut is not None:
        cmd += ['-t', f'{max(0.5, fin - debut):.3f}']
    elif duree:
        cmd += ['-t', f'{duree + 0.5:.3f}']   # garde anti-boucle infinie
    cmd.append(str(sortie))
    subprocess.run(cmd, check=True)


def ass_segmentaire(cfg, fenetres, transfos, dpi, mode, mots, t0, t1,
                    chemin):
    """ASS décalé pour le segment [t0, t1) : événements recoupés puis
    décalés à 0 (le rendu du segment démarre à 0).
    Un segment sans aucun mot lu (grande explication somali) reçoit un
    ASS vide (en-tête seul) — le fond de page reste affiché sans
    surlignage, conformément à la règle des 3 états."""
    entete, _ = generer_ass(cfg, [], next(iter(transfos.values())),
                            dpi, mode)
    mots_seg = []
    for m in mots:
        if m.get('fin', m['debut']) > t0 and m['debut'] < t1:
            c = dict(m)
            c['debut'] = max(0.0, m['debut'] - t0)
            c['fin'] = max(0.05, m.get('fin', m['debut']) - t0)
            mots_seg.append(c)
    evenements = []
    for p, _d0, _d1 in fenetres:
        mp = [m for m in mots_seg if m['page'] == p]
        if not mp:
            continue
        ent, ev = generer_ass(cfg, mp, transfos[p], dpi, mode)
        evenements += ev
    Path(chemin).write_text(entete + '\n'.join(evenements) + '\n',
                            encoding='utf-8')
    return len(evenements)


def rendre_segments(fenetres, fonds, audio, chemin_ass, sortie, cfg,
                    duree, longueur, par_appel=1, mots=None, transfos=None,
                    dpi=None, mode='mot', pages_cfg=None):
    """Rendu SEGMENTÉ avec reprise : les processus de fond ne survivant pas
    entre les appels d'outils, le rendu se fait par tranches (au plus
    par_appel tranches nouvelles par invocation) ; les segments complets
    sont sautés, puis concaténés SANS ré-encodage quand tout est prêt.
    Chaque segment reçoit sa propre liste concat (fenêtres recadrées sur
    [t, fin)) et son ASS décalé à 0 — aucun seek sur le flux vidéo."""
    sortie = Path(sortie)
    dossier = sortie.parent
    prefix = sortie.stem
    segments, t, k = [], 0.0, 0
    manquants = 0
    while t < duree - 0.5:
        fin = min(t + longueur, duree)
        seg = dossier / f"{prefix}_seg{k:03d}.mp4"
        attendu = fin - t
        deja = duree_media(seg) if seg.exists() else 0.0
        if deja >= attendu - 1.5:
            print(f"  segment {k} [{t:.0f}-{fin:.0f}s] déjà complet "
                  f"({deja:.1f}s) — sauté")
        elif manquants >= par_appel:
            print(f"  segment {k} [{t:.0f}-{fin:.0f}s] EN ATTENTE "
                  f"(relancez l'appel suivant)")
        else:
            # fenêtres recadrées sur le segment (contiguïté conservée)
            seg_fen, seg_fonds = [], []
            for (p, d0, d1), fpath in zip(fenetres, fonds):
                a, b = max(d0, t), min(d1, fin)
                if b - a > 0.05:
                    seg_fen.append((p, a - t, b - t))
                    seg_fonds.append(fpath)
            ass_seg = dossier / f"{prefix}_seg{k:03d}.ass"
            n_ev = ass_segmentaire(cfg, seg_fen, transfos, dpi, mode,
                                   mots or [], t, fin, ass_seg)
            print(f"  segment {k} [{t:.0f}-{fin:.0f}s] "
                  f"({len(seg_fen)} fenêtres, {n_ev} événements) ...")
            rendre_video(seg_fen, seg_fonds, audio, ass_seg, seg, cfg,
                         debut=t, fin=fin)
            ass_seg.unlink()
            manquants += 1
        segments.append(seg)
        t = fin
        k += 1
    if manquants:
        restants = sum(1 for s in segments
                       if not s.exists() or duree_media(s) < 0.5)
        print(f"ENCORE {restants} segment(s) à rendre — "
              f"relancez avec les mêmes arguments")
        return
    lst = dossier / f"{prefix}_segments.txt"
    lst.write_text('\n'.join(f"file '{s}'" for s in segments) + '\n',
                   encoding='utf-8')
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-hide_banner',
                    '-loglevel', 'error', '-f', 'concat', '-safe', '0',
                    '-i', str(lst), '-c', 'copy',
                    '-movflags', '+faststart', str(sortie)], check=True)
    for s in segments:
        s.unlink()
    lst.unlink()
    print(f"  {k} segments concaténés sans ré-encodage")


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
    ap.add_argument('--segment', type=float, default=None,
                    help='rendu segmenté avec reprise : longueur cible d un '
                         'segment en s (le rendu complet se fait appel '
                         'après appel, puis concat sans ré-encodage)')
    ap.add_argument('--par-appel', type=int, default=1,
                    help='segments rendus par invocation (défaut 1)')
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

    # ---- stabilité des sessions + fenêtres CHRONOLOGIQUES ----------------
    # le surlignage ne conserve que les lectures posées du livre (règle des
    # 3 états) et la page affichée suit l'ordre RÉEL de la lecture.
    mots_gardes, sessions = stabiliser_sessions(mots)
    sessions = [s for s in sessions if s['vivante']]
    if not sessions:
        raise SystemExit("Aucune lecture du livre n'a été confirmée après "
                         "stabilisation — vérifiez l'étape 3.")
    n_ecartes = sum(1 for m in mots
                    if m.get('etat') in ('whisper', 'interpole')
                    and m.get('debut') is not None) - len(mots_gardes)
    print(f"stabilisation : {len(mots_gardes)} mots gardés "
          f"({n_ecartes} écartés : îlots, récitations de mémoire, "
          f"hésitations) en {len(sessions)} sessions de lecture")

    # fenêtres : une par rafale de sessions de même page ; la première
    # couvre depuis 0 s (avant la première lecture, la page du premier
    # passage lu reste affichée, sans surlignage) ; CONTIGUÏTÉ obligatoire
    # pour le démuxeur concat (sinon dérive pages/surligneur ASS).
    têtes = []
    for s in sessions:
        d0 = max(0.0, s['debut'] - 0.4)
        if têtes and têtes[-1][0] == s['page']:
            continue                      # même page : la fenêtre continue
        têtes.append([s['page'], d0])
    if têtes:
        têtes[0][1] = 0.0                 # la vidéo commence à 0 s !
    fenetres = []
    for k, (p, d0) in enumerate(têtes):
        d1 = têtes[k + 1][1] if k + 1 < len(têtes) else duree
        if d1 <= d0:
            d1 = d0 + 1.0
        fenetres.append((p, d0, d1))
    for p, d0, d1 in fenetres:
        print(f"  page {p}: affichée de {d0:.1f}s à {d1:.1f}s")

    # ---- fonds composés + transformations -------------------------------
    # (cache : le fond composé est déterministe, on ne refait que les
    #  nouveaux — chaque invocation de rendu segmenté gagne ~30 s)
    dossier_fonds = Path(travail) / 'fonds' / args.dars
    dossier_fonds.mkdir(parents=True, exist_ok=True)
    infos_pages = {p['numero']: p for p in pages['pages']}
    fonds, transfos = [], {}
    for p, d0, d1 in fenetres:
        pj = infos_pages[p]
        fond_path = dossier_fonds / f"fond_p{p:03d}.png"
        transfos[p] = composer_fond(cfg, cheikh,
                                    Path(travail) / pj['image'],
                                    fond_path, cache=True)
        fonds.append(fond_path)

    # ---- surligneur ASS --------------------------------------------------
    chemin_ass = Path(travail) / args.dars / 'surlignage.ass'
    entete, evenements = None, []
    for p, d0, d1 in fenetres:
        # mots GARDÉS de cette page dont l'instant tombe dans la fenêtre
        # (une même page peut avoir plusieurs fenêtres si le cheikh y
        # revient plus tard — le filtre temporel évite les doublons)
        mots_page = [m for m in mots_gardes
                     if m['page'] == p and d0 <= m['debut'] < d1]
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
    # ---- CSV de synchronisation (mots RÉELLEMENT surlignés) --------------
    if not args.max:
        csv_chemin = exporter_csv(dossier_sortie, args.dars, mots_gardes)
        print(f"CSV synchronisation ré-exporté -> {csv_chemin}")

    print(f"rendu ffmpeg -> {sortie}")
    if args.segment:
        rendre_segments(fenetres, fonds, audio, chemin_ass, sortie, cfg,
                        duree, args.segment, args.par_appel,
                        mots=mots_gardes, transfos=transfos,
                        dpi=pages['dpi'], mode=mode)
    else:
        rendre_video(fenetres, fonds, audio, chemin_ass, sortie, cfg, duree)
    print(f"OK -> {sortie}")


if __name__ == '__main__':
    main()
