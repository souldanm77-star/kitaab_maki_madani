#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inspecte les runs rejetés proches du seuil : lecture réelle ou coïncidence ?"""
import json
import sys
from pathlib import Path

PROJET = Path('/home/z/my-project/download/video-recitation')
sys.path.insert(0, str(PROJET / 'pipeline'))
from commun import normaliser, similarite, est_recitable  # noqa: E402
import importlib.util
spec = importlib.util.spec_from_file_location(
    "aligner", PROJET / 'pipeline' / '3_aligner.py')
al = importlib.util.module_from_spec(spec)
sys.argv = ['aligner']
spec.loader.exec_module(al)

pages = al.charger_json(PROJET / 'travail_darsi' / 'pages.json')
trans = al.charger_json(PROJET / 'travail_darsi' / 'dars1' / 'transcription.json')

mots = []
for p in pages['pages']:
    for m in p['mots']:
        m['page'] = p['numero']
        mots.append(m)
parle_idx = [i for i, m in enumerate(mots)
             if est_recitable(m['texte']) and normaliser(m['texte'])]
b_norms = [normaliser(mots[i]['texte']) for i in parle_idx]
w_mots = trans['mots']
w_norms = [normaliser(w['mot']) if est_recitable(w['mot']) else None
           for w in w_mots]

ancrages = al.chercher_ancrages(w_norms, b_norms)
paires = {}
bornes = [(-1, -1)] + [tuple(a) for a in ancrages] + [(len(w_norms), len(b_norms))]
for (i1, j1), (i2, j2) in zip(bornes, bornes[1:]):
    w_r = list(range(i1 + 1, i2))
    b_r = list(range(j1 + 1, j2))
    if not w_r or not b_r:
        continue
    n_r = len(w_r)
    if (i1, j1) == (-1, -1):
        b_r = b_r[-(n_r + 400):] if len(b_r) > n_r + 400 else b_r
    else:
        b_r = b_r[:n_r + 400] if len(b_r) > n_r + 400 else b_r
    sous_w = [w_norms[i] for i in w_r]
    sous_b = [b_norms[j] for j in b_r]
    ops = al.dp_locale(sous_w, sous_b)
    for op in ops:
        if op[0] == 'M':
            paires[w_r[op[1]]] = (b_r[op[2]], similarite(sous_w[op[1]], sous_b[op[2]]))
for i, j in ancrages:
    paires[i] = (j, 1.0)

runs = []
for wi, (bj, sc) in sorted(paires.items()):
    if runs:
        dern = runs[-1]['paires'][-1]
        if (wi - dern[0] - 1 <= al.TROU_WHISPER and bj - dern[1] - 1 <= al.TROU_LIVRE):
            runs[-1]['paires'].append((wi, bj, sc))
            continue
    runs.append({'paires': [(wi, bj, sc)]})

# reconstruit les stats et montre les rejetés proches (0.58-0.64) avec du texte
print("=== RUNS REJETÉS, moyenne 0.58-0.64 (candidats douteux) ===")
aff = 0
for r in runs:
    ps = sorted(r['paires'], key=lambda x: x[1])
    n = len(ps)
    if n < 3:
        continue
    mean = sum(sc for _w, _b, sc in ps) / n
    if not (0.58 <= mean < 0.64):
        continue
    d0 = w_mots[ps[0][0]]['debut']
    j0, j1 = ps[0][1], ps[-1][1]
    span = j1 - j0 + 1
    if span / n > 2.2:
        continue
    wtxt = ' '.join(w_mots[wi]['mot'] for wi, _b, _s in ps[:10])
    btxt = ' '.join(mots[parle_idx[bj]]['texte'] for _w, bj, _s in ps[:10])
    pg = mots[parle_idx[j0]]['page']
    print(f"\nt={d0:7.1f}s p{pg} n={n} moy={mean:.2f} span/n={span / n:.2f}")
    print(f"  WHISPER: {wtxt}")
    print(f"  LIVRE  : {btxt}")
    aff += 1
    if aff >= 12:
        break
