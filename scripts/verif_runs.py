#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vérification des runs actifs avec texte + score moyen + contexte audio."""
import json
from collections import defaultdict
from pathlib import Path

BASE = Path('/home/z/my-project/download/video-recitation')
T = json.load(open(BASE / 'travail_darsi/dars1/timing.json', encoding='utf-8'))
TR = json.load(open(BASE / 'travail_darsi/dars1/transcription.json',
                    encoding='utf-8'))
mots_w = TR['mots']

def contexte(t0, t1, marge=6):
    seg = [m['mot'] for m in mots_w if t0 - marge <= m['debut'] <= t1 + marge]
    return ' '.join(seg)[:170]

for r in T['runs']:
    ps = [m for m in T['mots'] if m.get('run') == r['run']
          and m['etat'] == 'whisper']
    sc = [m['confiance'] for m in ps]
    moy = sum(sc) / len(sc) if sc else 0
    print(f"run {r['run']:>2}  {r['debut']:>7.1f}s → {r['fin']:>7.1f}s  "
          f"p{r['page_debut']:<2} ({r['n_mots']:>2} mots, moy={moy:.2f})")
    print(f"     livre  : {r['texte'][:90]}")
    print(f"     audio  : {contexte(r['debut'], r['fin'])}")
