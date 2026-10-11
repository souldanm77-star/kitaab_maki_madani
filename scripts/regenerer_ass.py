#!/usr/bin/env python3
# Régénère les fichiers travail_darsi/<dars>/surlignage.ass COMPLETS
# (tous les mots alignés, sans rendu vidéo) à partir des timing.json
# et des transformations de fonds déjà calculées.
import json
import sys
from pathlib import Path

sys.path.insert(0, '/home/z/my-project/download/video-recitation/pipeline')
from commun import charger_config, charger_json, chemin_projet  # noqa: E402
import importlib.util

spec = importlib.util.spec_from_file_location(
    'quatre', '/home/z/my-project/download/video-recitation/pipeline/4_video.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

PROJ = Path('/home/z/my-project/download/video-recitation')
cfg = charger_config(str(PROJ / 'config_darsi.json'))
travail = chemin_projet(cfg, cfg.get('travail', 'travail'))
pages = charger_json(Path(travail) / 'pages.json')

for d in ['dars1', 'dars2', 'dars3', 'dars4']:
    dars = cfg['darses'][d]
    timing = charger_json(Path(travail) / d / 'timing.json')
    p1, p2 = dars['pages']
    mots = [m for m in timing['mots'] if p1 <= m['page'] <= p2]
    transfos_mem = charger_json(Path(travail) / 'fonds' / d / 'transfos.json')
    mode = dars.get('mode') or 'mot'
    entete, evenements = None, []
    for p in sorted({m['page'] for m in mots
                     if m.get('etat') in ('whisper', 'interpole')}):
        mots_page = [m for m in mots if m['page'] == p]
        ent, ev = mod.generer_ass(cfg, mots_page, transfos_mem[str(p)],
                                  pages['dpi'], mode)
        entete = ent
        evenements += ev
    dest = Path(travail) / d / 'surlignage.ass'
    dest.write_text(entete + "\n".join(evenements) + "\n", encoding='utf-8')
    print(f'{d}: {len(evenements)} événements -> {dest}')
