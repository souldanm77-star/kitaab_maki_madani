#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Distribution des mesures qualité des runs rejetés (pass 1)."""
import json, sys
sys.path.insert(0, '/home/z/my-project/download/video-recitation/pipeline')
from commun import normaliser, similarite, est_recitable, charger_json

TRAV = '/home/z/my-project/download/video-recitation/travail_darsi'
pages = charger_json(f'{TRAV}/pages.json')
trans = charger_json(f'{TRAV}/dars1/transcription.json')

mots = []
for p in pages['pages']:
    for m in p['mots']:
        m['page'] = p['numero']
        mots.append(m)
b_norms = [normaliser(m['texte']) for m in mots
           if est_recitable(m['texte']) and normaliser(m['texte'])]
w_mots = trans['mots']
w_norms = [normaliser(w['mot']) if (normaliser(w['mot']) and est_recitable(w['mot'])) else None
           for w in w_mots]

import importlib
al = importlib.import_module('3_aligner') if False else None
# réimplémente la qualité sans import (module nommé 3_aligner non importable)
def qualite(ps):
    n = len(ps)
    d0 = w_mots[ps[0][0]]['debut']; d1 = w_mots[ps[-1][0]]['fin']
    mean = sum(s for _,_,s in ps)/n
    p80 = sum(1 for _,_,s in ps if s>=0.80)/n
    j0, j1 = ps[0][1], ps[-1][1]
    span = j1-j0+1
    longs = sum(1 for _w,bj,_s in ps if len(b_norms[bj])>=3)/n
    ancre = any(len(b_norms[bj])>=4 and s>=0.80 for _w,bj,s in ps)
    return n, d0, d1, mean, p80, span, longs, ancre

# --- refaire pass 1 DP/ancrages minimal : réutiliser le code en exécutant le module par chemin
import subprocess, tempfile, os
# plus simple : relancer le pipeline d'alignement en mode debug — mais on va
# plutôt instrumenter : réutiliser chercher_ancrages + dp_locale importés par fichier
import importlib.util
spec = importlib.util.spec_from_file_location(
    "aligner3", "/home/z/my-project/download/video-recitation/pipeline/3_aligner.py")
al = importlib.util.module_from_spec(spec)
spec.loader.exec_module(al)

ancrages = al.chercher_ancrages(w_norms, b_norms)
paires = {}
bornes = [(-1,-1)] + [tuple(a) for a in ancrages] + [(len(w_norms), len(b_norms))]
for (i1,j1),(i2,j2) in zip(bornes, bornes[1:]):
    w_r = list(range(i1+1, i2)); b_r = list(range(j1+1, j2))
    if not w_r or not b_r: continue
    n_r = len(w_r)
    if (i1,j1) == (-1,-1):
        b_r = b_r[-(n_r+400):] if len(b_r) > n_r+400 else b_r
    else:
        b_r = b_r[:n_r+400] if len(b_r) > n_r+400 else b_r
    sous_w = [w_norms[i] for i in w_r]
    sous_b = [b_norms[j] for j in b_r]
    ops = al.dp_locale(sous_w, sous_b)
    for op in ops:
        if op[0]=='M':
            paires[w_r[op[1]]] = (b_r[op[2]], similarite(sous_w[op[1]], sous_b[op[2]]))
for i,j in ancrages:
    paires[i] = (j, 1.0)

runs = []
for wi,(bj,sc) in sorted(paires.items()):
    if runs:
        dern = runs[-1][-1]
        if wi-dern[0]-1 <= 4 and bj-dern[1]-1 <= 3:
            runs[-1].append((wi,bj,sc)); continue
    runs.append([(wi,bj,sc)])

print(f"{len(runs)} runs bruts (TROU_W=4, TROU_B=3)")
buckets = {}
for r in runs:
    n,d0,d1,mean,p80,span,longs,ancre = qualite(r)
    if mean >= 0.62 and ancre and p80 >= 0.25:
        cat = 'ACTIF actuel'
    elif mean >= 0.45 and p80 >= 0.15:
        cat = 'frontiere 0.45-0.62'
    elif mean >= 0.35:
        cat = 'faible 0.35-0.45'
    else:
        cat = 'bruit <0.35'
    buckets.setdefault(cat, []).append((n, round(mean,2), round(p80,2), round(d1-d0,1), round(d1,1), ancre))

for cat, lst in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
    print(f"\n### {cat} : {len(lst)} runs")
    if 'frontiere' in cat or 'faible' in cat:
        for n,mean,p80,dur,t1,ancre in sorted(lst, key=lambda x:-x[1])[:25]:
            print(f"   n={n:3d} mean={mean:.2f} p80={p80:.2f} dur={dur:5.1f}s fin={t1:7.1f}s ancre={ancre}")
