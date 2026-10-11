#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dump des codepoints de la 1re ligne de texte de la page 1."""
import fitz

doc = fitz.open('/home/z/my-project/upload/LIVRE.pdf')
page = doc[0]
d = page.get_text('rawdict', flags=fitz.TEXT_PRESERVE_WHITESPACE |
                  fitz.TEXT_PRESERVE_LIGATURES)
blocs = [b for b in d.get('blocks', []) if b.get('type') == 0]
print(f"{len(blocs)} blocs de texte")
n = 0
for bloc in blocs:
    for line in bloc.get('lines', []):
        chars = [ch for sp in line.get('spans', [])
                 for ch in sp.get('chars', [])]
        if not chars:
            continue
        n += 1
        if n > 3:
            break
        txt = ''.join(ch['c'] for ch in chars)
        print(f'--- ligne {n} (flux, {len(chars)} car) ---')
        print(f'    texte: {txt[:80]!r}')
        print('    codepoints:', ' '.join(f"{ord(c):04X}" for c in txt[:50]))
        # positions des caractères non blancs, ordre flux
        for ch in chars[:45]:
            b = ch['bbox']
            print(f"   {ch['c']!r} U+{ord(ch['c']):04X} "
                  f"x0={b[0]:7.2f} x1={b[2]:7.2f}")
    if n > 3:
        break
