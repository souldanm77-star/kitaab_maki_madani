#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostic des 4 bugs de surlignage signalés par l'utilisateur."""
import json, re, sys
from pathlib import Path
from collections import Counter

RACINE = Path('/home/z/my-project/download/video-recitation')

def fmt_ass(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def parse_ass_time(s):
    h, m, sec = s.split(':')
    return int(h) * 3600 + int(m) * 60 + float(sec)

def analyser(dars):
    tj = RACINE / 'travail_darsi' / dars / 'timing.json'
    if not tj.exists():
        print(f"\n===== {dars} : timing.json ABSENT =====")
        return
    timing = json.loads(tj.read_text(encoding='utf-8'))
    mots = timing['mots']
    print(f"\n===== {dars} =====")
    print(f"duree audio: {timing.get('duree', 0):.1f}s  pages: {timing.get('pages')}")
    print(f"stats: {timing.get('stats')}")
    actifs = [m for m in mots if m.get('etat') in ('whisper', 'interpole') and m.get('debut') is not None]
    print(f"mots surlignables: {len(actifs)}")
    if actifs:
        debuts = [m['debut'] for m in actifs]
        print(f"plage surlignage: {min(debuts):.1f}s -> {max(m['fin'] for m in actifs):.1f}s")
        # histogramme par minute
        hist = Counter(int(d // 60) for d in debuts)
        for minute in sorted(hist):
            barre = '#' * min(60, hist[minute] // 5)
            print(f"  min {minute:2d}: {hist[minute]:4d} mots {barre}")
    # runs
    runs = timing.get('runs', [])
    print(f"runs actifs: {len(runs)}")
    for r in runs[:25]:
        print(f"  run {r['run']:3d}: {r['debut']:7.1f}s -> {r['fin']:7.1f}s  pages {r['page_debut']}-{r['page_fin']}  ({r['n_mots']} mots)  «{' '.join(r['texte'].split()[:5])}»")
    if len(runs) > 25:
        print(f"  ... +{len(runs)-25} autres")
    # pages couvertes par les mots actifs
    pages_actives = sorted(set(m['page'] for m in actifs))
    print(f"pages avec surlignage: {pages_actives[:30]}")
    # ASS
    ass = RACINE / 'travail_darsi' / dars / 'surlignage.ass'
    if ass.exists():
        txt = ass.read_text(encoding='utf-8')
        evs = re.findall(r'Dialogue: 0,([\d:.]+),([\d:.]+),', txt)
        if evs:
            t0 = [parse_ass_time(a) for a, b in evs]
            print(f"ASS: {len(evs)} événements, de {min(t0):.1f}s à {max(parse_ass_time(b) for a, b in evs):.1f}s")
        else:
            print("ASS: AUCUN événement !")
    else:
        print("ASS: fichier absent")

for d in sys.argv[1:] if len(sys.argv) > 1 else ['dars1']:
    analyser(d)
