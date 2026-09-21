#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test : écarts inter-mots calculés sur LETTRES SEULES (hors diacritiques)."""
import sys

import fitz

sys.path.insert(0, '/home/z/my-project/download/video-recitation/pipeline')
from importlib import import_module
ex = import_module('1_extraire_pdf')

PDF = '/home/z/my-project/upload/LIVRE.pdf'
doc = fitz.open(PDF)


def est_lettre(c):
    return '\u0621' <= c <= '\u064A'


for pno in (0, 1):
    page = doc[pno]
    groupes = ex.grouper_caracteres(page)
    rangees = ex.fusionner_en_rangees(groupes)
    print('=' * 78)
    print(f'PAGE {pno + 1}')
    for ri, r in enumerate(rangees[:4]):
        # lettres seules, triées RTL
        lettres = [(b, c) for b, c in r['chars'] if est_lettre(c)]
        lettres = sorted(lettres, key=lambda t: (-t[0][2], t[0][0]))
        gaps = sorted(round(b1[0] - b2[2], 2)
                      for (b1, c1), (b2, c2) in zip(lettres, lettres[1:]))
        pos = [g for g in gaps if g > 0]
        print(f'  r{ri}: {len(lettres)} lettres | gaps>0 : {pos[:30]}')
        # texte de la rangée dans l'ordre de lecture RTL (pour référence)
        txt = ''.join(c for _, c in lettres)
        print(f'      texte: {txt[:70]}')
