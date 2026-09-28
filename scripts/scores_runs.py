#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Distribution des scores de similarité par run actif — pour calibrer
le filtre qualité (vrais passages vs coïncidences somali)."""
import json
from collections import defaultdict

T = json.load(open('/home/z/my-project/download/video-recitation/'
                   'travail_darsi/dars1/timing.json', encoding='utf-8'))

par_run = defaultdict(list)
for m in T['mots']:
    if m.get('run'):
        par_run[m['run']].append(m['confiance'])

runs = {r['run']: r for r in T['runs']}
print(f"{'run':>4} {'n':>3} {'moy':>5} {'min':>5} {'%≥.85':>6}  texte")
for k in sorted(par_run):
    sc = par_run[k]
    n = len(sc)
    moy = sum(sc) / n
    mn = min(sc)
    p85 = 100 * sum(1 for s in sc if s >= 0.85) / n
    txt = runs[k]['texte'][:52] if k in runs else '?'
    print(f"{k:>4} {n:>3} {moy:5.2f} {mn:5.2f} {p85:5.0f}%  {txt}")
