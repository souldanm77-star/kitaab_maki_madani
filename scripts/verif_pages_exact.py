#!/usr/bin/env python3
# Vérification EXACTE des pages affichées : seek sur keyframe réelle
# (ffprobe -read_intervals) puis décode jusqu'au temps cible précis.
import json
import subprocess
from PIL import Image

PROJ = '/home/z/my-project/download/video-recitation'
VID = f'{PROJ}/sortie/dars4.mp4'
t = json.load(open(f'{PROJ}/travail_darsi/dars4/timing.json'))
runs = t['runs']

# précharger les fonds (panneau droit)
fonds = {}
for pg in [7, 9, 16, 18, 19, 20, 21, 22, 23]:
    im = Image.open(f'{PROJ}/travail_darsi/fonds/dars4/fond_p{pg:03d}.png') \
        .convert('RGB')
    w, h = im.size
    fonds[pg] = list(im.crop((960, 100, w, h - 100)).getdata())


def keyframe_avant(tm):
    """dernière keyframe <= tm dans [tm-40, tm]"""
    r = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v',
         '-read_intervals', f'{max(0, tm - 40)}%{tm}',
         '-show_entries', 'frame=pts_time,keyframe',
         '-of', 'csv=p=0', VID],
        capture_output=True, text=True, check=True)
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


def frame_exacte(tm, out='/tmp/vx.png'):
    kf = keyframe_avant(tm)
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error',
                    '-ss', f'{kf:.3f}', '-i', VID,
                    '-ss', f'{tm - kf:.3f}', '-frames:v', '1', out],
                   check=True)
    im = Image.open(out).convert('RGB')
    w, h = im.size
    return list(im.crop((960, 100, w, h - 100)).getdata())


def ecart(px_a, px_b):
    tot = 0
    for pa, pb in zip(px_a, px_b):
        if pa[0] > 200 and pa[1] > 180 and pa[2] < 190 and \
           (pa[0] - pa[2]) > 40:
            continue      # pixels teintés par le surligneur
        tot += abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]) + abs(pa[2] - pb[2])
    return tot / (len(px_a) * 3)


# moments de test : MILIEU de runs longs, loin des transitions de pages
print('=== dars4 : vérification EXACTE des pages (keyframe + decode) ===')
cibles = []
for i, r in enumerate(runs):
    duree = r['fin'] - r['debut']
    if duree >= 2.0:                     # run assez long pour être stable
        cibles.append((i, r, r['debut'] + duree / 2))
# garder 8 runs répartis
pas = max(1, len(cibles) // 8)
for i, r, tm in cibles[::pas][:8]:
    px = frame_exacte(tm)
    ecarts = {pg: ecart(px, fx) for pg, fx in fonds.items()}
    meilleure = min(ecarts, key=ecarts.get)
    attendue = r['page_debut']
    verdict = 'CONFORME' if meilleure == attendue else 'ERREUR'
    print(f"  t={tm:7.1f}s run {r['run']:2d} attendue={attendue:2d} -> "
          f"détectée={meilleure:2d} ({ecarts[meilleure]:.1f} vs "
          f"{ecarts[attendue]:.1f}) {verdict}")
