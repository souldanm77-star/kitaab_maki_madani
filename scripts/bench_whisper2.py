#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cartographie du contenu audio + comparaison qualité small/medium avec prompt."""
import subprocess, time

AUDIO = '/home/z/my-project/download/video-recitation/entree/audio/dars1.mp3'

def extraire(t0, dur, nom):
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error',
                    '-ss', str(t0), '-t', str(dur), '-i', AUDIO,
                    '-ar', '16000', '-ac', '1', nom], check=True)

from faster_whisper import WhisperModel

PROMPT = ("في اسم الله الرحمن الرحيم الحمد لله نحمده ونستعينه ونستغفره ونعوذ بالله "
          "من شرور أنفسنا وبكلمة الله التامة نعوذ من شرور أنفسنا الكتاب الناسخ والمنسوخ "
          "المكي والمدني السور القرآن درس علم")

# ---- cartographie rapide avec base ----
m = WhisperModel('base', device='cpu', compute_type='int8')
for t0 in (0, 300, 900, 1800, 3000, 4200):
    extraire(t0, 30, '/tmp/map.wav')
    segs, _ = m.transcribe('/tmp/map.wav', language='ar', beam_size=1)
    txt = ' '.join(s.text.strip() for s in segs)[:150]
    print(f"t={t0:>5}s  base: {txt}")
del m

# ---- qualité : comparaison sur t=300 ----
extraire(300, 45, '/tmp/q.wav')
for modele, beam, prompt in (('small', 5, PROMPT), ('medium', 1, PROMPT)):
    t0 = time.time()
    m = WhisperModel(modele, device='cpu', compute_type='int8')
    segs, _ = m.transcribe('/tmp/q.wav', language='ar', word_timestamps=True,
                           beam_size=beam, initial_prompt=prompt)
    mots = []
    t_start = time.time()
    for s in segs:
        for w in (s.words or []):
            if (w.word or '').strip():
                mots.append(w.word.strip())
    dt = time.time() - t0
    print(f"\n{modele} beam={beam}: {dt:.1f}s pour 45s ({45/dt:.2f}x), {len(mots)} mots")
    print("   ", ' '.join(mots[:40]))
    del m
