#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analyse de la distribution des runs et des rejets dans dars1."""
import json

with open('/home/z/my-project/download/video-recitation/travail_darsi/dars1/timing.json') as f:
    t = json.load(f)

runs = t['runs']
duree = t['duree']
print(f"=== {len(runs)} runs actifs sur {duree/60:.0f} min ===")
print("\nDistribution temporelle (诵读秒数/每5分钟):")
bins = {}
for r in runs:
    b = int(r['debut'] // 300)
    bins[b] = bins.get(b, 0) + (r['fin'] - r['debut'])
for b in sorted(bins):
    bar = '#' * int(bins[b] / 2)
    print(f"  {b*5:3d}-{b*5+5:3d} min : {bins[b]:6.1f}s {bar}")

# positions dans le livre (j = index dans b_norms reconstruit depuis runs)
print("\nRuns par page:")
pages = {}
for r in runs:
    for p in range(r['page_debut'], r['page_fin'] + 1):
        pages[p] = pages.get(p, 0) + 1
print(f"  pages touchées: {sorted(pages)}")

# segments hors_livre longs
print("\nSegments hors_livre > 30s (candidats lectures manquées):")
for s in t['segments']:
    if s['type'] == 'hors_livre' and s['fin'] - s['debut'] > 30:
        print(f"  {s['debut']:7.1f} → {s['fin']:7.1f}  ({(s['fin']-s['debut']):5.1f}s, {s['n_mots']:3d} mots)  {s['texte'][:70]}")
