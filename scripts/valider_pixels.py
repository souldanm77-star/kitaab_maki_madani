#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validation pixels jaunes du rendu : échantillonne des frames aux moments
des runs d'un dars et compte les pixels jaunes (surlignage visible)."""
import json, subprocess, sys, tempfile, os
from pathlib import Path
from PIL import Image

RACINE = Path('/home/z/my-project/download/video-recitation')

def jaunes(video, t):
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        tmp = f.name
    r = subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error',
                        '-ss', str(max(0, t - 0.2)), '-i', str(video),
                        '-frames:v', '1', tmp],
                       capture_output=True)
    if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
        return -1
    img = Image.open(tmp).convert('RGB')
    w, h = img.size
    # moitié droite (zone page) : r>240, g>225, b<170
    px = list(img.crop((w // 2, 100, w, h - 100)).getdata())
    n = sum(1 for r_, g_, b_ in px if r_ > 240 and g_ > 225 and b_ < 170)
    os.unlink(tmp)
    return n

def main(dars):
    video = RACINE / 'sortie' / f'{dars}.mp4'
    if not video.exists():
        print(f"{video} ABSENT"); return
    timing = json.loads((RACINE / 'travail_darsi' / dars / 'timing.json').read_text(encoding='utf-8'))
    actifs = [m for m in timing['mots'] if m.get('etat') in ('whisper', 'interpole') and m.get('debut') is not None]
    runs = timing.get('runs', [])
    print(f"=== {dars} : {len(runs)} runs, {len(actifs)} mots actifs ===")
    # échantillonner : milieu de 8 runs répartis + 3 zones sans run
    echant = []
    if runs:
        pas = max(1, len(runs) // 8)
        for r in runs[::pas][:8]:
            mil = (r['debut'] + r['fin']) / 2
            echant.append((mil, f"run {r['run']} p{r['page_debut']}"))
    # zones calmes (entre runs, milieu des plus grands gaps)
    fins = [r['fin'] for r in runs]; debuts = [r['debut'] for r in runs]
    gaps = [(b - a, (a + b) / 2) for a, b in zip(fins, debuts[1:]) if b - a > 60]
    for g, mil in sorted(gaps, reverse=True)[:3]:
        echant.append((mil, f"silence {g:.0f}s"))
    for t, lbl in sorted(echant):
        n = jaunes(video, t)
        verdict = ('SURLIGNE' if n > 800 else 'rien') if n >= 0 else 'ERREUR'
        print(f"  t={t:7.1f}s  {lbl:<18} jaunes={n:6d}  -> {verdict}")

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'dars1')
