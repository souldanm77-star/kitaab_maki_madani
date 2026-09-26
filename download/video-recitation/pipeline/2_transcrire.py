#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÉTAPE 2 — Transcription Whisper MULTILINGUE (arabe + somali), par morceaux
==========================================================================
L'audio d'un dars mélange l'arabe (lecture du livre + explications) et le
somali. Le pipeline :
  1. découpe l'audio en morceaux WAV 16 kHz (480 s) — découpes précises ;
  2. transcrit chaque morceau avec détection de langue PAR SEGMENT
     (multilingual=True) et horodatage MOT À MOT ;
  3. chaque mot reçoit sa langue détectée (ar/so/…) → servira à
     l'étiquetage des segments (lecture / somali / arabe hors livre).
     NB : la décision de surlignage reste basée sur la CORRESPONDANCE
     avec le texte du livre (étape 3), pas sur la langue seule.

Reprise : chaque morceau terminé est mis en cache (morceau_XXX.json) ;
relancer la commande recommence là où elle s'était arrêtée.

Sortie : travail/<dars>/transcription.json
"""
import argparse
import subprocess
import time
from pathlib import Path

from commun import sauver_json, charger_config, chemin_projet, duree_media

DUREE_MORCEAU = 480.0        # secondes par morceau
BUDGET = 480.0               # budget de traitement par invocation (s)


def preparer_morceaux(audio: Path, dossier: Path):
    """Découpe l'audio en WAV 16 kHz mono. Renvoie la liste des chemins."""
    dossier.mkdir(parents=True, exist_ok=True)
    total = duree_media(str(audio))
    if total <= 0:
        raise SystemExit(f"Durée illisible pour {audio}")
    n = int(total // DUREE_MORCEAU) + (1 if total % DUREE_MORCEAU else 0)
    chemins = []
    for k in range(n):
        c = dossier / f"morceau_{k:03d}.wav"
        if not c.exists():
            subprocess.run(
                ['ffmpeg', '-nostdin', '-y', '-hide_banner', '-loglevel',
                 'error', '-ss', f'{k * DUREE_MORCEAU:.3f}', '-i', str(audio),
                 '-t', f'{DUREE_MORCEAU:.3f}', '-ar', '16000', '-ac', '1',
                 '-c:a', 'pcm_s16le', str(c)],
                check=True)
        chemins.append(c)
    return chemins, total


def transcrire_un(model, morceau: Path, offset: float, multilingual: bool):
    """Transcrit un morceau -> (mots, segments) avec temps ABSOLUS."""
    kwargs = dict(language=None, word_timestamps=True, vad_filter=True,
                  beam_size=1, condition_on_previous_text=False)
    if multilingual:
        kwargs['multilingual'] = True
    try:
        segments, info = model.transcribe(str(morceau), **kwargs)
    except TypeError:                      # vieille version sans multilingual
        kwargs.pop('multilingual', None)
        segments, info = model.transcribe(str(morceau), **kwargs)

    mots, segs = [], []
    for seg in segments:
        langue = getattr(seg, 'language', None) or info.language
        proba = getattr(seg, 'language_probability', None)
        segs.append({'debut': round(seg.start + offset, 3),
                     'fin': round(seg.end + offset, 3),
                     'langue': langue,
                     'texte': (seg.text or '').strip()})
        for wd in (seg.words or []):
            mot = (wd.word or '').strip()
            if mot:
                mots.append({'mot': mot,
                             'debut': round(wd.start + offset, 3),
                             'fin': round(wd.end + offset, 3),
                             'langue': langue})
    return mots, segs


def main():
    ap = argparse.ArgumentParser(
        description="Transcription Whisper multilingue par morceaux (étape 2)")
    ap.add_argument('--config', default='config.json')
    ap.add_argument('--dars', required=True)
    ap.add_argument('--audio', default=None)
    ap.add_argument('--modele', default=None)
    ap.add_argument('--calcul', default=None)
    ap.add_argument('--budget', type=float, default=BUDGET,
                    help="budget de traitement par invocation (s)")
    ap.add_argument('--travail', default=None)
    args = ap.parse_args()

    cfg = charger_config(args.config)
    dars = cfg['darses'][args.dars]
    audio = Path(args.audio or dars['audio'])
    if not audio.is_absolute():
        audio = chemin_projet(cfg, audio)
    travail = chemin_projet(cfg, args.travail or cfg.get('travail', 'travail'))
    w = cfg.get('whisper', {})
    modele = args.modele or w.get('modele', 'small')
    calcul = args.calcul or w.get('calcul', 'int8')
    multilingual = bool(w.get('multilingual', True))

    dossier = Path(travail) / args.dars
    cache = dossier / 'morceaux'
    print(f"audio : {audio}")

    # ---- 1. découpage (idempotent) --------------------------------------
    morceaux, total = preparer_morceaux(audio, cache)
    print(f"{len(morceaux)} morceaux de {DUREE_MORCEAU:.0f} s "
          f"(durée totale {total:.0f} s = {total / 60:.1f} min)")

    # ---- 2. transcription avec reprise -----------------------------------
    from faster_whisper import WhisperModel
    t0 = time.time()
    model = WhisperModel(modele, device='cpu', compute_type=calcul)
    print(f"modèle « {modele} » ({calcul}) chargé en {time.time() - t0:.0f} s")

    faits = 0
    for k, morceau in enumerate(morceaux):
        dest = cache / f"morceau_{k:03d}.json"
        if dest.exists():
            faits += 1
            continue
        offset = k * DUREE_MORCEAU
        t1 = time.time()
        mots, segs = transcrire_un(model, morceau, offset, multilingual)
        sauver_json(dest, {'mots': mots, 'segments': segs})
        faits += 1
        extrait = ' '.join(m['mot'] for m in mots[:8])
        langues = sorted({s['langue'] for s in segs if s.get('langue')})
        print(f"  morceau {k + 1}/{len(morceaux)} : {len(mots)} mots "
              f"en {time.time() - t1:.0f}s | langues: {','.join(langues)} "
              f"| « {extrait} »")
        if time.time() - t0 > args.budget:
            print(f"⏸ budget d'invocation atteint — relancez la commande "
                  f"({faits}/{len(morceaux)} morceaux prêts)")
            return

    # ---- 3. fusion --------------------------------------------------------
    mots, segs = [], []
    for k in range(len(morceaux)):
        d = charger_cache(cache / f"morceau_{k:03d}.json")
        mots += d['mots']
        segs += d['segments']
    mots.sort(key=lambda m: m['debut'])
    segs.sort(key=lambda s: s['debut'])
    langues = sorted({m.get('langue') for m in mots if m.get('langue')})
    sortie = {'dars': args.dars, 'audio': str(audio), 'modele': modele,
              'duree': round(total, 3), 'langues': langues,
              'mots': mots, 'segments': segs}
    chemin = dossier / 'transcription.json'
    sauver_json(chemin, sortie)

    n_ar = sum(1 for m in mots if (m.get('langue') or '').startswith('ar'))
    print(f"OK -> {chemin}")
    print(f"   {len(mots)} mots horodatés | langues : "
          f"{', '.join(langues)} | mots étiquetés ar : {n_ar}")


def charger_cache(chemin):
    import json
    with open(chemin, 'r', encoding='utf-8') as f:
        return json.load(f)


if __name__ == '__main__':
    main()
