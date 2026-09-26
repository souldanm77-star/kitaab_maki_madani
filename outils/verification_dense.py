#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vérification dense du surlignage sur les vidéos finales.
Pour chaque dars : échantillonnage à 0.5 fps sur toute la durée,
comptage de pixels jaunes (moitié droite = zone du livre),
rapport par plages de 60 s + synthèse de couverture.
"""
import subprocess, os, tempfile, sys, json

BASE = '/home/z/my-project/kitaab_maki_madani/download/video-recitation/sortie'
RAPPORT = '/home/z/my-project/kitaab_maki_madani/outils/verification_surlignage.json'

DUREES = {'dars1': 4819, 'dars2': 2752, 'dars3': 3834, 'dars4': 9012}
FPS = 0.5
TRANCHE = 300  # s par tranche d'extraction

def pixels_jaunes(img):
    w, h = img.size
    px = list(img.crop((960, 100, w, h - 100)).getdata())
    return sum(1 for r, g, b in px if r > 240 and g > 225 and b < 170)

def verifier(dars):
    video = f'{BASE}/{dars}.mp4'
    if not os.path.exists(video):
        return None
    duree = DUREES[dars]
    resultats = []  # (temps, px)
    tmp = tempfile.mkdtemp(prefix=f'ver_{dars}_')
    t = 0.0
    while t < duree - 1:
        fin = min(t + TRANCHE, duree)
        motif = os.path.join(tmp, 'f%05d.png')
        for f in os.listdir(tmp):
            os.unlink(os.path.join(tmp, f))
        subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error',
                        '-ss', f'{t:.2f}', '-i', video,
                        '-t', f'{fin - t:.2f}', '-vf', f'fps={FPS}', motif],
                       check=True)
        for k, fn in enumerate(sorted(os.listdir(tmp))):
            tt = t + k / FPS
            n = pixels_jaunes(
                __import__('PIL.Image', fromlist=['Image'])
                .open(os.path.join(tmp, fn)).convert('RGB'))
            resultats.append((round(tt, 1), n))
        t = fin
    subprocess.run(['rm', '-rf', tmp])
    # synthèse par minute
    par_min = {}
    for tt, n in resultats:
        m = int(tt // 60)
        par_min[m] = par_min.get(m, 0) + (1 if n > 200 else 0)
    tot = len(resultats)
    avec = sum(1 for _, n in resultats if n > 200)
    return {'dars': dars, 'frames': tot, 'frames_surlignees': avec,
            'pourcentage': round(100 * avec / max(tot, 1), 1),
            'par_minute': par_min, 'echantillon': resultats}

if __name__ == '__main__':
    darses = sys.argv[1:] or ['dars1', 'dars2', 'dars3', 'dars4']
    rapport = {}
    if os.path.exists(RAPPORT):
        rapport = json.load(open(RAPPORT))
    for d in darses:
        print(f'vérification {d}...', flush=True)
        try:
            r = verifier(d)
            if r:
                rapport[d] = r
                print(f"  {r['frames_surlignees']}/{r['frames']} frames "
                      f"surlignées ({r['pourcentage']}%)", flush=True)
        except Exception as e:
            print(f'  ERREUR: {e}', flush=True)
            rapport[d + '_erreur'] = str(e)
        json.dump(rapport, open(RAPPORT, 'w'))
    print('RAPPORT ->', RAPPORT)
