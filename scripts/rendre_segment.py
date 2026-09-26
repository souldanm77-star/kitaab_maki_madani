#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rendu SEGMENTÉ d'un dars : rend le segment N (1700 s) ou assemble les
segments terminés. Contourne la limite des appels d'outils (575 s) : chaque
segment de 1700 s de vidéo se rend en ~440 s."""
import argparse
import subprocess
import sys
from pathlib import Path

import json

PROJET = Path('/home/z/my-project/download/video-recitation')
SEG = 1700.0


def plan_segments(duree):
    n = int(duree // SEG) + (1 if duree % SEG else 0)
    return [(k * SEG, min((k + 1) * SEG, duree)) for k in range(n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dars', required=True)
    ap.add_argument('--seg', type=int, default=None,
                    help='numéro du segment à rendre (0-based)')
    ap.add_argument('--assemble', action='store_true',
                    help='assemble les segments en vidéo finale')
    args = ap.parse_args()

    sortie_dir = PROJET / 'sortie'
    seg_dir = sortie_dir / f'segments_{args.dars}'
    seg_dir.mkdir(exist_ok=True)

    if args.assemble:
        parts = sorted(seg_dir.glob('seg_*.mp4'))
        if not parts:
            raise SystemExit('aucun segment trouvé')
        lst = seg_dir / 'liste.txt'
        lst.write_text(''.join(f"file '{p.name}'\n" for p in parts))
        final = sortie_dir / f'{args.dars}.mp4'
        cmd = ['ffmpeg', '-nostdin', '-y', '-hide_banner', '-loglevel',
               'error', '-f', 'concat', '-safe', '0', '-i', str(lst),
               '-c:v', 'copy', '-c:a', 'aac', '-b:a', '160k',
               '-movflags', '+faststart', str(final)]
        subprocess.run(cmd, check=True)
        print(f'OK -> {final}')
        return

    # rendu d'un segment
    with open(PROJET / 'travail_darsi' / args.dars / 'timing.json',
              encoding='utf-8') as f:
        duree = float(json.load(f)['duree'])
    plan = plan_segments(duree)
    if args.seg is None or args.seg >= len(plan):
        raise SystemExit(f'seg {args.seg} hors plan ({len(plan)} segments)')
    t0, t1 = plan[args.seg]
    dest = seg_dir / f'seg_{args.seg:02d}.mp4'
    if dest.exists() and dest.stat().st_size > 100_000:
        print(f'seg {args.seg} déjà rendu : {dest}')
        return
    print(f'rendu segment {args.seg}: [{t0:.0f}s, {t1:.0f}s) '
          f'-> {dest.name}')
    cmd = [sys.executable, str(PROJET / 'pipeline' / '4_video.py'),
           '--config', str(PROJET / 'config_darsi.json'),
           '--dars', args.dars,
           '--debut', f'{t0:.3f}', '--fin', f'{t1:.3f}',
           '--sortie', str(dest)]
    subprocess.run(cmd, check=True)
    print(f'OK seg {args.seg} -> {dest}')


if __name__ == '__main__':
    main()
