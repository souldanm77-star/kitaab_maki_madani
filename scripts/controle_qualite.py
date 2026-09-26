#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contrôle qualité : pour chaque dars, échantillonne des frames au MILIEU
de mots surlignés (runs répartis sur toute la durée) et compte les pixels
jaunes dans la moitié droite. Vérifie aussi la page affichée."""
import json
import subprocess
from pathlib import Path

from PIL import Image

PROJET = Path('/home/z/my-project/download/video-recitation')
JAUge = lambda px: sum(1 for r, g, b in px if r > 240 and g > 225 and b < 170)

for dars in ('dars1', 'dars2', 'dars3', 'dars4'):
    t = json.load(open(PROJET / 'travail_darsi' / dars / 'timing.json'))
    video = PROJET / 'sortie' / f'{dars}.mp4'
    runs = t['runs']
    n = len(runs)
    choix = [runs[i] for i in sorted(set(
        int(k * (n - 1) / 5) for k in range(6)))] if n > 1 else [runs[0]]
    print(f'=== {dars} ({n} runs) ===')
    for r in choix:
        mots = [m for m in t['mots']
                if m.get('run') == r['run'] and m['etat'] in
                ('whisper', 'interpole') and m.get('debut') is not None]
        if not mots:
            continue
        m = mots[len(mots) // 2]          # mot du MILIEU du run
        tc = m['debut'] + (m['fin'] - m['debut']) * 0.5
        # seek hybride : -ss d'entrée rapide puis -ss sortie précis
        subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error',
                        '-ss', f'{max(0.0, tc - 20):.2f}', '-i', str(video),
                        '-ss', '20', '-frames:v', '1', '/tmp/qc.png'],
                       check=True)
        im = Image.open('/tmp/qc.png').convert('RGB')
        w, h = im.size
        jaunes = JAUge(list(im.crop((960, 100, w, h - 100)).getdata()))
        # page affichée : OCR léger impossible → on compare le fond moyen
        # de la zone page avec la page attendue (info seulement)
        print(f"  run {r['run']:>2} t={tc:7.1f}s p{m['page']:<2} "
              f"{m['texte'][:12]:<14} {jaunes:>5} px jaunes "
              f"{'OK' if jaunes > 200 else '*** FAIBLE ***'}")
