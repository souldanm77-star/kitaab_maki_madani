#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostic : pourquoi des lectures réelles sont-elles manquées ?
Compare des fenêtres de transcription Whisper avec le texte du livre
pour distinguer  (a) lectures manquées par le filtre  /  (b) somali/hors livre."""
import json
import sys
from pathlib import Path

PROJET = Path('/home/z/my-project/download/video-recitation')
sys.path.insert(0, str(PROJET / 'pipeline'))
from commun import normaliser, similarite, est_recitable  # noqa: E402

trans = json.load(open(PROJET / 'travail_darsi/dars1/transcription.json'))
pages = json.load(open(PROJET / 'travail_darsi/pages.json'))
timing = json.load(open(PROJET / 'travail_darsi/dars1/timing.json'))

# mots du livre normalisés (tout le livre)
livre = []
for p in pages['pages']:
    for m in p['mots']:
        n = normaliser(m['texte'])
        if n and est_recitable(m['texte']):
            livre.append((p['numero'], m['position'], n))
B = [n for _p, _q, n in livre]

# état surligné par mot whisper
etat_whisper = {}
for m in timing['mots']:
    pass  # timing est indexé par mots du LIVRE, pas whisper


def meilleur_score_fenetre(w_norms, j_debut=0, j_fin=None, taille=60):
    """Pour chaque fenêtre glissante de `taille` mots du livre, similarité
    moyenne des meilleures correspondances mot à mot (échantillonnée)."""
    j_fin = j_fin or len(B)
    best = 0.0; best_j = 0
    # échantillonne les fenêtres pour rester rapide
    pas = max(1, taille // 4)
    for j0 in range(j_debut, max(j_debut + 1, j_fin - taille), pas):
        s = 0.0; n = 0
        for w in w_norms:
            if not w:
                continue
            m = max((similarite(w, B[j]) for j in range(j0, min(j0 + taille, len(B)))),
                    default=0.0)
            s += m; n += 1
        moy = s / max(n, 1)
        if moy > best:
            best, best_j = moy, j0
    return best, best_j


# ---- fenêtres de 60 s d'audio à tester (zones sans surlignage) -------------
ZONES = [(60, 230), (900, 1000), (1500, 1600), (2000, 2100),
         (2600, 2700), (3000, 3100), (3300, 3400), (3600, 3700),
         (3900, 4000), (4200, 4300), (4500, 4600), (4700, 4800)]

w_mots = trans['mots']
print(f"{'zone':>12} | {'nb mots':>7} | {'%arabe':>6} | {'score':>5} | page~")
for d0, d1 in ZONES:
    fen = [w for w in w_mots if d0 <= w['debut'] < d1]
    norms = [normaliser(w['mot']) if est_recitable(w['mot']) else None
             for w in fen]
    n_ar = sum(1 for n in norms if n)
    pct_ar = 100 * n_ar / max(len(fen), 1)
    # sous-échantillonne pour la vitesse
    echant = [n for n in norms if n][::3][:40]
    score, j = meilleur_score_fenetre(echant, 0, len(B), 80)
    page = livre[min(j, len(livre) - 1)][0] if score > 0.2 else '?'
    print(f"{d0:>5}-{d1:<6} | {len(fen):>7} | {pct_ar:>5.0f}% | {score:>5.2f} | {page}")
