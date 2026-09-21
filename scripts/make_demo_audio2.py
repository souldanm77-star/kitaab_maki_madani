# -*- coding: utf-8 -*-
"""Génère l'audio de démo : Fatiha + Ikhlas, verset par verset, avec pauses.
edge-tts (ar-SA-HamedNeural) -> concat ffmpeg avec silences."""
import asyncio
import subprocess
import tempfile
from pathlib import Path

import edge_tts

VOIX = 'ar-SA-HamedNeural'
SORTIE = '/home/z/my-project/download/video-recitation/demo/audio.mp3'

VERSETS = [
    'بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ',
    'الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ',
    'الرَّحْمَٰنِ الرَّحِيمِ',
    'مَالِكِ يَوْمِ الدِّينِ',
    'إِيَّاكَ نَعْبُدُ وَإِيَّاكَ نَسْتَعِينُ',
    'اهْدِنَا الصِّرَاطَ الْمُسْتَقِيمَ',
    'صِرَاطَ الَّذِينَ أَنْعَمْتَ عَلَيْهِمْ غَيْرِ الْمَغْضُوبِ عَلَيْهِمْ وَلَا الضَّالِّينَ',
    'قُلْ هُوَ اللَّهُ أَحَدٌ',
    'اللَّهُ الصَّمَدُ',
    'لَمْ يَلِدْ وَلَمْ يُولَدْ',
    'وَلَمْ يَكُن لَّهُ كُفُوًا أَحَدٌ',
]


async def generer():
    dossier = Path(tempfile.mkdtemp(prefix='tts_demo_'))
    fichiers = []
    for i, texte in enumerate(VERSETS):
        dest = dossier / f'v{i:02d}.mp3'
        tts = edge_tts.Communicate(texte, VOIX, rate='-12%')
        await tts.save(str(dest))
        fichiers.append(dest)
        print(f'  verset {i + 1}/{len(VERSETS)} ok')
    return fichiers


def concatener(fichiers):
    """Concatène avec 1,1 s de silence entre les versets."""
    args = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error']
    entrees, filtres = [], []
    for i, f in enumerate(fichiers):
        args += ['-i', str(f)]
    n = len(fichiers)
    courant = ''
    parties = []
    for i in range(n):
        if i == 0:
            courant = '0:a'
        parties.append(f'[{i}:a]')
        if i < n - 1:
            parties.append('aevalsrc=0:d=1.1:s=44100')
    # approche plus simple : concat brut + adelay par étage trop lourd —
    # on construit la piste silence puis concat[seq]
    filtres = []
    for i in range(n - 1):
        filtres.append(f'aevalsrc=0:d=1.1:s=44100[s{i}]')
    seq = []
    for i in range(n):
        seq.append(f'[{i}:a]')
        if i < n - 1:
            seq.append(f'[s{i}]')
    filtres.append(''.join(seq) + f'concat=n={2 * n - 1}:v=0:a=1[out]')
    args += ['-filter_complex', ';'.join(filtres), '-map', '[out]',
             '-c:a', 'libmp3lame', '-b:a', '128k', SORTIE]
    subprocess.run(args, check=True)


if __name__ == '__main__':
    fics = asyncio.run(generer())
    print('concaténation…')
    concatener(fics)
    d = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1', SORTIE],
        capture_output=True, text=True).stdout.strip()
    print(f'OK -> {SORTIE} ({float(d):.1f}s)')
