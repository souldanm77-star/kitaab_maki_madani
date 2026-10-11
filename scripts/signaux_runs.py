#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Signaux de discrimination : densité du span livre + taux de
correspondance du contexte Whisper autour de chaque run actif."""
import json
from pathlib import Path

BASE = Path('/home/z/my-project/download/video-recitation')
T = json.load(open(BASE / 'travail_darsi/dars1/timing.json', encoding='utf-8'))
TR = json.load(open(BASE / 'travail_darsi/dars1/transcription.json',
                    encoding='utf-8'))

# reconstruire toutes les paires (wi -> bj, sc) depuis timing? Non —
# les paires ne sont pas sauvées. On réutilise les mots 'whisper' des
# runs ACTIFS seulement pour le span, et pour le contexte on relit
# timing.json : les mots whisper appariés = mots du livre état 'whisper'
# avec leur confiance ; on peut reconstruire wi via les temps.

# carte temps -> index whisper
widx = {}
for k, w in enumerate(TR['mots']):
    widx[round(w['debut'], 2)] = k

# paires de tous les runs actifs : (wi, bj) — bj via position dans le livre
mots_livre = T['mots']
pos_livre = {}
for m in mots_livre:
    if m['etat'] == 'whisper':
        pos_livre[(m['page'], m['position'])] = m['confiance']

# liste ordonnée des (page, position) des mots du livre
seq = [(m['page'], m['position']) for m in mots_livre]
index_seq = {pp: i for i, pp in enumerate(seq)}

paires_all = []          # (wi, j_global, sc) des runs actifs
for m in mots_livre:
    if m['etat'] == 'whisper' and m.get('run'):
        # retrouver wi par le temps de début
        wi = None
        for k, w in enumerate(TR['mots']):
            if abs(w['debut'] - m['debut']) < 0.02:
                wi = k
                break
        if wi is not None:
            paires_all.append((wi, index_seq[(m['page'], m['position'])],
                               m['confiance']))
paires_all.sort()

wi_matche = {p[0]: p[2] for p in paires_all}

print(f"{'run':>4} {'n':>3} {'span':>4} {'sp/n':>5} {'ctx±12':>7}  texte")
runs = {r['run']: r for r in T['runs']}
for r in T['runs']:
    ps = [(wi, j, s) for wi, j, s in paires_all
          if runs[r['run']]['debut'] - 0.5 <= TR['mots'][wi]['debut']
          <= runs[r['run']]['fin'] + 0.5]
    # plus sûr : via le run id
    ps = [(wi, j, s) for wi, j, s in paires_all
          if any(m['etat'] == 'whisper' and m.get('run') == r['run']
                 and abs(TR['mots'][wi]['debut'] - m['debut']) < 0.02
                 for m in mots_livre)]
    if not ps:
        continue
    n = len(ps)
    span = ps[-1][1] - ps[0][1] + 1
    wi0 = ps[0][0]
    wi1 = ps[-1][0]
    ctx = range(max(0, wi0 - 12), min(len(TR['mots']), wi1 + 13))
    bon = sum(1 for k in ctx if wi_matche.get(k, 0) >= 0.7)
    tot = len(range(max(0, wi0 - 12), min(len(TR['mots']), wi1 + 13)))
    print(f"{r['run']:>4} {n:>3} {span:>4} {span / n:5.2f} "
          f"{bon / max(1, tot):6.2f}  {r['texte'][:44]}")
