#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inspecte les runs actifs : texte des mots appariés + scores moyens,
pour distinguer citations arabes réelles et faux positifs somali."""
import json
from pathlib import Path

T = json.load(open('/home/z/my-project/download/video-recitation/'
                   'travail_darsi/dars1/timing.json', encoding='utf-8'))

print(f"{len(T['runs'])} runs actifs\n")
for r in T['runs']:
    print(f"run {r['run']:>3}  {r['debut']:>7.1f}s → {r['fin']:>7.1f}s  "
          f"p{r['page_debut']}-p{r['page_fin']}  ({r['n_mots']:>3} mots)  "
          f"{r['texte'][:80]}")

# transcription brute autour de quelques runs suspects
TR = json.load(open('/home/z/my-project/download/video-recitation/'
                    'travail_darsi/dars1/transcription.json',
                    encoding='utf-8'))
mots = TR['mots']

def apercu(t0, t1):
    seg = [m['mot'] for m in mots if t0 - 4 <= m['debut'] <= t1 + 4]
    return ' '.join(seg)[:150]

print('\n--- contexte audio autour de runs choisis ---')
for num in (1, 24, 33, 60, 90, 110, 125, 139):
    r = T['runs'][num - 1]
    print(f"\nrun {num} ({r['debut']:.0f}s, p{r['page_debut']}) :")
    print(f"   audio : {apercu(r['debut'], r['fin'])}")
