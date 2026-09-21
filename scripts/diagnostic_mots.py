#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostic du découpage de mots : distributions d'écarts par rangée."""
import sys
from pathlib import Path

import fitz

sys.path.insert(0, '/home/z/my-project/download/video-recitation/pipeline')
from commun import normaliser
from importlib import import_module
ex = import_module('1_extraire_pdf')

PDF = '/home/z/my-project/upload/LIVRE.pdf'
doc = fitz.open(PDF)

for pno in (0, 1, 3):                      # pages 1, 2, 4
    page = doc[pno]
    groupes = ex.grouper_caracteres(page)
    rangees = ex.fusionner_en_rangees(groupes)
    print('=' * 78)
    print(f'PAGE {pno + 1} — {len(rangees)} rangées')
    for ri, r in enumerate(rangees[:6]):
        chars = sorted(r['chars'], key=lambda t: (-t[0][2], t[0][0]))
        gaps = []
        for (b1, c1), (b2, c2) in zip(chars, chars[1:]):
            gaps.append(round(b1[0] - b2[2], 2))     # RTL
        gaps_pos = sorted(g for g in gaps if g > 0)
        larges = sorted(b[2] - b[0] for b, c in chars
                        if '\u0621' <= c <= '\u064A')
        med = larges[len(larges) // 2] if larges else 4.0
        seuil = ex.seuil_de_rangee(chars, med)
        mots = ex.mots_de_rangee(r['chars'])
        apercu = ' '.join(normaliser(m['texte'])[:14] for m in mots[:6])
        print(f'  r{ri:>2}: {len(chars):>3} car, méd={med:.2f}, '
              f'seuil={seuil:.2f}, {len(mots)} mots')
        print(f'       gaps>0 : {gaps_pos[:28]}')
        print(f'       mots   : {apercu}')
