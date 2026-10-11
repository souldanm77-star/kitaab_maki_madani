#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostic des gaps intra/inter-mot sur le vrai PDF (page 1)."""
import fitz
import statistics

doc = fitz.open('/home/z/my-project/download/video-recitation/entree/livre.pdf')
page = doc[0]
d = page.get_text('rawdict',
                  flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES)

# prendre la 3e ligne du 1er bloc (ligne de corps de texte)
groupes = []
for bloc in d.get('blocks', []):
    if bloc.get('type') != 0:
        continue
    for line in bloc.get('lines', []):
        chars = []
        for span in line.get('spans', []):
            for ch in span.get('chars', []):
                if ch['c'].strip():
                    chars.append((ch['bbox'], ch['c']))
        if chars:
            groupes.append(chars)

print(f"{len(groupes)} groupes 'ligne' bruts sur la page 1")
chars = sorted(groupes[2], key=lambda t: -t[0][2])   # ligne de corps, tri RTL
print("\nCaractères (x0..x1 c) et gap avec le précédent (RTL) :")
prev = None
gaps = []
for b, c in chars:
    g = (prev - b[2]) if prev is not None else 0.0
    gaps.append(g)
    print(f"  x[{b[0]:6.1f}..{b[2]:6.1f}] gap {g:6.2f}  {c!r}")
    prev = b[0]

positifs = sorted(g for g in gaps if g > 0.05)
print(f"\nGaps > 0.05pt : n={len(positifs)}")
if positifs:
    print(f"  min={positifs[0]:.2f} p25={positifs[len(positifs)//4]:.2f} "
          f"med={statistics.median(positifs):.2f} p75={positifs[3*len(positifs)//4]:.2f} "
          f"max={positifs[-1]:.2f}")
    # histogramme grossier
    import collections
    hist = collections.Counter(round(g * 2) / 2 for g in positifs)
    for v in sorted(hist):
        print(f"   gap~{v:5.1f}pt : {'#' * min(60, hist[v])} ({hist[v]})")

# largeur médiane des lettres
larges = sorted(b[2] - b[0] for b, c in chars if '\u0621' <= c <= '\u064A')
print(f"\nLargeur médiane lettre : {larges[len(larges)//2]:.2f}pt, "
      f"nombre de chars dans la ligne : {len(chars)}")

# comparer avec la ligne 2 de la page 2 (police différente ?)
page2 = doc[1]
d2 = page2.get_text('rawdict', flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES)
g2 = []
for bloc in d2.get('blocks', []):
    if bloc.get('type') != 0:
        continue
    for line in bloc.get('lines', []):
        cs = [(ch['bbox'], ch['c']) for span in line.get('spans', [])
              for ch in span.get('chars', []) if ch['c'].strip()]
        if cs:
            g2.append(cs)
cs2 = sorted(g2[1], key=lambda t: -t[0][2])
prev = None
gaps2 = []
for b, c in cs2:
    g = (prev - b[2]) if prev is not None else 0.0
    gaps2.append(g)
    prev = b[0]
pos2 = sorted(g for g in gaps2 if g > 0.05)
print(f"\nPAGE 2 ligne 2 : gaps>0.05 : n={len(pos2)}, "
      f"med={statistics.median(pos2):.2f}, max={pos2[-1]:.2f}")
import collections
hist2 = collections.Counter(round(g * 2) / 2 for g in pos2)
for v in sorted(hist2):
    print(f"   gap~{v:5.1f}pt : {'#' * min(60, hist2[v])} ({hist2[v]})")
