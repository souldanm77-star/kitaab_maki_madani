#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vérification mot à mot : pour N mots du CSV, sonde [debut-0.1, fin+0.1]
à fps=10 et compte les mots dont au moins 1 frame contient le rectangle
jaune. Seuil PROPORTIONNEL à la surface du rectangle écran du mot (un mot
court couvre surtout son glyphe sombre -> moins de pixels jaune-papier)."""
import csv
import json
import math
import os
import subprocess
import sys
import tempfile

from PIL import Image

video = os.path.abspath(sys.argv[1])
csv_path = os.path.abspath(sys.argv[2])
n_ech = int(sys.argv[3]) if len(sys.argv) > 3 else 20
projet = os.path.dirname(csv_path).split('/sortie')[0]
cfg = json.load(open(os.path.join(projet, 'config_darsi.json'), encoding='utf-8'))
pages = json.load(open(os.path.join(projet, 'travail_darsi/pages.json'),
                       encoding='utf-8'))
v = cfg['video']
LW = v['panneau_cheikh']['largeur']
RW = v['largeur'] - LW
W, H = v['largeur'], v['hauteur']
dpi = pages['dpi']
ratio = dpi / 72.0
pad = v.get('surlignage', {}).get('pad', 5)

# échelle s2 identique à composer_fond (pages toutes de mêmes dimensions ~)
p0 = pages['pages'][0]
img = Image.open(os.path.join(projet, 'travail_darsi', p0['image']))
mx, my = 36, 36
s2 = min((RW - 2 * mx) / img.width, (H - 2 * my) / img.height)
ox = LW + (RW - 2) // 4  # approx ox: la valeur exacte importe peu pour le
oy = 0                   # SEUL calcul de surface (pas de position)
SC = ratio * s2


def surface_ecran(m):
    x0, x1 = m['x0'] * SC, m['x1'] * SC
    y0, y1 = m['y0'] * SC, m['y1'] * SC
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    lx = max(16, (x1 - x0) + 2 * pad)
    ly = max(22, (y1 - y0) + 2 * pad)
    return lx * ly


rows = list(csv.reader(open(csv_path, encoding='utf-8'), delimiter=';'))[1:]
# garder les mots dont on connaît les coordonnées (jointure timing)
timing = json.load(open(os.path.join(projet,
                     'travail_darsi/' + os.path.basename(csv_path)
                     .replace('_synchronisation.csv', '/timing.json')),
                     encoding='utf-8'))['mots']
pos2mot = {}
for m in timing:
    if m.get('debut') is not None and m.get('etat') in ('whisper', 'interpole'):
        pos2mot[(m['page'], m['position'])] = m

pas = max(1, len(rows) // n_ech)
echantillon = rows[::pas][:n_ech]

ok, ko = 0, []
with tempfile.TemporaryDirectory() as tmp:
    for r in echantillon:
        mot, debut, fin, page, position = r[0], float(r[1]), float(r[2]), \
            int(r[3]), int(r[4])
        m = pos2mot.get((page, position))
        if not m:
            continue
        # les frames sont extraites en 960x540 = surface / 4
        seuil = max(40.0, 0.055 * surface_ecran(m))
        t0 = max(0.0, debut - 0.1)
        t1 = fin + 0.1
        for fn in os.listdir(tmp):
            os.remove(os.path.join(tmp, fn))
        subprocess.run(
            ['ffmpeg', '-nostdin', '-y', '-loglevel', 'error',
             '-ss', f'{t0:.3f}', '-t', f'{t1 - t0:.3f}',
             '-i', video, '-vf', 'fps=10,scale=960:540',
             '-start_number', '0', os.path.join(tmp, 'f%03d.png')],
            check=True)
        trouve = False
        for fn in sorted(os.listdir(tmp)):
            img2 = Image.open(os.path.join(tmp, fn)).convert('RGB')
            w, h = img2.size
            px = list(img2.crop((w // 2, 50, w, h - 50)).getdata())
            jaunes = sum(1 for rr, gg, bb in px
                         if rr > 240 and gg > 225 and bb < 170)
            if jaunes >= seuil:
                trouve = True
                break
        if trouve:
            ok += 1
        else:
            ko.append((mot, debut, page, round(seuil)))
print(f"=== {ok}/{len(echantillon)} mots vérifiés surlignés à l'écran")
for mot, debut, page, seuil in ko:
    print(f"    MANQUÉ: {mot} @ {debut:.2f}s p{page} (seuil {seuil}px)")
