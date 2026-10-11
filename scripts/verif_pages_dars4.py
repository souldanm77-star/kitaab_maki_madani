#!/usr/bin/env python3
# Preuve de conformité des pages affichées : pour chaque moment testé,
# on compare la frame (hors zone panneau cheikh) à TOUS les fonds
# disponibles et on désigne la page la plus proche (argmin).
# La transparence du surligneur teinte la zone surlignée -> l'écart absolu
# peut rester >8 même sur la bonne page ; l'ARGMIN est la preuve fiable.
import json
import subprocess
from PIL import Image

PROJ = '/home/z/my-project/download/video-recitation'
t = json.load(open(f'{PROJ}/travail_darsi/dars4/timing.json'))
runs = t['runs']

# précharger les fonds (panneau droit uniquement)
fonds = {}
for pg in [7, 9, 16, 18, 19, 20, 21, 22, 23]:
    im = Image.open(f'{PROJ}/travail_darsi/fonds/dars4/fond_p{pg:03d}.png') \
        .convert('RGB')
    w, h = im.size
    fonds[pg] = list(im.crop((960, 100, w, h - 100)).getdata())


def ecart(tm, pg, out='/tmp/vp.png'):
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error',
                    '-ss', f'{max(0, tm - 12):.2f}',
                    '-i', f'{PROJ}/sortie/dars4.mp4',
                    '-ss', '12', '-frames:v', '1', out], check=True)
    im = Image.open(out).convert('RGB')
    w, h = im.size
    a = list(im.crop((960, 100, w, h - 100)).getdata())
    b = fonds[pg]
    tot = 0
    for pa, pb in zip(a, b):
        # ignorer les pixels teintés par le surligneur (jaune fort ou mélange)
        if pa[0] > 200 and pa[1] > 180 and pa[2] < 190 and \
           (pa[0] - pa[2]) > 40:
            continue
        tot += abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]) + abs(pa[2] - pb[2])
    n = len(a) * 3
    return tot / n


print('=== dars4 : page affichée = argmin sur tous les fonds ===')
for i in [0, len(runs) // 4, len(runs) // 2, 3 * len(runs) // 4,
          len(runs) - 1]:
    r = runs[i]
    tm = (r['debut'] + r['fin']) / 2
    attendue = r['page_debut']
    ecarts = {pg: ecart(tm, pg) for pg in fonds}
    meilleure = min(ecarts, key=ecarts.get)
    verdict = 'CONFORME' if meilleure == attendue else 'ERREUR'
    print(f"  t={tm:7.1f}s attendue={attendue:2d} -> détectée={meilleure:2d} "
          f"(écart {ecarts[meilleure]:.1f} vs attendue {ecarts[attendue]:.1f}) {verdict}")
