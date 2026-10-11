#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assemble les tranches rendues en une vidéo finale (concat sans ré-encodage).
Usage : python3 assembler_tranches.py <dossier_tranches> <sortie.mp4>
"""
import sys
from pathlib import Path
import subprocess

dossier = Path(sys.argv[1])
sortie = Path(sys.argv[2])
parts = sorted(dossier.glob('*_part*.mp4'))
if not parts:
    raise SystemExit(f"Aucune tranche dans {dossier}")
liste = dossier / 'concat.txt'
with open(liste, 'w') as f:
    for p in parts:
        f.write(f"file '{p.resolve()}'\n")
subprocess.run(['ffmpeg', '-nostdin', '-y', '-hide_banner', '-loglevel',
                'error', '-f', 'concat', '-safe', '0', '-i', str(liste),
                '-c', 'copy', '-movflags', '+faststart', str(sortie)],
               check=True)
print(f"OK -> {sortie} ({len(parts)} tranches)")
