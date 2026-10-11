#!/usr/bin/env python3
# Vérification fine dars4 : échantillonnage dense des moments « jaune ABSENT »
# + vérification page affichée (MSE hors pixels jaunes)
import json
import subprocess
from PIL import Image

PROJ = '/home/z/my-project/download/video-recitation'
t = json.load(open(f'{PROJ}/travail_darsi/dars4/timing.json'))
runs = t['runs']


def jaune_a(tm, out='/tmp/vf.png'):
    """compte les pixels jaunes à l'instant tm (seek hybride)"""
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error',
                    '-ss', f'{max(0, tm - 12):.2f}', '-i', f'{PROJ}/sortie/dars4.mp4',
                    '-ss', '12', '-frames:v', '1', out], check=True)
    im = Image.open(out).convert('RGB')
    w, h = im.size
    px = list(im.crop((960, 100, w, h - 100)).getdata())
    return sum(1 for r, g, b in px if r > 240 and g > 225 and b < 170)


def page_ecart(tm, pg, out='/tmp/vf.png'):
    """écart moyen par canal entre la frame et le fond attendu,
    calculé HORS pixels jaunes (le surlignage fausse le MSE brut)"""
    im = Image.open(out).convert('RGB')
    w, h = im.size
    crop = im.crop((960, 100, w, h - 100))
    fond = Image.open(f'{PROJ}/travail_darsi/fonds/dars4/fond_p{pg:03d}.png') \
        .convert('RGB').crop((960, 100, w, h - 100))
    a, b = crop.getdata(), fond.getdata()
    tot, n = 0, 0
    for pa, pb in zip(a, b):
        if pa[0] > 240 and pa[1] > 225 and pa[2] < 170:
            continue          # pixel jaune = surlignage, ignoré
        tot += abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]) + abs(pa[2] - pb[2])
        n += 3
    return tot / n if n else 999.0


# ---- 1) run 1 (page 7, 6.82-9.7 s) : échantillonnage dense ---------------
r0 = runs[0]
print(f"run1: {r0['debut']}-{r0['fin']}s page {r0['page_debut']}")
for tm in [7.0, 7.4, 7.8, 8.2, 8.6, 9.0, 9.4]:
    j = jaune_a(tm)
    print(f"  t={tm}s jaune={j}")

# ---- 2) le run contenant 4193 s -----------------------------------------
r4 = [r for r in runs if r['debut'] <= 4193.2 <= r['fin']][0]
print(f"run@4193: {r4['debut']}-{r4['fin']} page {r4['page_debut']}")
for tm in [4193.0, 4193.6, 4194.2, 4194.8, 4195.4, 4196.0]:
    j = jaune_a(tm)
    print(f"  t={tm}s jaune={j}")

# ---- 3) page affichée aux 4 gros runs (MSE hors jaune) -------------------
print('=== Pages affichées (écart hors pixels jaunes, seuil OK < 8) ===')
for i in [len(runs) // 4, len(runs) // 2, 3 * len(runs) // 4, len(runs) - 1]:
    r = runs[i]
    tm = (r['debut'] + r['fin']) / 2
    jaune_a(tm)
    e = page_ecart(tm, r['page_debut'])
    print(f"  t={tm:7.1f}s page attendue {r['page_debut']:2d} -> écart={e:5.2f} "
          f"{'CONFORME' if e < 8 else 'ERREUR'}")
