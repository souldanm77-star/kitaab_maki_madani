#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vérifie la page affichée à des instants donnés : compare la zone page
de la frame aux fonds composés (fond_pXXX.png) et choisit la meilleure."""
import os
import subprocess
import sys
import tempfile

from PIL import Image

video = sys.argv[1]
dossier_fonds = sys.argv[2]
instants = [float(x) for x in sys.argv[3].split(',')]

fonds = {}
for fn in sorted(os.listdir(dossier_fonds)):
    if fn.startswith('fond_p') and fn.endswith('.png'):
        page = int(fn[6:9])
        img = Image.open(os.path.join(dossier_fonds, fn)).convert('RGB')
        fonds[page] = img.resize((320, 180))

def page_visible(video, t):
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error',
                        '-ss', f'{t:.3f}', '-t', '0.2', '-i', video,
                        '-vf', 'scale=320:180', '-start_number', '0',
                        os.path.join(tmp, 'f%03d.png')], check=True)
        fn = sorted(os.listdir(tmp))[0]
        frame = Image.open(os.path.join(tmp, fn)).convert('RGB')
    pf = list(frame.getdata())
    meilleur, score = None, 1e18
    for page, fond in fonds.items():
        px = list(fond.getdata())
        diff = sum(abs(a[0]-b[0]) + abs(a[1]-b[1]) + abs(a[2]-b[2])
                   for a, b in zip(pf, px)) / len(px)
        if diff < score:
            meilleur, score = page, diff
    return meilleur, score

print(f"{'instant':>9} | page visible | confiance")
for t in instants:
    page, diff = page_visible(video, t)
    print(f"{t:9.1f} | p{page:^11} | diff={diff:.1f}")
