#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vérifie le surlignage jaune sur une vidéo : extrait une séquence fps=2
et compte les pixels jaunes (zone page = moitié droite)."""
import subprocess
import sys
from PIL import Image
import tempfile
import os

video = sys.argv[1]
t0, t1 = float(sys.argv[2]), float(sys.argv[3])
seuil = int(sys.argv[4]) if len(sys.argv) > 4 else 300

with tempfile.TemporaryDirectory() as tmp:
    subprocess.run(
        ['ffmpeg', '-nostdin', '-y', '-loglevel', 'error',
         '-ss', str(t0), '-t', str(t1 - t0),
         '-i', video, '-vf', 'fps=2,scale=960:540',
         '-start_number', '0', os.path.join(tmp, 'f%04d.png')],
        check=True)
    fichiers = sorted(os.listdir(tmp))
    total_actif = 0
    for i, fn in enumerate(fichiers):
        img = Image.open(os.path.join(tmp, fn)).convert('RGB')
        w, h = img.size
        px = list(img.crop((w // 2, 50, w, h - 50)).getdata())
        jaunes = sum(1 for r, g, b in px
                     if r > 240 and g > 225 and b < 170)
        t = t0 + i / 2.0
        if jaunes >= seuil:
            total_actif += 1
            print(f"  t={t:7.1f}s  {jaunes:5d} px jaunes  << SURLIGNÉ")
        else:
            print(f"  t={t:7.1f}s  {jaunes:5d} px")
    print(f"=== {total_actif}/{len(fichiers)} frames surlignées "
          f"(seuil {seuil} px)")
