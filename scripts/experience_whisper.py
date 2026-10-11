#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Expérience : comparer 3 configurations Whisper sur le même extrait.
A = multilingual beam=1          (config actuelle, mauvaise qualité)
B = language='ar' beam=1         (force l'arabe)
C = language='ar' beam=5 + prompt(force l'arabe + indication vocabulaire)
Score = similarité moyenne des meilleures fenêtres de 8 mots vs livre p.1-3.
"""
import json, time, statistics, sys
sys.path.insert(0, '/home/z/my-project/download/video-recitation/pipeline')
from commun import normaliser, similarite

with open('/home/z/my-project/download/video-recitation/travail_darsi/dars1/timing.json') as f:
    timing = json.load(f)
b_norms = [normaliser(m['texte']) for m in timing['mots'] if m['page'] in (1, 2, 3)]
b_norms = [x for x in b_norms if x]

PROMPT = ("إن الحمد لله نحمده ونستعينه ونستغفره ونعوذ بالله من شرور أنفسنا "
          "ومن سيئات أعمالنا. علوم القرآن المكي والمدني الناسخ والمنسوخ "
          "بنزول القرآن التشريع الإسلامي")

CONFIGS = {
    'A multilingue beam1': dict(language=None, multilingual=True, beam_size=1),
    'B ar force beam1':    dict(language='ar', beam_size=1),
    'C ar beam5 prompt':   dict(language='ar', beam_size=5, initial_prompt=PROMPT),
}

from faster_whisper import WhisperModel
model = WhisperModel('small', device='cpu', compute_type='int8')

resultats = {}
for nom, kw in CONFIGS.items():
    t0 = time.time()
    kwargs = dict(word_timestamps=True, vad_filter=True,
                  condition_on_previous_text=False)
    kwargs.update(kw)
    try:
        segments, info = model.transcribe('/home/z/my-project/scripts/extrait_test.wav', **kwargs)
        mots = []
        for seg in segments:
            for wd in (seg.words or []):
                mot = (wd.word or '').strip()
                if mot:
                    mots.append(mot)
    except TypeError:
        continue
    dt = time.time() - t0
    w_norms = [normaliser(x) for x in mots]
    w_norms = [x for x in w_norms if x]
    # score : pour chaque fenêtre de 8 mots whisper -> meilleur score moyen
    scores = []
    L = 8
    for i in range(0, len(w_norms) - L, 4):
        wa = w_norms[i:i + L]
        best = 0.0
        for j in range(0, len(b_norms) - L, 2):
            s = sum(similarite(wa[k], b_norms[j + k]) for k in range(L)) / L
            if s > best:
                best = s
        scores.append(best)
    moy = statistics.mean(scores) if scores else 0
    resultats[nom] = (moy, dt, len(mots))
    print(f"\n### {nom} : score={moy:.3f}  temps={dt:.0f}s  mots={len(mots)}")
    print('    début :', ' '.join(mots[:25]))

print("\n===== RÉSUMÉ =====")
for nom, (moy, dt, nm) in resultats.items():
    print(f"{nom:24s} score={moy:.3f} temps={dt:5.0f}s mots={nm}")
