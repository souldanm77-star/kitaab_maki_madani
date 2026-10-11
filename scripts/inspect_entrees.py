#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inspection des 3 fichiers réels uploadés : PDF, image, audio."""
import subprocess
from pathlib import Path

import fitz  # PyMuPDF

UP = Path('/home/z/my-project/upload')

# ---------------------------------------------------------------- PDF ----
pdf = UP / 'LIVRE.pdf'
print('=' * 70)
print(f'PDF : {pdf}  ({pdf.stat().st_size / 1e6:.1f} Mo)')
doc = fitz.open(str(pdf))
print(f'  pages : {doc.page_count}')
total_chars, pages_texte = 0, 0
for i in range(min(6, doc.page_count)):
    page = doc[i]
    d = page.get_text('rawdict')
    nch = sum(len(sp.get('chars', []))
              for b in d.get('blocks', []) if b.get('type') == 0
              for ln in b.get('lines', []) for sp in ln.get('spans', []))
    nimg = len(page.get_images(full=True))
    print(f'  page {i + 1}: {nch:>5} caracteres, {nimg} image(s), '
          f'{page.rect.width:.0f}x{page.rect.height:.0f} pt')
    total_chars += nch
    pages_texte += 1
print(f'  -> moyenne caracteres/page (6 premieres) : {total_chars / max(1, pages_texte):.0f}')

# echantillon de texte de la page 2 (si textuel)
if total_chars > 100:
    for i in (1, 2):
        if i < doc.page_count:
            t = doc[i].get_text('text')[:220].replace('\n', ' | ')
            print(f'  extrait page {i + 1} : {t!r}')

# -------------------------------------------------------------- image ----
img = UP / 'IMAGE.jpeg'
print('=' * 70)
print(f'IMAGE : {img}  ({img.stat().st_size / 1e6:.2f} Mo)')
from PIL import Image
im = Image.open(img)
print(f'  format : {im.format}  dimensions : {im.width}x{im.height}  mode : {im.mode}')

# -------------------------------------------------------------- audio ----
aud = UP / 'Audio darsi-1.mpeg'
print('=' * 70)
print(f'AUDIO : {aud}  ({aud.stat().st_size / 1e6:.1f} Mo)')
r = subprocess.run(
    ['ffprobe', '-v', 'error', '-show_entries',
     'format=duration,format_name,bit_rate', '-show_entries',
     'stream=codec_name,codec_type,sample_rate,channels',
     '-of', 'default=noprint_wrappers=1', str(aud)],
    capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip())
