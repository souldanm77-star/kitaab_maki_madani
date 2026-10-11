#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostic des 4 bugs signalés par l'utilisateur :
  1) dars1 : interruption à 1:01, plus aucun surlignage ensuite
  2) dars2 : aucun surlignage visible
  3) dars3 : aucun surlignage visible
  4) dars4 : sur-surlignage + mauvais suivi de pages
Analyse : timing.json (runs/mots), concat.txt (fenêtres de pages rendues),
         transcription.json (langues whisper), surlignage.ass (événements).
"""
import json, re, sys, os
from collections import defaultdict

BASE = '/home/z/my-project/kitaab_maki_madani/download/video-recitation'

def lire_concat(dars):
    """Retourne [(page, debut, fin)] depuis le fichier concat."""
    chemin = f'{BASE}/sortie/{dars}_concat.txt'
    res, t = [], 0.0
    if not os.path.exists(chemin):
        return res
    fichier = None
    for ligne in open(chemin):
        ligne = ligne.strip()
        m = re.match(r"file '.*fond_p(\d+)\.png'", ligne)
        if m:
            fichier = int(m.group(1))
            continue
        m = re.match(r'duration ([0-9.]+)', ligne)
        if m and fichier:
            d = float(m.group(1))
            res.append((fichier, t, t + d))
            t += d
    return res

def analyser(dars):
    tj = json.load(open(f'{BASE}/travail_darsi/{dars}/timing.json'))
    stats = tj['stats']
    runs = tj['runs']
    mots = tj['mots']
    segs = json.load(open(f'{BASE}/travail_darsi/{dars}/transcription.json'))
    segs = segs if isinstance(segs, list) else segs.get('segments', [])
    duree = tj.get('duree', 0)

    print(f'{"="*78}')
    print(f'### {dars.upper()}  — durée audio {duree/60:.1f} min')
    print(f'  stats: runs_actifs={stats.get("runs_actifs")} appariements={stats.get("appariements")} etats={stats.get("etats")}')

    # --- Langues whisper ---
    langs = defaultdict(float)
    for s in segs:
        langs[s.get('langue', '?')] += s['fin'] - s['debut']
    print(f'  langues whisper: ' + ', '.join(f'{k}={v/60:.1f}min' for k, v in sorted(langs.items(), key=lambda x: -x[1])))

    # --- Runs actifs ---
    tot_surl = sum(r['fin'] - r['debut'] for r in runs)
    n_mots_surl = sum(r['n_mots'] for r in runs)
    pages_runs = sorted({r['page_debut'] for r in runs} | {r['page_fin'] for r in runs})
    print(f'  RUNS: {len(runs)} | durée surlignée totale {tot_surl/60:.1f} min ({100*tot_surl/max(duree,1):.1f}%) | {n_mots_surl} mots')
    print(f'  pages des runs: {pages_runs}')

    # --- Mots surlignés par page ---
    par_page = defaultdict(int)
    for m in mots:
        if m.get('etat') in ('whisper', 'interpole'):
            par_page[m['page']] += 1
    print(f'  mots surlignés par page: {dict(sorted(par_page.items()))}')

    # --- Timeline des runs (groupée) ---
    print(f'  --- timeline des runs (t en min) ---')
    for r in runs:
        print(f'    {r["debut"]/60:6.1f} → {r["fin"]/60:6.1f} min  p{r["page_debut"]:>2}  {r["n_mots"]:>3} mots  {r["texte"][:40]}')

    # --- Fenêtres concat ---
    win = lire_concat(dars)
    print(f'  --- fenêtres de pages rendues (concat) ---')
    for p, d, f in win:
        print(f'    {d/60:6.1f} → {f/60:6.1f} min  page {p:>2}  ({f-d:7.1f}s)')

    # --- Incohérences concat vs runs ---
    err = []
    for r in runs:
        t = (r['debut'] + r['fin']) / 2
        aff = next((p for p, d, f in win if d <= t < f), None)
        if aff is not None and aff not in (r['page_debut'], r['page_fin']):
            err.append((r['run'], r['debut']/60, r['page_debut'], aff))
    if err:
        print(f'  ⚠ INCOHÉRENCES page affichée vs page lue: {len(err)}/{len(runs)} runs')
        for rn, tm, plue, paff in err[:12]:
            print(f'     run{rn} à {tm:.1f} min : lit p{plue}, écran montre p{paff}')
    else:
        print(f'  ✓ toutes les pages affichées correspondent aux pages lues')

    # --- surlignage.ass ---
    ass = f'{BASE}/travail_darsi/{dars}/surlignage.ass'
    if os.path.exists(ass):
        evs = [l for l in open(ass) if l.startswith('Dialogue:')]
        print(f'  surlignage.ass: {len(evs)} événements de surlignage')
        def s2t(s):
            h, m, rest = s.split(':'); sec, cs = rest.split('.')
            return int(h)*3600 + int(m)*60 + int(sec) + int(cs)/100
        dur = 0.0
        for e in evs:
            parties = e.split(',')
            try:
                dur += s2t(parties[1]) - s2t(parties[2].split('{')[0])
            except Exception:
                pass
        print(f'    durée totale cumulée des rectangles: {dur/60:.1f} min')
    print()

for d in ['dars1', 'dars2', 'dars3', 'dars4']:
    try:
        analyser(d)
    except Exception as e:
        print(f'ERREUR {d}: {type(e).__name__}: {e}\n')
