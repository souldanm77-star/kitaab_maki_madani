#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Dump des caractères bruts (codes + bbox) pour :
#  - le mot « لله » de la khutba (page 1)
#  - une zone à kashidas (page 5)
import fitz

pdf = '/home/z/my-project/download/video-recitation/audio/LIVRE.pdf'
doc = fitz.open(pdf)


def dump(pno, match, label):
    page = doc[pno]
    d = page.get_text('rawdict', flags=fitz.TEXT_PRESERVE_WHITESPACE |
                      fitz.TEXT_PRESERVE_LIGATURES)
    print(f'===== {label} (page {pno + 1}) =====')
    trouve = 0
    for bloc in d.get('blocks', []):
        if bloc.get('type') != 0:
            continue
        for line in bloc.get('lines', []):
            txt = ''
            for span in line.get('spans', []):
                for ch in span.get('chars', []):
                    txt += ch['c']
            if match in txt:
                trouve += 1
                print('LIGNE:', txt.strip()[:70])
                items = []
                for span in line.get('spans', []):
                    for ch in span.get('chars', []):
                        if ch['c'].strip():
                            b = ch['bbox']
                            items.append((f'{ord(ch["c"]):04X}', ch['c'],
                                          round(b[0], 1), round(b[2], 1)))
                for it in items[:60]:
                    print('   ', it)
                print('---')
                if trouve >= 2:
                    return


dump(0, 'الحمد', 'KHUTBA الله page1')
