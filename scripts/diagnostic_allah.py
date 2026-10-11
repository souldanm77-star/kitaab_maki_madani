#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inspecte l'ordre FLUX vs ordre SPATIAL des caractères du mot لله."""
import sys

import fitz

sys.path.insert(0, '/home/z/my-project/download/video-recitation/pipeline')
from importlib import import_module
ex = import_module('1_extraire_pdf')

doc = fitz.open('/home/z/my-project/upload/LIVRE.pdf')
page = doc[0]
d = page.get_text('rawdict', flags=fitz.TEXT_PRESERVE_WHITESPACE |
                  fitz.TEXT_PRESERVE_LIGATURES)
k = 0
for bloc in d.get('blocks', []):
    if bloc.get('type') != 0:
        continue
    for line in bloc.get('lines', []):
        chars = [ch for sp in line.get('spans', [])
                 for ch in sp.get('chars', []) if ch['c'].strip()]
        txt = ''.join(ch['c'] for ch in chars)
        if 'لله' in txt or 'لهل' in txt or 'الله' in txt:
            k += 1
            print(f'--- ligne (flux) : {txt!r}')
            for ch in chars:
                b = ch['bbox']
                print(f"   {ch['c']!r}  x0={b[0]:7.2f} x1={b[2]:7.2f} "
                      f"y0={b[1]:7.2f} y1={b[3]:7.2f}")
            if k >= 1:
                sys.exit(0)
