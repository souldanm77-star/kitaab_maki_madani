#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vérifie la qualité de la chaîne d'ancrages : (wi, bj) doit être une
escalier monotone régulier si le cheikh lit linéairement le livre."""
import json, importlib.util, sys
sys.path.insert(0, '/home/z/my-project/download/video-recitation/pipeline')
from commun import normaliser, similarite, est_recitable, charger_json

spec = importlib.util.spec_from_file_location(
    "aligner3", "/home/z/my-project/download/video-recitation/pipeline/3_aligner.py")
al = importlib.util.module_from_spec(spec)
spec.loader.exec_module(al)

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

ancrages = al.chercher_ancrages(w_norms, b_norms)
print(f"{len(ancrages)} ancrages")
print("\n(sauts entre ancrages consécutifs : dw=écart Whisper, db=écart livre)")
print("Les grands db>0 avec dw petit = MORCEAUX DU LIVRE SAUTÉS par la chaîne")
prev = None
sauts_grands = 0
for k, (i, j) in enumerate(ancrages):
    if prev:
        dw, db = i - prev[0], j - prev[1]
        if db > 8 or dw > 25:
            sauts_grands += 1
            if sauts_grands <= 40:
                print(f"  ancre {k:3d}: w[{prev[0]}→{i}] (dw={dw:4d})  b[{prev[1]}→{j}] (db={db:4d})  "
                      f"t={w_mots[i]['debut']:7.1f}s  mot_w=«{w_mots[i]['mot'][:14]}» mot_b=«{b_norms[j][:14]}»")
    prev = (i, j)
print(f"\ntotal sauts anormaux : {sauts_grands} / {len(ancrages)}")

# couverture : derniers/1ers ancrages
print(f"\n1er ancre: w[{ancrages[0][0]}] ↔ b[{ancrages[0][1]}]   (b=0 si le dars commence au début du livre)")
print(f"dernier ancre: w[{ancrages[-1][0]}] ↔ b[{ancrages[-1][1]}] (b={len(b_norms)-1} = fin du livre)")
