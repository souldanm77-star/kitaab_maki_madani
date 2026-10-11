#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dry-run du fenêtrage v5 (sans rendu ffmpeg) :
rejoue la logique de 4_video.main() jusqu'aux fenêtres + ASS,
affiche les fenêtres, les mots gardés par page et les événements ASS.
"""
import sys, os, json
sys.path.insert(0, '/home/z/my-project/kitaab_maki_madani/download/video-recitation/pipeline')
from pathlib import Path
import importlib
import commun
importlib.reload(commun)
from commun import charger_json, charger_config, chemin_projet, duree_media
import importlib.util
spec = importlib.util.spec_from_file_location(
    'quatre', '/home/z/my-project/kitaab_maki_madani/download/video-recitation/pipeline/4_video.py')
quatre = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quatre)

PROJET = Path('/home/z/my-project/kitaab_maki_madani/download/video-recitation')
cfg = charger_config(str(PROJET / 'config_darsi.json'))
pages = charger_json(PROJET / 'travail_darsi' / 'pages.json')

for dars_nom in ['dars1', 'dars2', 'dars3', 'dars4']:
    timing = charger_json(PROJET / 'travail_darsi' / dars_nom / 'timing.json')
    dars = cfg['darses'][dars_nom]
    p1, p2 = dars['pages']
    mots = [m for m in timing['mots'] if p1 <= m['page'] <= p2]
    mots_gardes, sessions = quatre.stabiliser_sessions(mots)
    vivantes = [s for s in sessions if s['vivante']]
    from collections import Counter
    par_page_g = Counter(m['page'] for m in mots_gardes)
    par_page_t = Counter(m['page'] for m in mots
                         if m.get('etat') in ('whisper', 'interpole')
                         and m.get('debut') is not None)
    print(f'=== {dars_nom}: {len(mots_gardes)} mots gardés / {sum(par_page_t.values())} mots lus bruts ; {len(vivantes)} sessions vivantes')
    print(f'    par page brut: {dict(sorted(par_page_t.items()))}')
    print(f'    par page gardé: {dict(sorted(par_page_g.items()))}')
    # fenêtres v5
    têtes = []
    for s in vivantes:
        d0 = max(0.0, s['debut'] - 0.4)
        if têtes and têtes[-1][0] == s['page']:
            continue
        têtes.append([s['page'], d0])
    if têtes:
        têtes[0][1] = 0.0
    duree = timing.get('duree', 0)
    fenetres = []
    for k, (p, d0) in enumerate(têtes):
        d1 = têtes[k + 1][1] if k + 1 < len(têtes) else duree
        if d1 <= d0:
            d1 = d0 + 1.0
        fenetres.append((p, d0, d1))
    print(f'    fenêtres v5 ({len(fenetres)}):')
    for p, d0, d1 in fenetres:
        flag = ' ⚠COURTE' if (d1 - d0) < 10 else ''
        print(f'      page {p:>2} : {d0/60:6.1f} → {d1/60:6.1f} min ({d1-d0:7.1f}s){flag}')
    # événements ASS par page
    ev_par_page = Counter()
    for p, d0, d1 in fenetres:
        mots_page = [m for m in mots_gardes if m['page'] == p and d0 <= m['debut'] < d1]
        ev_par_page[p] += len(mots_page)
    print(f'    événements ASS par page: {dict(sorted(ev_par_page.items()))}')
    print()
