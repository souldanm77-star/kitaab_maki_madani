#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostic: compare la transcription Whisper du segment rejeté
(32.9s-231.8s) avec le texte du livre pages 1-2."""
import json, sys
sys.path.insert(0, '/home/z/my-project/download/video-recitation/pipeline')
from commun import normaliser, similarite

TRAV = '/home/z/my-project/download/video-recitation/travail_darsi/dars1'

# --- transcription complète du dars1
with open(f'{TRAV}/transcription.json') as f:
    trans = json.load(f)

mots = [m for m in trans['mots'] if 32.88 <= m['debut'] <= 231.84]
ar = [m['mot'] for m in mots if (m.get('langue') or '').startswith('ar')]
print(f"=== mots Whisper 32.9-231.8s : {len(mots)} total, {len(ar)} ar ===")
txt_w = ' '.join(ar)
print(txt_w[:1500])
print()

# --- texte du livre pages 1-3
with open(f'{TRAV}/timing.json') as f:
    timing = json.load(f)
livre = [m['texte'] for m in timing['mots'] if m['page'] in (1, 2, 3)]
txt_b = ' '.join(livre)
print(f"=== livre p.1-3 : {len(livre)} mots ===")
print(txt_b[:600])
print()

# --- windows de similarité : pour chaque fenêtre de 10 mots whisper,
#     meilleur score moyen contre fenêtres glissantes du livre
w_norms = [normaliser(x) for x in ar]
w_norms = [x for x in w_norms if x]
b_norms = [normaliser(x) for x in livre]
b_norms = [x for x in b_norms if x]

def score_fenetre(i, L=8):
    wa = w_norms[i:i+L]
    if len(wa) < L: return None
    best, bj = 0.0, -1
    for j in range(0, len(b_norms) - L, 3):
        s = sum(similarite(wa[k], b_norms[j+k]) for k in range(L)) / L
        if s > best:
            best, bj = s, j
    return best, bj

print("=== meilleur ancrage par fenêtre de 8 mots Whisper (segment rejeté) ===")
scores = []
for i in range(0, len(w_norms) - 8, 8):
    r = score_fenetre(i)
    if r:
        scores.append((i, round(r[0], 2), r[1]))
        print(f"  w[{i:4d}:{i+8}]  best={r[0]:.2f}  @ livre[{r[1]}]")
import statistics
vals = [s[1] for s in scores]
print(f"\nmoyenne des meilleurs scores: {statistics.mean(vals):.2f} | médiane: {statistics.median(vals):.2f}")
