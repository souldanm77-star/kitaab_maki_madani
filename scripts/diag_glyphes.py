#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Diagnostic : caractères bruts de la page 14 du PDF — chercher les
# glyphes non mappés (U+FFFD / usage privé) et identifier ce qui manque.
import fitz
import unicodedata

pdf = '/home/z/my-project/download/video-recitation/audio/LIVRE.pdf'
doc = fitz.open(pdf)
page = doc[13]                       # page 14 (0-based 13)
d = page.get_text('rawdict', flags=fitz.TEXT_PRESERVE_WHITESPACE |
                  fitz.TEXT_PRESERVE_LIGATURES)

# 1) inventaire des caractères suspects sur la page
suspects = {}
for bloc in d.get('blocks', []):
    if bloc.get('type') != 0:
        continue
    for line in bloc.get('lines', []):
        for span in line.get('spans', []):
            for ch in span.get('chars', []):
                c = ch['c']
                o = ord(c)
                if o == 0xFFFD or 0xE000 <= o <= 0xF8FF or o == 0x25A1:
                    suspects.setdefault(c, 0)
                    suspects[c] += 1
print('caractères suspects (FFFD/usage privé):', {hex(ord(k)): v for k, v in suspects.items()})

# 2) afficher la ligne contenant «كتب» telle que PyMuPDF la voit
def norm_probe(s):
    return s
for bloc in d.get('blocks', []):
    if bloc.get('type') != 0:
        continue
    for line in bloc.get('lines', []):
        txt = ''
        for span in line.get('spans', []):
            for ch in span.get('chars', []):
                txt += ch['c']
        if 'عليكم' in txt or 'الوصية' in txt:
            # représentation par points de code
            codes = ' '.join(f'{ord(c):04X}' for c in txt if c.strip())
            print('LIGNE:', txt.strip()[:90])
            print('CODES:', codes[:200])
            print('---')

# 3) quelles polices ?
fonts = page.get_fonts()
for f in fonts:
    print('POLICE:', f[3], f[4] if len(f) > 4 else '')
