#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostic v2 : affiche côte à côte transcription Whisper et texte du livre
pour juger visuellement si une zone est une lecture réelle ou du somali déformé."""
import json
import sys
from pathlib import Path

PROJET = Path('/home/z/my-project/download/video-recitation')
sys.path.insert(0, str(PROJET / 'pipeline'))
from commun import normaliser, similarite, est_recitable  # noqa: E402

trans = json.load(open(PROJET / 'travail_darsi/dars1/transcription.json'))
pages = json.load(open(PROJET / 'travail_darsi/pages.json'))

livre = []
for p in pages['pages']:
    for m in p['mots']:
        n = normaliser(m['texte'])
        if n and est_recitable(m['texte']):
            livre.append((p['numero'], m['position'], n, m['texte']))
B = [x[2] for x in livre]

w_mots = trans['mots']


def montrer(d0, d1, titre):
    fen = [w for w in w_mots if d0 <= w['debut'] < d1]
    norms = [normaliser(w['mot']) if est_recitable(w['mot']) else None
             for w in fen]
    # trouve la fenêtre de livre la plus proche globalement ( DP simple par
    # somme des max de similarité, fenêtre de 120 mots, pas 20)
    best, bj = -1, 0
    for j0 in range(0, max(1, len(B) - 120), 20):
        s = sum(max((similarite(n, B[j]) for j in range(j0, min(j0 + 120, len(B)))),
                    default=0.0) for n in norms if n)
        if s > best:
            best, bj = s, j0
    print(f"\n{'=' * 78}\n{titre}  (t={d0}-{d1}s) — meilleure zone livre: page "
          f"{livre[min(bj, len(livre)-1)][0]}, pos {livre[min(bj, len(livre)-1)][1]}")
    print("--- WHISPER (60 premiers mots) ---")
    txt = ' '.join(w['mot'] for w in fen[:60])
    print(txt)
    print("--- LIVRE (80 mots à la position trouvée) ---")
    print(' '.join(x[3] for x in livre[bj:bj + 80]))


montrer(3000, 3080, "ZONE A (entre run 48 et 49)")
montrer(4200, 4280, "ZONE B (entre run 49 et 50)")
monoser = None
montrer(460, 540, "ZONE C (autour du run 9 détecté, pour comparaison)")
