#!/usr/bin/env python3
# Vérification FINALE des 4 vidéos : page affichée (argmin sur tous les
# fonds du dars) + présence du surlignage jaune, avec seek EXACT
# (keyframe réelle + décode jusqu'au temps cible).
import json
import subprocess
from pathlib import Path
from PIL import Image

PROJ = Path('/home/z/my-project/download/video-recitation')
DARS = {
    'dars1': 4819.296,
    'dars2': 2751.744,
    'dars3': 3834.864,
    'dars4': 9011.520,
}


def keyframe_avant(vid, tm):
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


def frame_exacte(vid, tm, out='/tmp/vfin.png'):
    kf = keyframe_avant(vid, tm)
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error',
                    '-ss', f'{kf:.3f}', '-i', str(vid),
                    '-ss', f'{tm - kf:.3f}', '-frames:v', '1', out],
                   check=True)
    return Image.open(out).convert('RGB')


def pixels_jaunes(im):
    w, h = im.size
    return sum(1 for r, g, b in im.crop((960, 100, w, h - 100)).getdata()
               if r > 240 and g > 225 and b < 170)


def ecart_hors_jaune(px_a, px_b):
    tot = 0
    for pa, pb in zip(px_a, px_b):
        if pa[0] > 200 and pa[1] > 180 and pa[2] < 190 and \
           (pa[0] - pa[2]) > 40:
            continue
        tot += abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]) + abs(pa[2] - pb[2])
    return tot / (len(px_a) * 3)


print('=== VÉRIFICATION FINALE (seek exact, page par argmin) ===')
bilan = {}
for d, _duree in DARS.items():
    vid = PROJ / 'sortie' / f'{d}.mp4'
    timing = json.load(open(PROJ / 'travail_darsi' / d / 'timing.json'))
    runs = [r for r in timing['runs'] if r['fin'] - r['debut'] >= 2.0]
    # fonds disponibles
    fonds = {}
    for fp in sorted((PROJ / 'travail_darsi' / 'fonds' / d).glob('fond_p*.png')):
        pg = int(fp.stem.replace('fond_p', ''))
        im = Image.open(fp).convert('RGB')
        w, h = im.size
        fonds[pg] = list(im.crop((960, 100, w, h - 100)).getdata())
    # 5 runs répartis
    pas = max(1, len(runs) // 5)
    choix = runs[::pas][:5]
    ok_pages = ok_jaune = 0
    print(f'--- {d} ({len(runs)} runs testables) ---')
    for r in choix:
        tm = r['debut'] + (r['fin'] - r['debut']) / 2
        im = frame_exacte(vid, tm)
        jaune = pixels_jaunes(im)
        w, h = im.size
        px = list(im.crop((960, 100, w, h - 100)).getdata())
        ecarts = {pg: ecart_hors_jaune(px, fx) for pg, fx in fonds.items()}
        detectee = min(ecarts, key=ecarts.get)
        attendue = r['page_debut']
        bon = detectee == attendue
        jaune_ok = jaune > 400
        ok_pages += bon
        ok_jaune += jaune_ok
        print(f"  t={tm:7.1f}s attendue={attendue:2d} détectée={detectee:2d} "
              f"({'OK' if bon else 'ERREUR'}) jaune={jaune:5d} "
              f"({'OK' if jaune_ok else 'ABSENT'})")
    bilan[d] = (ok_pages, len(choix), ok_jaune, len(choix))

print('=== BILAN ===')
for d, (p, np_, j, nj) in bilan.items():
    print(f'  {d}: pages {p}/{np_} conformes, surlignage {j}/{nj} présents')
