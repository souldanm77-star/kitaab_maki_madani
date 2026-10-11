#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÉTAPE 2 v2 — Transcription Whisper par TRANCHES (anti-OOM)
===========================================================
L'audio long (80 min) décodé d'un bloc fait exploser la RAM (OOM kill
sur machine 3 Go). Ici :
  1. ffmpeg convertit l'audio en WAV 16 kHz mono (1 passe, sur disque).
  2. Le WAV est lu TRANCHE par TRANCHE (10 min + 2 s de recouvrement),
     chaque tranche est transrite indépendamment (modèle chargé UNE fois).
  3. Les timestamps sont décalés de l'origine de la tranche ; les mots
     dupliqués sur les coutures (recouvrement) sont dédupliqués.

Sortie : même format JSON que 2_transcrire.py (compatible 3_aligner.py).
"""
import argparse
import json
import os
import subprocess
import sys
import wave

import numpy as np
from faster_whisper import WhisperModel

TANCHE = 600.0        # secondes par tranche
RECOUVRE = 2.0        # secondes de contexte repris au début de chaque tranche


def vers_wav(audio, wav):
    """Convertit en WAV 16 kHz mono PCM (léger à lire par tranches)."""
    if os.path.exists(wav) and os.path.getsize(wav) > 44:
        return
    print(f"Conversion ffmpeg → {wav} ...", flush=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", audio,
                    "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav],
                   check=True)


def duree_wav(wav):
    with wave.open(wav, "rb") as w:
        return w.getnframes() / w.getframerate()


def lire_tranche(wav, debut, fin):
    """Lit [debut, fin) du WAV → float32 [-1,1] (mono 16 kHz)."""
    with wave.open(wav, "rb") as w:
        fr = w.getframerate()
        i0 = max(0, int(debut * fr))
        i1 = min(w.getnframes(), int(fin * fr))
        w.setpos(i0)
        data = w.readframes(i1 - i0)
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def normaliser_mot(t):
    return ''.join(ch for ch in t.strip() if not ch.isspace())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--sortie", required=True)
    ap.add_argument("--modele", default="small")
    ap.add_argument("--langue", default="ar")
    ap.add_argument("--beam", type=int, default=1)
    ap.add_argument("--tranche", type=float, default=TANCHE)
    ap.add_argument("--reprendre", action="store_true",
                    help="reprend depuis la sauvegarde partielle")
    args = ap.parse_args()

    partiel = args.sortie.replace(".json", "_partiel.json")
    deja = []
    if args.reprendre and os.path.exists(partiel):
        deja = json.load(open(partiel, encoding="utf-8"))["mots"]
        print(f"Reprise : {len(deja)} mots déjà transcrits", flush=True)

    wav = os.path.join(os.path.dirname(args.sortie), "audio_16k.wav")
    vers_wav(args.audio, wav)
    duree = duree_wav(wav)
    print(f"Durée totale : {duree/60:.1f} min → {int(-(-duree // args.tranche))} tranches",
          flush=True)

    print(f"Chargement du modèle « {args.modele} »...", flush=True)
    model = WhisperModel(args.modele, device="cpu", compute_type="int8",
                         cpu_threads=2)

    tous = list(deja)
    debut = (tous[-1]["fin"] if tous else 0.0)
    # on repart au début de la tranche suivante non traitée
    debut = (int(debut // args.tranche) + 1) * args.tranche \
        if tous else 0.0
    n_tranche = int(debut // args.tranche)
    while debut < duree - 0.5:
        n_tranche += 1
        fin = min(debut + args.tranche, duree)
        # contexte de recouvrement : aide Whisper sur les mots coupés,
        # mais on ne GARDE que les mots commençant dans [debut, fin)
        t0 = max(0.0, debut - RECOUVRE) if debut > 0 else 0.0
        audio = lire_tranche(wav, t0, fin)
        print(f"— Tranche {n_tranche} [{debut:.0f} → {fin:.0f}]s ...",
              flush=True)
        segments, info = model.transcribe(
            audio, language=args.langue, word_timestamps=True,
            vad_filter=True, beam_size=args.beam,
            condition_on_previous_text=False,
            vad_parameters={"max_speech_duration_s": 28.0,
                            "min_silence_duration_ms": 400})
        nb = 0
        for seg in segments:
            for w in (seg.words or []):
                t = normaliser_mot(w.word)
                if not t:
                    continue
                d = w.start + t0
                f = w.end + t0
                if d < debut - 0.05:          # mot du recouvrement : ignoré
                    continue
                tous.append({"mot": t, "debut": round(d, 3),
                             "fin": round(f, 3)})
                nb += 1
        print(f"   {nb} mots (cumul {len(tous)})", flush=True)
        # sauvegarde partielle après CHAQUE tranche (anti-OOM-loss)
        with open(partiel, "w", encoding="utf-8") as f:
            json.dump({"mots": tous}, f, ensure_ascii=False)
        debut = fin

    # déduplication des coutures (même mot, quasi même temps)
    nettoyes = []
    for m in tous:
        if nettoyes:
            p = nettoyes[-1]
            if (m["mot"] == p["mot"] and abs(m["debut"] - p["debut"]) < 0.6):
                p["fin"] = max(p["fin"], m["fin"])
                continue
        nettoyes.append(m)

    out = {"audio": args.audio, "modele": args.modele,
           "langue": args.langue, "duree": round(duree, 3),
           "nb_mots": len(nettoyes), "mots": nettoyes}
    with open(args.sortie, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"✔ {len(nettoyes)} mots horodatés → {args.sortie}", flush=True)


if __name__ == "__main__":
    main()
