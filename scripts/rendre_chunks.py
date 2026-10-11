#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rend une liste de chunks du plan (un appel sandbox = plusieurs chunks).
Usage : python3 rendre_chunks.py <config> <dars> <i1> <i2> ...
Saute les chunks déjà rendus (reprise possible)."""
import subprocess
import sys
from pathlib import Path

ici = Path(__file__).resolve().parent
sys.path.insert(0, str(ici.parent / 'download/video-recitation/pipeline'))

from commun import charger_json, charger_config, chemin_projet  # noqa: E402

config = charger_config(sys.argv[1])
dars = sys.argv[2]
indices = [int(a) for a in sys.argv[3:]]

travail = chemin_projet(config, config.get('travail', 'travail'))
plan = charger_json(travail / dars / 'plan_rendu.json')
sorties = chemin_projet(config, config.get('sortie', 'sortie')) / 'tranches'

for i in indices:
    c = plan['chunks'][i]
    out = sorties / f"{dars}_part{i:03d}.mp4"
    if out.exists() and out.stat().st_size > 10000:
        print(f"chunk {i}: déjà rendu -> {out.name}")
        continue
    duree = c['t1'] - c['t0']
    print(f"=== chunk {i} : page {c['page']} {c['t0']:.0f}->{c['t1']:.0f}s "
          f"({duree:.0f}s) ===", flush=True)
    r = subprocess.run(['python3',
                        str(ici.parent / 'download/video-recitation/pipeline/4_video.py'),
                        '--config', sys.argv[1], '--dars', dars,
                        '--chunk', str(i)])
    if r.returncode != 0:
        print(f"chunk {i} ÉCHOUÉ (code {r.returncode})")
        sys.exit(r.returncode)
print("terminé")
