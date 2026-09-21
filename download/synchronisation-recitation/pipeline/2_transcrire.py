#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÉTAPE 2 — Transcription Whisper avec timestamps MOT par MOT
============================================================
Transcrit l'audio du cheikh (langue arabe) et sort chaque mot reconnu avec
son intervalle de temps [début, fin] en secondes.

IMPORTANT : cette transcription n'est qu'un «échafaudage temporel».
Le texte définitif reste celui du PDF (étape 1) ; l'étape 3 aligne les deux.

Usage :
  python 2_transcrire.py --audio demo/audio.mp3 --modele small \
                         --sortie demo/transcription.json

Modèles : tiny < base < small < medium < large-v3
  (plus précis = plus lent ; « small » convient pour tester,
   « medium » ou « large-v3 » recommandés en production)
Premier lancement : le modèle se télécharge depuis Hugging Face.
"""
import argparse
import json

from faster_whisper import WhisperModel


def main():
    ap = argparse.ArgumentParser(description="Transcription Whisper + timestamps mots")
    ap.add_argument("--audio", required=True, help="fichier audio (mp3/wav/m4a...)")
    ap.add_argument("--sortie", required=True, help="JSON de sortie (transcription.json)")
    ap.add_argument("--modele", default="small",
                    help="tiny | base | small | medium | large-v3 (défaut: small)")
    ap.add_argument("--langue", default="ar", help="code langue (défaut: ar)")
    ap.add_argument("--beam", type=int, default=5, help="beam size (défaut: 5)")
    args = ap.parse_args()

    print(f"Chargement du modèle « {args.modele} » (téléchargement au 1er lancement)...")
    model = WhisperModel(args.modele, device="cpu", compute_type="int8")

    print(f"Transcription de {args.audio} ...")
    segments, info = model.transcribe(
        args.audio,
        language=args.langue,
        word_timestamps=True,     # <- la clé : un timestamp par mot
        vad_filter=True,          # ignore les silences
        beam_size=args.beam,
    )

    mots = []
    for seg in segments:
        for w in (seg.words or []):
            t = w.word.strip()
            if t:
                mots.append({"mot": t,
                             "debut": round(w.start, 3),
                             "fin": round(w.end, 3)})

    out = {
        "audio": args.audio,
        "modele": args.modele,
        "langue": info.language,
        "langue_prob": round(info.language_probability, 3),
        "duree": round(info.duration, 3),
        "nb_mots": len(mots),
        "mots": mots,
    }
    with open(args.sortie, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print(f"✔ {len(mots)} mots horodatés sur {info.duration:.1f}s "
          f"(langue: {info.language} {info.language_probability:.0%})")
    print(f"→ {args.sortie}")
    if mots[:6]:
        apercu = " | ".join(f"{m['mot']}[{m['debut']:.2f}]" for m in mots[:6])
        print(f"  aperçu : {apercu} ...")


if __name__ == "__main__":
    main()
