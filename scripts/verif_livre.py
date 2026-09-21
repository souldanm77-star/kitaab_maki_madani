#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Affiche le texte du LIVRE autour des mots appariés de chaque run :
si les mots forment une phrase verbatim du livre, le run est réel."""
import json
from pathlib import Path

BASE = Path('/home/z/my-project/download/video-recitation')
T = json.load(open(BASE / 'travail_darsi/dars1/timing.json', encoding='utf-8'))
mots = T['mots']

# index global des mots récitable (même filtre que l'aligneur)
from sys import path
path.insert(0, str(BASE / 'pipeline'))
from commun import normaliser, est_recitable

parle = [i for i, m in enumerate(mots)
         if est_recitable(m['texte']) and normaliser(m['texte'])]

def contexte_livre(q0, q1, marge=5):
    idx0, idx1 = parle[q0], parle[q1]
    sel = mots[max(0, idx0 - marge):idx1 + 1 + marge]
    return ' '.join(m['texte'] for m in sel)

for r in T['runs']:
    q = [k for k, i in enumerate(parle)
         if mots[i].get('run') == r['run'] and mots[i]['etat'] == 'whisper']
    if not q:
        continue
    print(f"run {r['run']:>2} p{r['page_debut']:<2} | livre : "
          f"{contexte_livre(q[0], q[-1])}")
