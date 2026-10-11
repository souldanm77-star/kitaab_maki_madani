#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transcrit UNE tranche de l'audio réel (contrainte sandbox : appel < 10 min).
Usage : python3 transcrire_chunk.py <debut_s> <fin_s> <fichier_sortie.json>
- extraction wav 16 kHz mono par ffmpeg
- faster-whisper small/int8, beam=1, word_timestamps, VAD, prompt arabe
- les timestamps sont décalés du début de tranche -> temps global
"""
import json
import subprocess
import sys
import time
from pathlib import Path

AUDIO = '/home/z/my-project/download/video-recitation/entree/audio/dars1.mp3'
PROMPT = ("بسم الله الرحمن الرحيم الحمد لله نحمده ونستعينه ونستغفره ونعوذ بالله "
          "من شرور أنفسنا ومن سيئات أعمالنا، الناسخ والمنسوخ، المكي والمدني، "
          "السور المكية، القرآن الكريم، الدرس العلمي")

def main():
    debut, fin, sortie = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
    Path(sortie).parent.mkdir(parents=True, exist_ok=True)
    wav = '/tmp/tranche.wav'
    t0 = time.time()
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error',
                    '-ss', f'{debut:.2f}', '-t', f'{fin - debut:.2f}',
                    '-i', AUDIO, '-ar', '16000', '-ac', '1', wav], check=True)
    from faster_whisper import WhisperModel
    model = WhisperModel('small', device='cpu', compute_type='int8')
    segs, info = model.transcribe(
        wav, language='ar', word_timestamps=True, vad_filter=True,
        beam_size=1, initial_prompt=PROMPT)
    mots, segments = [], []
    for s in segs:
        segments.append({'debut': round(s.start + debut, 3),
                         'fin': round(s.end + debut, 3),
                         'texte': (s.text or '').strip()})
        for w in (s.words or []):
            mot = (w.word or '').strip()
            if mot:
                mots.append({'mot': mot,
                             'debut': round(w.start + debut, 3),
                             'fin': round(w.end + debut, 3)})
    out = {'tranche': [debut, fin], 'duree_tranche': round(fin - debut, 3),
           'duree_audio': round(info.duration + debut, 3), 'mots': mots,
           'segments': segments,
           'temps_calcul': round(time.time() - t0, 1)}
    Path(sortie).write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
    print(f"OK tranche {debut:.0f}-{fin:.0f}s : {len(mots)} mots en "
          f"{time.time() - t0:.0f}s -> {sortie}")

if __name__ == '__main__':
    main()
