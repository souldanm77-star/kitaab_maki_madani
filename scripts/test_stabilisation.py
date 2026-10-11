#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test à sec de stabiliser_sessions() : affiche les sessions gardées,
les fenêtres de pages et les stats sans rien rendre."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent /
                       'download/video-recitation/pipeline'))

PROJET = Path('/home/z/my-project/kitaab_maki_madani/download/video-recitation')

# import direct du module 4_video (nom avec chiffre en tête -> importlib)
import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location(
    'video4', PROJET / 'pipeline' / '4_video.py')
video4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(video4)
stabiliser_sessions = video4.stabiliser_sessions

# mode debug : python3 test_stabilisation.py debug dars2 223
if len(sys.argv) >= 4 and sys.argv[1] == 'debug':
    d, autour = sys.argv[2], float(sys.argv[3])
    timing = json.load(open(PROJET / f'travail_darsi/{d}/timing.json'))
    mots = [m for m in timing['mots'] if 1 <= m['page'] <= 23]
    gardes, sessions = stabiliser_sessions(mots, trace=True)
    gset = {id(m) for m in gardes}
    print(f"--- sessions de {d} autour de {autour}s:")
    for s in sessions:
        if s['debut'] <= autour + 60 and s['fin'] >= autour - 60:
            print(f"  session [{s['debut']:.1f}-{s['fin']:.1f}] "
                  f"page {s['page']} dom {len(s['mots'])} mots "
                  f"-> {'VIVANTE' if s['vivante'] else 'MORTE'} "
                  f"(visites: " + ', '.join(
                      f"p{v['page']}@{v['debut']:.0f}(n={v['n']})"
                      for v in s['visites']) + ")")
    sys.exit(0)

for d in ['dars1', 'dars2', 'dars3', 'dars4']:
    timing = json.load(open(PROJET / f'travail_darsi/{d}/timing.json'))
    mots = [m for m in timing['mots'] if 1 <= m['page'] <= 23]
    bruts = sum(1 for m in mots if m.get('etat') in ('whisper', 'interpole')
                and m.get('debut') is not None)
    gardes, sessions = stabiliser_sessions(mots)
    sessions = [s for s in sessions if s['vivante']]
    print(f"=== {d}: {bruts} mots lus bruts -> {len(gardes)} gardés "
          f"({100 * len(gardes) / max(1, bruts):.0f} %), "
          f"{len(sessions)} sessions")
    # fenêtres fusionnées par page consécutive
    tetes = []
    for s in sessions:
        d0 = max(0.0, s['debut'] - 0.4)
        if tetes and tetes[-1][0] == s['page']:
            continue
        tetes.append([s['page'], d0])
    if tetes:
        tetes[0][1] = 0.0
    fen = []
    for k, (p, d0) in enumerate(tetes):
        d1 = tetes[k + 1][1] if k + 1 < len(tetes) else 99999
        fen.append((p, d0, d1))
    mono = all(fen[k + 1][1] > fen[k][1] for k in range(len(fen) - 1))
    print(f"    fenêtres ({len(fen)}, monotones: {mono}):")
    print('    ' + ' | '.join(f"p{p}[{d0:.0f}-{d1:.0f}]"
                              for p, d0, d1 in fen))
    # contrôle: chaque mot gardé tombe dans la fenêtre de SA page
    hors = 0
    for m in gardes:
        ok = any(p == m['page'] and d0 <= m['debut'] < d1
                 for p, d0, d1 in fen)
        if not ok:
            hors += 1
    print(f"    mots hors fenêtre de leur page: {hors}")
