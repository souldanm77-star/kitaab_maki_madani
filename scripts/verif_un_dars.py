#!/usr/bin/env python3
# Vérification pages+surlignage pour UN dars passé en argument.
# Usage: python3 verif_un_dars.py <dars> [<nb_tests>]
import json
import subprocess
import sys
from pathlib import Path
from PIL import Image

PROJ = Path('/home/z/my-project/download/video-recitation')
d = sys.argv[1]
nb = int(sys.argv[2]) if len(sys.argv) > 2 else 5
vid = PROJ / 'sortie' / f'{d}.mp4'

timing = json.load(open(PROJ / 'travail_darsi' / d / 'timing.json'))
runs = [r for r in timing['runs'] if r['fin'] - r['debut'] >= 2.0]
fonds = {}
for fp in sorted((PROJ / 'travail_darsi' / 'fonds' / d).glob('fond_p*.png')):
    pg = int(fp.stem.replace('fond_p', ''))
    im = Image.open(fp).convert('RGB')
    w, h = im.size
    fonds[pg] = list(im.crop((960, 100, w, h - 100)).getdata())


def keyframe_avant(tm):
    r = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v',
         '-read_intervals', f'{max(0, tm - 40)}%{tm}',
         '-show_entries', 'frame=pts_time,keyframe', '-of', 'csv=p=0',
         str(vid)], capture_output=True, text=True, check=True)
    kf = 0.0
    for ligne in r.stdout.splitlines():
        parts = ligne.strip().split(',')
        if len(parts) >= 2 and parts[1] == '1':
            try:
                v = float(parts[0])
                if v <= tm:
                    kf = v
            except ValueError:
                pass
    return kf


def frame_exacte(tm, out='/tmp/vun.png'):
    kf = keyframe_avant(tm)
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error',
                    '-ss', f'{kf:.3f}', '-i', str(vid),
                    '-ss', f'{tm - kf:.3f}', '-frames:v', '1', out],
                   check=True)
    return Image.open(out).convert('RGB')


def ecart_hors_jaune(px_a, px_b):
    tot = 0
    for pa, pb in zip(px_a, px_b):
        if pa[0] > 200 and pa[1] > 180 and pa[2] < 190 and \
           (pa[0] - pa[2]) > 40:
            continue
        tot += abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]) + abs(pa[2] - pb[2])
    return tot / (len(px_a) * 3)


pas = max(1, len(runs) // nb)
choix = runs[::pas][:nb]
okp = okj = 0
print(f'--- {d} : {len(runs)} runs testables, {len(choix)} vérifiés ---')
for r in choix:
    tm = r['debut'] + (r['fin'] - r['debut']) / 2
    im = frame_exacte(tm)
    w, h = im.size
    jaune = sum(1 for rr, g, b in im.crop((960, 100, w, h - 100)).getdata()
                if rr > 240 and g > 225 and b < 170)
    px = list(im.crop((960, 100, w, h - 100)).getdata())
    ecarts = {pg: ecart_hors_jaune(px, fx) for pg, fx in fonds.items()}
    det = min(ecarts, key=ecarts.get)
    bon, jok = det == r['page_debut'], jaune > 250
    okp += bon
    okj += jok
    print(f"  t={tm:7.1f}s attendue={r['page_debut']:2d} détectée={det:2d} "
          f"({'OK' if bon else 'ERREUR'}) jaune={jaune:5d} "
          f"({'OK' if jok else 'faible/absent'})")
print(f'BILAN {d}: pages {okp}/{len(choix)}, surlignage {okj}/{len(choix)}')
