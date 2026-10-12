#!/usr/bin/env python3
"""
generer_videos.py — produit les vidéos de SURLIGNAGE (sans aucune transcription)
================================================================================
Les horodatages de chaque mot (travail_darsi/dars*/timing.json) sont déjà calculés
et stockés dans le dépôt. Ce script fabrique directement les vidéos :
Cheikh à gauche, page du livre à droite, mot surligné en jaune pendant la lecture
(rien pendant le somali ni les commentaires arabes hors livre).

Usage (depuis le dossier  download/video-recitation) :

    python generer_videos.py --test            # test rapide de chaque dars (quelques minutes)
    python generer_videos.py                   # les 4 dars complets
    python generer_videos.py --dars 1          # un seul dars
    python generer_videos.py --dars 1 3 --sortie "D:\\mes videos"

Prérequis : Python 3, ffmpeg dans le PATH, et  pip install pillow
Durée de rendu : environ la moitié de la durée de l'audio (80 min d'audio ≈ 40 min).
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
CONFIG = ICI / "config_darsi.json"
TRAVAIL = "travail_darsi"
PIPELINE = ICI / "pipeline" / "4_video.py"


def verifier():
    """Retourne la liste des problèmes bloquants."""
    pb = []
    if shutil.which("ffmpeg") is None:
        pb.append("ffmpeg est introuvable dans le PATH (installez-le : https://ffmpeg.org).")
    try:
        import PIL  # noqa: F401
    except ImportError:
        pb.append('Pillow manquant :  python -m pip install pillow')
    for f in (CONFIG, PIPELINE, ICI / TRAVAIL / "pages.json"):
        if not f.exists():
            pb.append("Fichier introuvable : %s (lancez le script depuis le dépôt complet, "
                      "dossier download/video-recitation)." % f)
    return pb


def premiere_lecture(timing_json):
    """Seconde du premier mot du livre réellement lu (états « whisper » / « interpole »)."""
    t = json.loads(Path(timing_json).read_text(encoding="utf-8"))
    mots = t["mots"] if isinstance(t, dict) else t
    debuts = [m["debut"] for m in mots
              if m.get("etat") in ("whisper", "interpole") and m.get("debut") is not None]
    return min(debuts) if debuts else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dars", type=int, nargs="+", default=[1, 2, 3, 4], help="numéros (défaut : 1 2 3 4)")
    ap.add_argument("--sortie", default=str(ICI / "videos"), help="dossier de sortie (défaut : ./videos)")
    ap.add_argument("--test", action="store_true", help="test rapide : rend jusqu'à 30 s après le début de la première lecture du livre")
    ap.add_argument("--max", type=float, default=None, help="ne rend que les N premières secondes")
    a = ap.parse_args()

    pb = verifier()
    if pb:
        print("Impossible de continuer :")
        for p in pb:
            print("  -", p)
        return 1

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    sortie = Path(a.sortie).resolve()
    sortie.mkdir(parents=True, exist_ok=True)
    limite_manuelle = a.max

    echecs = []
    for n in a.dars:
        cle = "dars%d" % n
        if cle not in cfg.get("darses", {}):
            print("[%s] inconnu dans config_darsi.json, ignoré" % cle)
            continue
        timing = ICI / TRAVAIL / cle / "timing.json"
        audio = ICI / cfg["darses"][cle]["audio"]
        manque = [str(p) for p in (timing, audio) if not p.exists()]
        if manque:
            print("[%s] fichiers manquants : %s" % (cle, ", ".join(manque)))
            echecs.append(n)
            continue
        limite = limite_manuelle
        if a.test:                       # 30 s APRÈS le début de la première lecture du livre
            debut = premiere_lecture(timing)
            limite = (debut or 0.0) + 30.0
            print("[%s] test : première lecture du livre à %.0f s -> rendu des %.0f premières secondes"
                  % (cle, debut or 0, limite))
        suffixe = "_test" if a.test else ("_%ds" % int(limite) if limite else "")
        video = sortie / ("Darsi-%d%s.mp4" % (n, suffixe))
        cmd = [sys.executable, str(PIPELINE), "--config", str(CONFIG), "--dars", cle,
               "--travail", TRAVAIL, "--sortie", str(video)]
        if limite:
            cmd += ["--max", str(limite)]
        print("\n" + "=" * 70 + "\n[%s] rendu -> %s" % (cle, video))
        if subprocess.call(cmd, cwd=str(ICI)) != 0 or not video.exists():
            print("[%s] ECHEC (voir les messages ci-dessus)" % cle)
            echecs.append(n)
        else:
            print("[%s] TERMINÉ : %s (%.0f Mo)" % (cle, video, video.stat().st_size / 1e6))

    print("\n" + "=" * 70)
    print("Dossier des vidéos :", sortie)
    print("Échecs :", echecs if echecs else "aucun")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
