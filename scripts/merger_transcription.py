#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fusionne les tranches de transcription en transcription.json."""
import glob
import json

parts = []
for f in sorted(glob.glob('/home/z/my-project/download/video-recitation/travail/dars1/tranche_*.json')):
    d = json.load(open(f))
    parts.append(d)

mots, segments = [], []
for d in parts:
    mots += d['mots']
    segments += d['segments']
mots.sort(key=lambda m: m['debut'])
segments.sort(key=lambda s: s['debut'])

# dédoublonnage sur les bords de tranches (même instant ±0.15s, même mot)
propres = []
for m in mots:
    if propres and abs(m['debut'] - propres[-1]['debut']) < 0.15 \
            and m['mot'] == propres[-1]['mot']:
        continue
    propres.append(m)

out = {'dars': 'dars1', 'audio': 'entree/audio/dars1.mp3',
       'modele': 'small (6 tranches, beam=1, prompt arabe)',
       'duree': 4819.296, 'langue': 'ar',
       'mots': propres, 'segments': segments}
with open('/home/z/my-project/download/video-recitation/travail/dars1/transcription.json',
          'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(f"OK : {len(propres)} mots (bruts {len(mots)}), {len(segments)} segments")
print("Aperçu début:", ' '.join(m['mot'] for m in propres[:15]))
print("Aperçu fin  :", ' '.join(m['mot'] for m in propres[-10:]))
