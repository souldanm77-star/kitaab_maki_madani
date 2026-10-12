#!/usr/bin/env python3
"""
lancer_darsi.py — détection automatique + rendu des vidéos Darsi
=================================================================
Placez ce fichier dans le MÊME dossier que darsi_video.py, puis lancez :

    python lancer_darsi.py

Il détecte tout seul :
  * le PDF du livre   (de préférence celui qui contient « livre » dans son nom)
  * tous les audios   (.mpeg .mp3 .wav .m4a .ogg .flac .aac), triés par numéro
Puis, pour chaque audio, il crée un dossier  dars1, dars2…, y met l'audio et le
PDF, et lance darsi_video.py avec le surlignage mot à mot.

Options utiles :
    python lancer_darsi.py --liste              # affiche ce qui est détecté, sans rien lancer
    python lancer_darsi.py --seulement 1        # ne traite que le dars 1 (ou: --seulement 1 3)
    python lancer_darsi.py --modele medium      # small (défaut, rapide) | medium | large-v3 (précis, lent)
    python lancer_darsi.py --refaire            # refait même si la vidéo existe déjà
    python lancer_darsi.py --dossier "D:\\autre\\dossier"   # cherche ailleurs
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

EXT_AUDIO = {".mpeg", ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}
# Les fichiers audio « darsi-2 » et « Darsi-3 » sont croisés (prouvé par le contenu : l'audio
# nommé 3 lit les pages 6-13, qui suivent le dars 1 ; l'audio nommé 2 lit les pages 14-17).
# Numéro de LEÇON dans l'ordre du cours  <-  numéro dans le nom du fichier audio.
ECHANGE_COURS = {2: 3, 3: 2}
IGNORER = {"sortie", "travail", "travail_darsi", "travail_demo", "demo", "images",
           "__pycache__", ".git", "node_modules", "conformite"}


def est_dossier_genere(p: Path) -> bool:
    """dars1, dars2… = dossiers créés par ce script : on ne les rescanne pas."""
    return bool(re.fullmatch(r"dars\d+", p.name, re.I))


def parcourir(base: Path, profondeur: int = 3):
    """Liste les fichiers de base et de ses sous-dossiers (profondeur limitée)."""
    res = []

    def rec(d: Path, niv: int):
        try:
            entrees = sorted(d.iterdir())
        except OSError:
            return
        for e in entrees:
            if e.is_dir():
                if niv < profondeur and e.name.lower() not in IGNORER and not est_dossier_genere(e):
                    rec(e, niv + 1)
            else:
                res.append(e)

    rec(base, 0)
    return res


MOTIF_DARS = re.compile(r"dars[i]?\s*[-_ ]*\s*(\d+)(?!\d)", re.I)


def numero(p: Path):
    """Numéro du darsi = chiffres juste après « dars » / « darsi » (ex. « Audio darsi-3 » -> 3).
    Retourne None si le nom ne ressemble pas à un darsi (extrait_test, *_16k_mono…)."""
    m = MOTIF_DARS.search(p.stem)
    return int(m.group(1)) if m else None


def detecter(base: Path, tout: bool = False):
    fichiers = parcourir(base)
    pdfs = [f for f in fichiers if f.suffix.lower() == ".pdf"]
    pdfs.sort(key=lambda f: (0 if "livre" in f.name.lower() else 1, len(f.parts)))
    audios = [f for f in fichiers if f.suffix.lower() in EXT_AUDIO]
    retenus, ignores = {}, []
    # à numéro égal on préfère l'original (.mpeg/.mp3…) au .wav converti, puis le nom le plus court
    audios.sort(key=lambda f: (f.suffix.lower() == ".wav", len(f.name), f.name.lower()))
    for i, a in enumerate(audios, 1):
        n = numero(a)
        if n is None:
            if tout:
                n = 100 + i
            else:
                ignores.append((a, "nom sans « darsi-N »"))
                continue
        if n in retenus:
            ignores.append((a, "doublon du dars%d (%s)" % (n, retenus[n].name)))
            continue
        retenus[n] = a
    return (pdfs[0] if pdfs else None), sorted(retenus.items()), ignores


def verifier_dependances_python():
    """Retourne la liste des paquets pip manquants."""
    manque = []
    for module, paquet in (("faster_whisper", "faster-whisper"), ("rapidfuzz", "rapidfuzz")):
        try:
            __import__(module)
        except ImportError:
            manque.append(paquet)
    try:
        __import__("pymupdf")
    except ImportError:
        try:
            __import__("fitz")
        except ImportError:
            manque.append("PyMuPDF")
    return manque


def copier(src: Path, dst: Path):
    if dst.exists() and dst.stat().st_size == src.stat().st_size:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dossier", help="dossier à scanner (défaut : celui de ce script)")
    ap.add_argument("--seulement", type=int, nargs="+", help="numéros de darsi à traiter")
    ap.add_argument("--modele", default="small", help="small | medium | large-v3")
    ap.add_argument("--res", type=int, default=1080)
    ap.add_argument("--refaire", action="store_true")
    ap.add_argument("--liste", action="store_true", help="affiche la détection puis s'arrête")
    ap.add_argument("--installer", action="store_true",
                    help="installe automatiquement faster-whisper, PyMuPDF, rapidfuzz s'ils manquent")
    ap.add_argument("--sans-echange", action="store_true",
                    help="désactive l'échange darsi-2 <-> darsi-3 (numéro de leçon = numéro du fichier)")
    ap.add_argument("--tout", action="store_true",
                    help="traite aussi les audios dont le nom ne contient pas « darsi-N »")
    a = ap.parse_args()

    base = Path(a.dossier).resolve() if a.dossier else Path(__file__).resolve().parent
    script = base / "darsi_video.py"
    if not script.exists():
        script = Path(__file__).resolve().parent / "darsi_video.py"

    pdf, audios, ignores = detecter(base, a.tout)
    if not a.sans_echange:
        audios = sorted(((ECHANGE_COURS.get(n, n), f) for n, f in audios), key=lambda x: x[0])

    print("Dossier scanné :", base)
    print("Livre (PDF)    :", pdf if pdf else "!!! AUCUN PDF TROUVÉ !!!")
    if not audios:
        print("Audios         : !!! AUCUN AUDIO TROUVÉ (.mpeg .mp3 .wav .m4a …) !!!")
    for n, f in audios:
        print("  dars%-3d <- %s  (%.0f Mo)" % (n, f.name, f.stat().st_size / 1e6))
    if not a.sans_echange and any(n != numero(f) for n, f in audios if numero(f) is not None):
        print("  (leçons 2 et 3 échangées : l'audio « darsi-3 » est la 2e leçon du cours. "
              "Option --sans-echange pour désactiver)")
    for f, raison in ignores:
        print("  (ignoré) %s : %s" % (f.name, raison))
    if a.liste:
        return 0
    if not pdf or not audios:
        print("\nImpossible de continuer : il faut au moins 1 PDF et 1 audio.")
        return 1
    if not script.exists():
        print("\ndarsi_video.py est introuvable. Mettez ce fichier à côté de darsi_video.py.")
        return 1

    manque = verifier_dependances_python()
    if manque:
        cmd_pip = [sys.executable, "-m", "pip", "install"] + manque
        if a.installer:
            print("\nInstallation des paquets manquants :", " ".join(manque))
            if subprocess.call(cmd_pip) != 0:
                print("L'installation a échoué. Lancez à la main :\n  " + " ".join(cmd_pip))
                return 1
        else:
            print("\nPaquets Python manquants :", ", ".join(manque))
            print("Installez-les avec :\n  " + " ".join(cmd_pip))
            print("ou relancez : python lancer_darsi.py --installer")
            return 1

    echecs = []
    for n, audio in audios:
        if a.seulement and n not in a.seulement:
            continue
        dest = base / ("dars%d" % n)
        video = dest / ("dars%d.mp4" % n)
        if video.exists() and not a.refaire:
            print("\n[dars%d] déjà fait -> %s (utilisez --refaire pour recommencer)" % (n, video))
            continue
        print("\n" + "=" * 70 + "\n[dars%d] préparation…" % n)
        copier(audio, dest / audio.name)
        copier(pdf, dest / pdf.name)
        cmd = [sys.executable, str(script), "--dossier", str(dest),
               "--audio", audio.name, "--pdf", pdf.name,
               "--surligner", "--modele", a.modele, "--res", str(a.res),
               "--sortie", str(video)]
        print("[dars%d] lancement :" % n, " ".join('"%s"' % c if " " in c else c for c in cmd))
        if subprocess.call(cmd) != 0:
            echecs.append(n)
            print("[dars%d] ECHEC (voir les messages ci-dessus)" % n)
        else:
            print("[dars%d] TERMINÉ -> %s" % (n, video))

    print("\n" + "=" * 70)
    print("Échecs :", echecs if echecs else "aucun")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
