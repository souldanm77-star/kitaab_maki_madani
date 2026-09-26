#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vérification du surlignage jaune par échantillonnage de frames.
Méthode éprouvée : extraire des séquences fps puis compter les pixels
jaunes (r>240, g>225, b<170) dans la moitié droite (zone du livre).
⚠ Une frame unique extraite exactement à t=start d'un événement ASS
  donne un faux négatif — d'où les séquences fps=1 minimum.
Usage : verifier_surlignage.py <video> <t_debut> <t_fin> [fps]
"""
import subprocess, sys, os, tempfile
from PIL import Image

video = sys.argv[1]
t0 = float(sys.argv[2])
t1 = float(sys.argv[3])
fps = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0

dossier = tempfile.mkdtemp(prefix='verif_')
motif = os.path.join(dossier, 'f%05d.png')
subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error',
                '-ss', f'{t0:.2f}', '-i', video,
                '-t', f'{t1-t0:.2f}', '-vf', f'fps={fps}',
                motif], check=True)

fichiers = sorted(os.listdir(dossier))
print(f'{"temps":>8} {"px jaunes":>10}  verdict')
n_avec = 0
for k, fn in enumerate(fichiers):
    t = t0 + k / fps
    img = Image.open(os.path.join(dossier, fn)).convert('RGB')
    w, h = img.size
    px = list(img.crop((960, 100, w, h - 100)).getdata())
    n = sum(1 for r, g, b in px if r > 240 and g > 225 and b < 170)
    verdict = 'SURLIGNÉ' if n > 200 else ('faible' if n > 50 else '-')
    if n > 200:
        n_avec += 1
    print(f'{t:8.1f} {n:10d}  {verdict}')
print(f'\n{n_avec}/{len(fichiers)} frames avec surlignage')
subprocess.run(['rm', '-rf', dossier])
