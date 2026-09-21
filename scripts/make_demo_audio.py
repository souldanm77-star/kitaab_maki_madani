#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixture de démo — crée demo/audio.mp3 : récitation TTS (Fatiha + Ikhlas)."""
import asyncio
import os
import subprocess

import edge_tts

ICI = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.join(ICI, "..", "download", "synchronisation-recitation",
                    "demo")
VOIX = "ar-SA-HamedNeural"

FATIHA = ("بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ ، "
          "الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ ، "
          "الرَّحْمَٰنِ الرَّحِيمِ ، "
          "مَالِكِ يَوْمِ الدِّينِ ، "
          "إِيَّاكَ نَعْبُدُ وَإِيَّاكَ نَسْتَعِينُ ، "
          "اهْدِنَا الصِّرَاطَ الْمُسْتَقِيمَ ، "
          "صِرَاطَ الَّذِينَ أَنْعَمْتَ عَلَيْهِمْ غَيْرِ الْمَغْضُوبِ عَلَيْهِمْ وَلَا الضَّالِّينَ")
IKHLAS = ("قُلْ هُوَ اللَّهُ أَحَدٌ ، "
          "اللَّهُ الصَّمَدُ ، "
          "لَمْ يَلِدْ وَلَمْ يُولَدْ ، "
          "وَلَمْ يَكُن لَّهُ كُفُوًا أَحَدٌ")


async def synth(texte, sortie):
    tts = edge_tts.Communicate(texte, voice=VOIX, rate="-10%")
    await tts.save(sortie)
    print("✔", sortie)


async def main():
    os.makedirs(DEMO, exist_ok=True)
    f1 = os.path.join(DEMO, "_tts_fatiha.mp3")
    f2 = os.path.join(DEMO, "_tts_ikhlas.mp3")
    final = os.path.join(DEMO, "audio.mp3")
    await synth(FATIHA, f1)
    await synth(IKHLAS, f2)
    subprocess.run([
        "ffmpeg", "-y",
        "-i", f1, "-i", f2,
        "-filter_complex",
        "[1]adelay=1200|1200[d2];[0][d2]amix=inputs=2:duration=longest,"
        "apad=pad_dur=0.6[out]",
        "-map", "[out]", "-b:a", "160k", final,
    ], check=True, capture_output=True)
    os.remove(f1)
    os.remove(f2)
    print("✔ audio de démo concaténé →", final)


asyncio.run(main())
