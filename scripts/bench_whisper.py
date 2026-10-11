#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Benchmark Whisper sur 60s de l'audio réel pour choisir modèle + taille de tranches."""
import time
import subprocess

# extraire 60s
subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error',
                '-ss', '120', '-t', '60',
                '-i', '/home/z/my-project/download/video-recitation/entree/audio/dars1.mp3',
                '-ar', '16000', '-ac', '1',
                '/tmp/bench60.wav'], check=True)

from faster_whisper import WhisperModel

for modele in ('small', 'base'):
    t0 = time.time()
    m = WhisperModel(modele, device='cpu', compute_type='int8')
    t_load = time.time() - t0
    t0 = time.time()
    segs, info = m.transcribe('/tmp/bench60.wav', language='ar',
                              word_timestamps=True, vad_filter=True,
                              beam_size=1)
    n_mots = 0
    texte = []
    for s in segs:
        for w in (s.words or []):
            if (w.word or '').strip():
                n_mots += 1
                texte.append(w.word.strip())
    dt = time.time() - t0
    print(f"{modele}: chargement {t_load:.1f}s, transcription 60s audio en {dt:.1f}s "
          f"-> vitesse {60/dt:.2f}x temps réel, {n_mots} mots")
    print("   texte:", ' '.join(texte[:20]))
    del m
