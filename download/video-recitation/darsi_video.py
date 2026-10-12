#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 darsi_video.py — Création automatique d'une vidéo « Darsi » synchronisée
================================================================================

QUE FAIT CE SCRIPT ?
--------------------
À partir de :
  (1) l'audio du Sheikh (récitation arabe + explications en langue locale),
  (2) les images des pages du Darsi (page1.jpg, page2.jpg, …) OU le PDF du livre,

il produit une vidéo (.mp4 ou .mpg) où :
  - la page en cours de lecture est affichée au bon moment ;
  - si le Sheikh REVIENT EN ARRIÈRE et répète un passage, la vidéo réaffiche
    automatiquement la page correspondante (détection des répétitions) ;
  - avec l'option --surligner (nécessite le PDF) : le mot exact en cours de
    récitation est surligné en jaune, mot par mot, et AUCUN surlignage n'est
    fait pendant les explications hors livre (règle des « 3 états »).

UTILISATION RAPIDE
------------------
  python3 darsi_video.py --dossier mon_darsi --langue ar --surligner

Voir README_DARSI.md : installation, organisation des fichiers, algorithme.

ÉTAPES INTERNES
---------------
  1. Transcription Whisper (faster-whisper) avec horodatage MOT par MOT
  2. Alignement transcription <-> texte de référence :
       ancres n-grammes -> Needleman-Wunsch local -> interpolation
     (c'est là que les répétitions / retours en arrière sont détectés)
  3. Association de chaque passage à sa page + séquence d'affichage
  4. Rendu vidéo avec FFmpeg (images + audio + surlignage ASS optionnel)
================================================================================
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ============================================================================
# SECTION 0 — Dépendances (vérification avec messages clairs)
# ============================================================================
# Obligatoires  : faster-whisper (transcription), ffmpeg/ffprobe (audio/vidéo)
# Optionnelles  : pdfplumber (lecture du PDF, requise pour --surligner),
#                 rapidfuzz (similarité rapide) — sinon difflib est utilisé.

def verifier_dependances(necessite_pdf: bool):
    """Arrête le script avec un message clair s'il manque une dépendance."""
    manquantes = []
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        manquantes.append("faster-whisper   ->  python3 -m pip install faster-whisper")
    if necessite_pdf and fitz is None:
        manquantes.append("PyMuPDF         ->  python3 -m pip install PyMuPDF")
    for outil in ("ffmpeg", "ffprobe"):
        if not shutil.which(outil):
            manquantes.append(outil + "  ->  installer ffmpeg (ex: apt install ffmpeg)")
    if manquantes:
        print("ERREUR : dépendances manquantes :")
        for m in manquantes:
            print("   - " + m)
        sys.exit(1)


# PyMuPDF : lecture des PDF (texte + rendu des pages en images)
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

# Similarité textuelle : rapidfuzz si disponible (rapide), sinon difflib.
try:
    from rapidfuzz import fuzz as _fz

    class Fuzz:
        @staticmethod
        def ratio(a: str, b: str) -> float:
            return _fz.ratio(a, b)
except ImportError:
    from difflib import SequenceMatcher

    class Fuzz:
        @staticmethod
        def ratio(a: str, b: str) -> float:
            return SequenceMatcher(None, a, b).ratio() * 100.0


# ============================================================================
# SECTION 1 — Normalisation du texte (arabe et latin)
# ============================================================================
# Pour COMPARER deux mots, on retire tout ce qui ne change pas le sens :
#   - les diacritiques arabes (fatha, damma, kasra, chadda, tanwin…)
#   - les variantes d'hamza (أ إ آ -> ا), taa marbouta (ة -> ه), alif maqsura…
#   - la casse pour le texte latin.
# La même normalisation est appliquée à la transcription ET au texte de
# référence : c'est ce qui rend le matching robuste aux fautes de Whisper.

RE_DIACRITIQUES = re.compile(r"[\u064B-\u065F\u0670\u0640\u06D6-\u06ED\u08F0-\u08F3]")
TABLE_NORMALISATION = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي",
})
RE_MOTS = re.compile(r"[\w\u0600-\u06FF\u0750-\u077F]+", re.UNICODE)


def normaliser(texte: str) -> str:
    """Forme canonique d'un mot pour la comparaison."""
    if not texte:
        return ""
    t = RE_DIACRITIQUES.sub("", texte)
    t = t.translate(TABLE_NORMALISATION)
    return t.lower().strip()


def decouper_mots(texte: str):
    """Découpe un texte en mots (sans ponctuation)."""
    return RE_MOTS.findall(texte or "")


# ============================================================================
# SECTION 2 — Outils : exécution de commandes, audio, PDF -> images
# ============================================================================

def lancer(cmd, cwd: str = None) -> str:
    """Exécute une commande externe et renvoie sa sortie (erreur claire sinon)."""
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("Échec de : " + " ".join(cmd) +
                           "\n" + (r.stderr or r.stdout)[-2000:])
    return r.stdout


def duree_audio(chemin: str) -> float:
    """Durée (en secondes) d'un fichier audio via ffprobe."""
    out = lancer(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                  "-of", "default=noprint_wrappers=1:nokey=1", chemin])
    return float(out.strip())


def decouper_audio(chemin_audio: str, dossier_morceaux: Path, duree_morceau: int = 480):
    """Découpe l'audio en morceaux WAV 16 kHz mono (format requis par Whisper).
    Renvoie la liste [(chemin_wav, décalage_en_secondes)].
    Les morceaux déjà présents ne sont PAS refaits (reprise après interruption)."""
    dossier_morceaux.mkdir(parents=True, exist_ok=True)
    total = duree_audio(chemin_audio)
    morceaux, k, t = [], 0, 0.0
    while t < total - 0.5:
        dest = dossier_morceaux / ("morceau_%02d.wav" % k)
        if not dest.exists():
            lancer(["ffmpeg", "-nostdin", "-y", "-ss", "%.2f" % t, "-t", str(duree_morceau),
                    "-i", chemin_audio, "-ar", "16000", "-ac", "1", str(dest)])
        morceaux.append((dest, t))
        t += duree_morceau
        k += 1
    return morceaux


def pdf_vers_images(chemin_pdf: str, dossier_images: Path, resolution: int = 150):
    """Rend chaque page du PDF en image pageN.jpg (PyMuPDF).
    Renvoie {numéro_de_page: chemin_image}."""
    dossier_images.mkdir(parents=True, exist_ok=True)
    import fitz
    images = {}
    with fitz.open(chemin_pdf) as doc:
        for pno in range(doc.page_count):
            pix = doc[pno].get_pixmap(dpi=resolution)
            dest = dossier_images / ("page-%d.jpg" % (pno + 1))
            pix.save(str(dest))
            images[pno + 1] = str(dest.resolve())
    return images


def charger_images_existantes(dossier_images: Path):
    """Cherche page1.jpg / page01.jpg / page1.png… et renvoie {numéro: chemin}."""
    images = {}
    if not dossier_images.exists():
        return images
    for f in sorted(dossier_images.iterdir()):
        m = re.match(r"page(\d+)\.(jpg|jpeg|png)$", f.name.lower())
        if m:
            n = int(m.group(1))
            if n not in images:
                images[n] = str(f.resolve())
    return images

# ============================================================================
# SECTION 3 — Transcription Whisper avec horodatage MOT PAR MOT
# ============================================================================
# faster-whisper est une réimplémentation optimisée d'OpenAI Whisper
# (4x plus rapide sur CPU, mêmes résultats) : word_timestamps=True renvoie
# le temps de début/fin de CHAQUE mot.
# L'audio est traité par morceaux de 480 s ; chaque morceau transcrit est mis
# en cache (travail/morceaux/morceau_XX.json) : si le script est relancé,
# les morceaux déjà faits ne sont PAS recalculés (reprise automatique).

def transcrire_audio(chemin_audio: str, dossier_travail: Path,
                     modele_nom: str = "small", langue: str = None,
                     duree_morceau: int = 480):
    """Transcrit l'audio et renvoie une liste de mots :
    [{"texte": str, "debut": float, "fin": float, "norm": str}, ...]"""
    from faster_whisper import WhisperModel
    morceaux = decouper_audio(chemin_audio, dossier_travail / "morceaux", duree_morceau)

    # 1) charger les caches existants, lister ce qui reste à faire
    a_faire = []
    for chemin_wav, decalage in morceaux:
        cache = dossier_travail / "morceaux" / (chemin_wav.stem + ".json")
        if not cache.exists():
            a_faire.append((chemin_wav, decalage, cache))

    # 2) transcrire uniquement les morceaux manquants
    modele = None
    for chemin_wav, decalage, cache in a_faire:
        if modele is None:
            print("  chargement du modèle Whisper '%s' (premier lancement : téléchargement)…" % modele_nom)
            modele = WhisperModel(modele_nom, device="cpu", compute_type="int8")
        print("  transcription de %s (décalage %.0f s)…" % (chemin_wav.name, decalage))
        t0 = time.time()
        segments, _info = modele.transcribe(
            str(chemin_wav), word_timestamps=True, language=langue, vad_filter=True)
        mots = []
        for seg in segments:
            for w in (seg.words or []):
                txt = (w.word or "").strip()
                if not txt:
                    continue
                mots.append({"texte": txt,
                             "debut": round(w.start + decalage, 3),
                             "fin": round(w.end + decalage, 3)})
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(mots, f, ensure_ascii=False)
        print("    %d mots en %.0f s" % (len(mots), time.time() - t0))

    # 3) fusionner tous les morceaux (temps absolus dès la transcription)
    tous_les_mots = []
    for chemin_wav, _decalage in morceaux:
        cache = dossier_travail / "morceaux" / (chemin_wav.stem + ".json")
        with open(cache, encoding="utf-8") as f:
            tous_les_mots.extend(json.load(f))
    tous_les_mots.sort(key=lambda m: m["debut"])
    for m in tous_les_mots:
        m["norm"] = normaliser(m["texte"])
    return tous_les_mots


# ============================================================================
# SECTION 4 — Texte de référence découpé par pages
# ============================================================================
# PRIORITÉ : si un PDF est fourni, il est la source UNIQUE et COHÉRENTE :
#   - texte de référence = mots extraits page par page (pdfplumber) ;
#   - coordonnées (x, y, largeur, hauteur) de chaque mot sur la page
#     -> rend possibles les rectangles jaunes de surlignage ;
#   - les images des pages sont générées si elles n'existent pas.
# SANS PDF : fichier .txt découpé par des séparateurs « === PAGE 2 === ».

class MotRef:
    """Un mot du texte de référence (+ sa position sur la page si PDF)."""
    __slots__ = ("texte", "norm", "page", "position",
                 "x", "y", "l", "h", "debut", "fin", "recite", "similarite")

    def __init__(self, texte, page, position, x=None, y=None, l=None, h=None):
        self.texte = texte
        self.norm = normaliser(texte)
        self.page = page
        self.position = position
        self.x, self.y, self.l, self.h = x, y, l, h   # coordonnées PDF (points)
        self.debut = None          # temps estimé après alignement
        self.fin = None
        self.recite = False        # prononcé par le Sheikh ?
        self.similarite = 0.0


def reference_depuis_pdf(chemin_pdf: str):
    """Extrait les mots de chaque page du PDF avec leurs coordonnées.
    MÉTHODE ROBUSTE pour l'arabe (les PDF sortent souvent les glyphes dans
    le désordre) :
      1. les CARACTÈRES sont collectés par PyMuPDF (rawdict) ;
      2. les lignes visuelles sont reconstruites (fusion des objets qui
         se chevauchent verticalement) ;
      3. dans chaque ligne, les lettres de base sont triées spatialement
         DE DROITE À GAUCHE (ordre de lecture arabe) ;
      4. les frontières de mots sont détectées par seuil d'Otsu sur les
         écarts horizontaux (les diacritiques ne participent jamais) ;
      5. les ligatures empilées (type لله) sont regroupées en ordre logique
         et les diacritiques rattachés au mot le plus proche.
    Renvoie (mots_par_page, tailles_pages) :
      mots_par_page = {page: [MotRef, ...]}   tailles_pages = {page: (w, h)}"""
    import fitz
    mots_par_page, tailles_pages = {}, {}
    with fitz.open(chemin_pdf) as doc:
        for pno in range(doc.page_count):
            page = doc[pno]
            num_page = pno + 1
            tailles_pages[num_page] = (float(page.rect.width), float(page.rect.height))
            liste = []
            for r in fusionner_en_rangees(grouper_caracteres(page)):
                for m in mots_de_rangee(r["chars"]):
                    liste.append(MotRef(
                        m["texte"], num_page, len(liste),
                        x=m["x0"], y=m["y0"], l=m["x1"] - m["x0"], h=m["y1"] - m["y0"]))
            mots_par_page[num_page] = liste
    return mots_par_page, tailles_pages


# --- Reconstruction des mots arabes depuis les caractères du PDF -----------

def grouper_caracteres(page):
    """Collecte les caractères de la page, groupés par objet 'ligne' du PDF."""
    d = page.get_text("rawdict",
                      flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES)
    groupes = []
    for bloc in d.get("blocks", []):
        if bloc.get("type") != 0:
            continue
        for line in bloc.get("lines", []):
            chars = []
            for span in line.get("spans", []):
                for ch in span.get("chars", []):
                    if ch["c"].strip():                      # ignore espaces
                        chars.append((ch["bbox"], ch["c"]))
            if chars:
                groupes.append(chars)
    return groupes


def fusionner_en_rangees(groupes, tol=0.5):
    """Fusionne les objets 'ligne' qui se chevauchent verticalement
    (certains PDFs émettent une ligne par mot) -> rangées visuelles."""
    groupes = sorted(groupes, key=lambda c: min(b[1] for b, _ in c))
    rangees = []
    for chars in groupes:
        y0 = min(b[1] for b, _ in chars)
        y1 = max(b[3] for b, _ in chars)
        placee = False
        for r in rangees:
            ov = min(r["y1"], y1) - max(r["y0"], y0)
            hh = min(r["y1"] - r["y0"], y1 - y0) or 1.0
            if ov > tol * hh:
                r["chars"] += chars
                r["y0"] = min(r["y0"], y0)
                r["y1"] = max(r["y1"], y1)
                placee = True
                break
        if not placee:
            rangees.append({"chars": list(chars), "y0": y0, "y1": y1})
    rangees.sort(key=lambda r: r["y0"])
    return rangees


def est_marque(c):
    """Diacritique / signe coranique (ne fait pas avancer la ligne de base)."""
    o = ord(c)
    return (0x0610 <= o <= 0x061A or 0x064B <= o <= 0x065F or
            o in (0x0670,) or 0x06D6 <= o <= 0x06ED)


def grouper_chevauchement(chars_triees):
    """Regroupe les glyphes dont les bbox se chevauchent fortement
    (ligatures empilées type لله) — l'ordre FLUX est conservé À
    L'INTÉRIEUR d'un groupe, restaurant l'ordre logique même si les
    x sont quasi égaux. À n'utiliser qu'À L'INTÉRIEUR d'un mot."""
    groupes = []
    for bbox, c in chars_triees:
        place = False
        if groupes:
            g = groupes[-1]
            gx0 = min(b[0] for b, _ in g)
            gx1 = max(b[2] for b, _ in g)
            ov = min(gx1, bbox[2]) - max(gx0, bbox[0])
            w = min(gx1 - gx0, bbox[2] - bbox[0])
            if w > 0 and ov > 0.45 * w:
                g.append((bbox, c))
                place = True
        if not place:
            groupes.append([(bbox, c)])
    return groupes


def seuil_otsu(gaps, largeur_med):
    """Seuil de séparation des mots : première séparation propre en parcourant
    les écarts croissants (bimodalité stricte : classe haute ≥ 1 pt et ≥ 2× la
    classe basse + 0,3). Sépare l'écart intra-mot (petit) de l'écart inter-mots
    (grand), même quand des trous de ponctuation bien plus grands existent."""
    pos = sorted(g for g in gaps if g > 0)
    fallback = max(1.0, 0.55 * largeur_med)
    if len(pos) < 3:
        return fallback
    for i in range(1, len(pos)):
        dessous, dessus = pos[:i], pos[i:]
        if min(dessus) >= 1.0 and min(dessus) >= 2.0 * max(dessous) + 0.3:
            return max(1.0, (max(dessous) + min(dessus)) / 2.0)
    return fallback


def mots_de_rangee(chars):
    """Reconstruit les mots d'une rangée :
      1. tri spatial RTL des LETTRES DE BASE (tie-break = ordre flux) ;
      2. frontières de mots par seuil d'Otsu sur les écarts entre lettres
         (les diacritiques ne participent JAMAIS aux frontières) ;
      3. à l'intérieur de chaque mot : regroupement des glyphes chevauchants
         (ligatures empilées) pour l'ordre logique ;
      4. les diacritiques sont rattachés au mot le plus proche."""
    base = [t for t in chars if not est_marque(t[1])]
    marques = [t for t in chars if est_marque(t[1])]
    base = sorted(base, key=lambda t: (-t[0][2], t[0][0]))
    if not base:
        return []

    larges = sorted(b[2] - b[0] for b, c in base if "\u0621" <= c <= "\u064A")
    med = larges[len(larges) // 2] if larges else 4.0

    gaps = [b1[0] - b2[2] for (b1, _c1), (b2, _c2) in zip(base, base[1:])]
    seuil = seuil_otsu(gaps, med)

    sacs = []                                # un sac = un mot en construction
    for t in base:
        if sacs and (sacs[-1]["x0"] - t[0][2]) <= seuil:
            s = sacs[-1]
            s["chars"].append(t)
            s["x0"] = min(s["x0"], t[0][0])
            s["x1"] = max(s["x1"], t[0][2])
            s["y0"] = min(s["y0"], t[0][1])
            s["y1"] = max(s["y1"], t[0][3])
        else:
            sacs.append({"chars": [t], "x0": t[0][0], "y0": t[0][1],
                         "x1": t[0][2], "y1": t[0][3]})

    mots = []
    for s in sacs:
        cs = sorted(s["chars"], key=lambda t: (-t[0][2], t[0][0]))
        groupes = grouper_chevauchement(cs)
        texte = "".join(c for _, c in [t for g in groupes for t in g])
        mots.append({"texte": texte, "x0": s["x0"], "y0": s["y0"],
                     "x1": s["x1"], "y1": s["y1"]})

    for bbox, c in marques:
        cx = (bbox[0] + bbox[2]) / 2.0
        best, best_d = None, None
        for m in mots:
            d = max(m["x0"] - cx, 0.0, cx - m["x1"])
            if best_d is None or d < best_d:
                best, best_d = m, d
        if best is not None and best_d <= med:
            best["texte"] += c
            best["x0"] = min(best["x0"], bbox[0])
            best["y0"] = min(best["y0"], bbox[1])
            best["x1"] = max(best["x1"], bbox[2])
            best["y1"] = max(best["y1"], bbox[3])
    return mots


def reference_depuis_txt(chemin_txt: str):
    """Lit un .txt découpé par des lignes « === PAGE 2 === ».
    Renvoie (mots_par_page, {}) — pas de coordonnées -> pas de surlignage fin."""
    mots_par_page = {}
    num_page = 1
    with open(chemin_txt, encoding="utf-8") as f:
        for ligne in f:
            m = re.match(r"\s*[=*\-]{2,}\s*PAGE\s*(\d+)\s*[=*\-]{2,}\s*$",
                         ligne, re.IGNORECASE)
            if m:
                num_page = int(m.group(1))
                continue
            for pos, w in enumerate(decouper_mots(ligne)):
                mots_par_page.setdefault(num_page, []).append(MotRef(w, num_page, pos))
    return mots_par_page, {}


def liste_plate(mots_par_page):
    """Tous les mots de référence dans l'ordre de lecture du livre."""
    mots = []
    for page in sorted(mots_par_page):
        mots.extend(mots_par_page[page])
    return mots

# ============================================================================
# SECTION 5 — ALGORITHME DE DÉTECTION DES RÉPÉTITIONS (le cœur du script)
# ============================================================================
# PROBLÈME : la transcription Whisper est imparfaite (mots mal reconnus, mots
# oubliés) et la lecture N'EST PAS linéaire : le Sheikh s'arrête, explique en
# langue locale, REVIENT EN ARRIÈRE et répète des passages déjà lus.
#
# STRATÉGIE EN 4 ÉTAPES (détails dans README_DARSI.md) :
#
#   ÉTAPE A — ANCRES : on cherche les n-grammes (5 puis 3 mots) de la
#      transcription qui apparaissent EXACTEMENT dans le texte de référence.
#      Une ancre = un couple fiable (indice_dans_transcription,
#      indice_dans_référence). En gardant TOUTES les ancres triées par temps,
#      la suite des indices de référence dessine la TRAJECTOIRE réelle de la
#      lecture : elle monte normalement… et REDESCEND quand le Sheikh répète
#      un passage antérieur. C'est la détection des répétitions.
#
#   ÉTAPE B — NEEDLEMAN-WUNSCH LOCAL : entre deux ancres consécutives, on
#      aligne la tranche de transcription contre la fenêtre de référence qui
#      couvre les deux ancres (algorithme d'alignement de séquences avec
#      scores match/mismatch/gap). Cet alignement local tolère les mots mal
#      reconnus et rattache le maximum de mots intermédiaires.
#
#   ÉTAPE C — INTERPOLATION : les mots de référence que Whisper a sautés
#      (aucun mot transcrit ne leur correspond) reçoivent des temps
#      interpolés linéairement entre leurs voisins connus.
#
#   ÉTAPE D — RUNS DE RÉCITATION (règle des « 3 états ») : un mot transcrit
#      n'est considéré RÉCITÉ que s'il appartient à un RUN d'au moins
#      --seuil-run mots consécutifs alignés (un alignement isolé est une
#      coïncidence : explications, formules répétitives). Pendant un run ->
#      surlignage jaune. Hors run -> AUCUN surlignage, la page affichée ne
#      change pas (l'explication hors livre ne fait pas avancer la lecture).

SIM_MIN = 0.60          # similarité minimale pour lier 2 mots
MOY_MIN = 0.70          # similarité moyenne minimale d'un run fiable
DUREE_MIN_RUN = 2.0     # durée minimale (s) d'un run fiable
LIMITE_NW = 400000      # sécurité : taille max d'une matrice NW (n * m)
VITESSE_MAX = 8.0       # mots/s max plausibles : au-delà, l'alignement est faux
SAUT_MAX = 5            # petits reculs tolérés dans un run (au-delà = répétition)


def similarite(wa: str, wb: str) -> float:
    """Similarité entre deux mots normalisés (0..1).
    Cas particulier ARABE : les ligatures désordonnées du PDF (الله écrit
    هلل ou اهلل) sont des ANAGRAMMES exactes -> considérées identiques."""
    if wa == wb:
        return 1.0
    if len(wa) >= 3 and sorted(wa) == sorted(wb):
        return 0.95
    return Fuzz.ratio(wa, wb) / 100.0


def trouver_ancres(mots_trans, mots_ref, n=5):
    """ÉTAPE A : ancres exactes par n-grammes (passe n=5, puis n=3).
    Renvoie [(i_trans, j_ref), ...] triée par position de transcription."""
    ref_norm = [m.norm for m in mots_ref]
    trans_norm = [m["norm"] for m in mots_trans]
    ancres = []
    deja = set()                                  # positions déjà couvertes

    for pas in (n, 3):
        index = {}
        for j in range(len(ref_norm) - pas + 1):
            cle = " ".join(ref_norm[j:j + pas])
            index.setdefault(cle, []).append(j)
        i = 0
        while i <= len(trans_norm) - pas:
            if pas < n and i in deja:             # 2e passe : zones déjà ancrées
                i += 1
                continue
            cle = " ".join(trans_norm[i:i + pas])
            if cle in index:
                for j in index[cle]:
                    ancres.append((i, j))
                for k in range(i, i + pas):
                    deja.add(k)
                i += pas                          # pas de chevauchement
            else:
                i += 1

    ancres.sort()
    return ancres


def nettoyer_ancres(ancres):
    """Supprime les ambiguïtés : un même moment de la transcription ne peut
    correspondre qu'à UN endroit du texte. Pour chaque position i en conflit,
    on garde l'indice j le plus proche de la trajectoire de lecture en cours
    (choix glouton) — les vraies répétitions, elles, sont sur des i différents
    et sont donc toutes conservées."""
    par_i = {}
    for i, j in ancres:
        par_i.setdefault(i, []).append(j)
    resultat, j_courant = [], 0
    for i in sorted(par_i):
        js = par_i[i]
        j_choisi = min(js, key=lambda j: abs(j - j_courant))
        resultat.append((i, j_choisi))
        j_courant = j_choisi
    return resultat


def aligner_nw(seq_a, seq_b):
    """Needleman-Wunsch global entre deux listes de mots normalisés.
    Scores : +2 si identiques ; -1 + 3*similarité sinon ; gap = -1.
    Renvoie les paires alignées [(indice_a, indice_b), ...] (les gaps sont
    simplement absents de la liste)."""
    n, m = len(seq_a), len(seq_b)
    if n == 0 or m == 0 or n * m > LIMITE_NW:
        return []
    GAP = -1.0
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    for a in range(1, n + 1):
        score[a][0] = a * GAP
    for b in range(1, m + 1):
        score[0][b] = b * GAP
    for a in range(1, n + 1):
        wa = seq_a[a - 1]
        ligne, prec = score[a], score[a - 1]
        for b in range(1, m + 1):
            wb = seq_b[b - 1]
            s = -1.0 + 3.0 * similarite(wa, wb)
            ligne[b] = max(prec[b - 1] + s, prec[b] + GAP, ligne[b - 1] + GAP)
    paires, a, b = [], n, m
    while a > 0 and b > 0:
        s = -1.0 + 3.0 * similarite(seq_a[a - 1], seq_b[b - 1])
        if abs(score[a][b] - (score[a - 1][b - 1] + s)) < 1e-9:
            paires.append((a - 1, b - 1))
            a -= 1
            b -= 1
        elif abs(score[a][b] - (score[a - 1][b] + GAP)) < 1e-9:
            a -= 1
        else:
            b -= 1
    paires.reverse()
    return paires


def aligner_transcription(mots_trans, mots_ref, seuil_run=4):
    """Exécute les étapes A -> D.
    Renvoie (runs_valides, ancres) où un run = [(i_trans, j_ref, sim), ...]."""
    n_trans = len(mots_trans)
    alignement = {}                     # i_trans -> (j_ref, similarité)

    # --- ÉTAPE A : ancres (points d'appui certains) -------------------------
    ancres = nettoyer_ancres(trouver_ancres(mots_trans, mots_ref, 5))
    for i, j in ancres:
        alignement[i] = (j, 1.0)
    print("  étape A : %d ancres fiables trouvées" % len(ancres))

    # --- ÉTAPE B : NW local entre ancres consécutives -----------------------
    # - La fenêtre couvre min(j1,j2)..max(j1,j2) : quand j2 < j1 (le Sheikh
    #   est revenu en arrière), elle contient toute la boucle de répétition.
    # - MAIS la progression EN AVANT est plafonnée : on ne peut pas lire
    #   5 x plus de mots qu'il n'y en a dans la transcription. Ce plafond
    #   empêche le NW d'éparpiller les mots jusqu'à des positions aléatoires.
    points = [(0, 0)] + ancres + [(n_trans - 1, len(mots_ref) - 1)]
    nb_nw = 0
    for (i1, j1), (i2, j2) in zip(points, points[1:]):
        if i2 <= i1:
            continue
        lo, hi = min(j1, j2), max(j1, j2)
        hi = min(hi, j1 + (i2 - i1) * 5 + 200)      # plafond de progression
        if (i2 - i1) * (hi - lo + 1) > LIMITE_NW:
            continue
        sous_a = [m["norm"] for m in mots_trans[i1:i2 + 1]]
        sous_b = [m.norm for m in mots_ref[lo:hi + 1]]
        for a, b in aligner_nw(sous_a, sous_b):
            i_abs, j_abs = i1 + a, lo + b
            if i_abs not in alignement:           # ne pas écraser les ancres
                alignement[i_abs] = (j_abs, similarite(sous_a[a], sous_b[b]))
                nb_nw += 1
    print("  étape B : %d mots supplémentaires alignés par Needleman-Wunsch" % nb_nw)

    # --- ÉTAPE D-1 : regrouper les alignements en runs -----------------------
    # Deux garde-fous de PLAUSIBILITÉ à l'intérieur d'un run :
    #   - saut en AVANT impossible : plus de mots sautés que la vitesse de
    #     lecture ne le permet (j augmente de 400 en 0,3 s = faux alignement) ;
    #   - saut en ARRIÈRE de plus de SAUT_MAX mots : c'est une RÉPÉTITION
    #     (le Sheikh revient en arrière) -> le run est coupé là, le passage
    #     répété formera son propre run.
    paires = sorted(alignement.items())
    runs, run = [], []
    for i, (j, sim) in paires:
        if sim >= SIM_MIN and run:
            ip, jp, _ = run[-1]
            dt = mots_trans[i]["debut"] - mots_trans[ip]["debut"]
            dj = j - jp
            if dj > dt * VITESSE_MAX + SAUT_MAX or dj < -SAUT_MAX:
                runs.append(run)
                run = []
        if sim >= SIM_MIN:
            run.append((i, j, sim))
        else:
            if run:
                runs.append(run)
            run = []
    if run:
        runs.append(run)

    # fusion des runs séparés par un petit trou (quelques mots mal reconnus)
    fusionnes = []
    for run in runs:
        if fusionnes and len(fusionnes[-1]) >= 2 and len(run) >= 2:
            prec = fusionnes[-1][-1]
            if 0 < run[0][0] - prec[0] <= 3 and 0 < run[0][1] - prec[1] <= 6:
                fusionnes[-1].extend(run)
                continue
        fusionnes.append(run)

    # --- ÉTAPE D-2 : ne garder que les runs de récitation fiables -----------
    bons = []
    for run in fusionnes:
        duree = mots_trans[run[-1][0]]["fin"] - mots_trans[run[0][0]]["debut"]
        moy = sum(s for _, _, s in run) / len(run)
        if len(run) >= seuil_run and duree >= DUREE_MIN_RUN and moy >= MOY_MIN:
            for _, j, s in run:
                mots_ref[j].recite = True
                mots_ref[j].similarite = max(mots_ref[j].similarite, s)
            bons.append(run)
    print("  étape D : %d runs de récitation validés (%d mots récités)"
          % (len(bons), sum(len(r) for r in bons)))
    return bons, ancres


def detecter_repetitions(runs, mots_trans, mots_ref):
    """Liste les retours en arrière : moments où le Sheikh répète un passage
    déjà lu (l'indice de référence redescend de plus de 5 mots)."""
    repetitions = []
    prec_j, prec_t = None, None
    for run in runs:
        for i, j, _ in run:
            t = mots_trans[i]["debut"]
            if prec_j is not None and j < prec_j - 5:
                page = mots_ref[j].page
                repetitions.append({"moment": round(t, 1),
                                    "page_reaffichee": page,
                                    "mot": mots_ref[j].texte})
                print("  RÉPÉTITION détectée à %.0f s -> retour page %d (« %s »)"
                      % (t, page, mots_ref[j].texte))
            prec_j, prec_t = j, t
    return repetitions


def inserer_mots_interpoles(run, mots_trans, mots_ref):
    """ÉTAPE C : à l'intérieur d'un run, les mots de référence sautés par
    Whisper (présents dans le livre, entre deux mots alignés consécutifs)
    reçoivent des temps interpolés — ils seront surlignés eux aussi."""
    evts = []
    prec_j, prec_fin = None, None
    for i, j, _ in run:
        # 1) mots sautés entre prec_j et j (si progression monotone)
        if prec_j is not None and j > prec_j + 1:
            t0, t1 = prec_fin, mots_trans[i]["debut"]
            if t1 > t0:
                nb = j - prec_j - 1
                pas = (t1 - t0) / (nb + 1)
                for k in range(1, nb + 1):
                    mref = mots_ref[prec_j + k]
                    if mref.x is not None:
                        evts.append((t0 + pas * (k - 1), t0 + pas * k,
                                     mref.page, mref.x, mref.y, mref.l, mref.h))
                    mref.debut, mref.fin = round(t0 + pas * (k - 1), 3), round(t0 + pas * k, 3)
                    mref.recite, mref.similarite = True, 0.5
        # 2) le mot courant lui-même
        mref = mots_ref[j]
        if mref.x is not None:
            evts.append((mots_trans[i]["debut"], mots_trans[i]["fin"],
                         mref.page, mref.x, mref.y, mref.l, mref.h))
        mref.debut, mref.fin = mots_trans[i]["debut"], mots_trans[i]["fin"]
        prec_j, prec_fin = j, mots_trans[i]["fin"]
    return evts

# ============================================================================
# SECTION 6 — Quelle page afficher à chaque instant ?
# ============================================================================

def construire_sequence_pages(runs, mots_trans, mots_ref):
    """Renvoie [(t_debut, t_fin_ou_None, num_page)] : les pages à afficher.
    La page change dès que le Sheikh commence à lire un mot d'une autre page
    — y compris quand il REVIENT EN ARRIÈRE (la page précédente réapparaît,
    c'est le comportement demandé). Hors récitation : la dernière page lue
    reste affichée, l'explication ne fait pas sauter de page."""
    evenements = []
    for run in runs:
        for i, j, _ in run:
            evenements.append((mots_trans[i]["debut"], mots_ref[j].page))
    evenements.sort()
    sequence, page_courante = [], None
    for t, page in evenements:
        if page != page_courante:
            if sequence:
                sequence[-1][1] = t                 # fermer le segment précédent
            sequence.append([t, None, page])
            page_courante = page
    return sequence


# ============================================================================
# SECTION 7 — Génération de la vidéo (FFmpeg)
# ============================================================================

def fmt_temps_ass(t: float) -> str:
    """Format de temps ASS : H:MM:SS.CC"""
    t = max(0.0, t)
    return "%d:%02d:%05.2f" % (int(t // 3600), int(t % 3600 // 60), t % 60)


def nettoyer_evenements(evenements, min_cluster=3, gap_cluster=2.5, duree_max_mot=1.6, pont=0.6):
    """Applique la règle « surligner UNIQUEMENT la vraie lecture du livre ».

    evenements : liste de (t0, t1, page, x, y, l, h) triée par t0.
    1) regroupe les mots consécutifs (même page, silence <= gap_cluster s) en
       « clusters » de lecture ;
    2) SUPPRIME les clusters de moins de min_cluster mots : ce sont des faux
       positifs (mot isolé reconnu par hasard pendant une explication) ;
    3) plafonne la durée de chaque mot (duree_max_mot) : un mot ne reste jamais
       surligné pendant une pause ou une explication ;
    4) rend le surligneur CONTINU : si le mot suivant (même page) démarre moins de
       `pont` s après la fin du mot courant, le jaune passe directement de l'un à
       l'autre (pas de clignotement dû au bruit des timestamps Whisper) ;
    5) supprime tout chevauchement (un seul mot surligné à la fois).
    Retourne (evenements_nettoyes, statistiques)."""
    # plafonner d'abord : un mot étiré sur une pause ne doit pas « ponter » deux lectures
    plaf0 = sum(1 for e in evenements if e[1] - e[0] > duree_max_mot)
    evs = sorted(((t0, min(t1, t0 + duree_max_mot), p, x, y, l, h)
                  for (t0, t1, p, x, y, l, h) in evenements), key=lambda e: (e[0], e[1]))
    if not evs:
        return evs, {"entree": 0, "sortie": 0, "isoles": 0, "plafonnes": 0, "chevauchements": 0, "ponts": 0}
    clusters = [[evs[0]]]
    for a, b in zip(evs, evs[1:]):
        if b[2] == a[2] and b[0] - a[1] <= gap_cluster:
            clusters[-1].append(b)
        else:
            clusters.append([b])
    gardes, isoles = [], 0
    for c in clusters:
        if len(c) >= min_cluster:
            gardes.extend(c)
        else:
            isoles += len(c)
    out, plafonnes, chevauch, ponts = [], plaf0, 0, 0
    for i, (t0, t1, page, x, y, l, h) in enumerate(gardes):
        if i + 1 < len(gardes):
            nxt = gardes[i + 1]
            if t1 > nxt[0]:
                t1 = nxt[0]
                chevauch += 1
            elif nxt[2] == page and 0 < nxt[0] - t1 <= pont:
                t1 = nxt[0]
                ponts += 1
        if t1 > t0:
            out.append((t0, t1, page, x, y, l, h))
    return out, {"entree": len(evs), "sortie": len(out), "isoles": isoles,
                 "plafonnes": plafonnes, "chevauchements": chevauch, "ponts": ponts}


def generer_ass(evenements, echelle_x, echelle_y, taille_video):
    r"""Génère un fichier de sous-titres ASS : un rectangle jaune semi-transparent
    (opacité ~0.45) dessiné sur chaque mot au moment où il est prononcé.
    Le dessin utilise le mode « Drawing » de libass : {\p1}…{\p0} (un rectangle
    vectoriel, indépendant de la police). Coordonnées PDF (points) converties
    en coordonnées vidéo (pixels) via les échelles calculées au rendu."""
    L = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: %d" % taille_video[0],
        "PlayResY: %d" % taille_video[1],
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Surl,Arial,20,&H00000000,&H00000000,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text",
    ]
    for (t0, t1, _page, x, y, l, h) in evenements:
        if t1 <= t0:
            continue
        X = x * echelle_x + 2.0
        Y = y * echelle_y + 2.0
        W = max(6.0, l * echelle_x - 4.0)
        H = max(6.0, h * echelle_y - 4.0)
        L.append("Dialogue: 2,%s,%s,Surl,,0,0,0,,{\\an7\\pos(%.1f,%.1f)"
                 "\\1c&H00FFFF&\\1a&H8C&\\p1}m 0 0 l %.1f 0 %.1f %.1f 0 %.1f{\\p0}"
                 % (fmt_temps_ass(t0), fmt_temps_ass(t1), X, Y, W, W, H, H))
    return "\n".join(L) + "\n"


def taille_image(chemin_image: str):
    """Dimensions (largeur, hauteur) d'une image via ffprobe."""
    out = lancer(["ffprobe", "-v", "error", "-select_streams", "v:0",
                  "-show_entries", "stream=width,height",
                  "-of", "csv=p=0:s=x", chemin_image])
    w, h = out.strip().split("x")
    return int(w), int(h)


def rendre_video(sequence_pages, chemin_audio, images, dossier_travail: Path,
                 chemin_sortie: Path, taille_video, fichier_ass=None, fps=25,
                 fmt="mp4"):
    """Assemble la vidéo finale :
      - images des pages (via le démuxeur « concat », gère 1 h+ d'audio) ;
      - audio original ; - surlignage ASS superposé si fourni.
    MP4  : H.264 + AAC (recommandé, lisible partout) ;
    MPEG : MPEG-2 + MP2 (format .mpg « MPEG » classique)."""
    dossier_travail.mkdir(parents=True, exist_ok=True)
    total = duree_audio(str(chemin_audio))

    # normaliser la séquence : le 1er segment démarre à 0, le dernier finit à total
    seq = [list(s) for s in sequence_pages]
    if not seq:
        if not images:
            raise RuntimeError("Aucune page à afficher (aucune image trouvée).")
        seq = [[0.0, total, min(images)]]
    if seq[0][0] > 0.5:
        seq.insert(0, [0.0, seq[0][0], seq[0][2]])
    for s in seq:
        if s[1] is None or s[1] > total:
            s[1] = total

    # fusionner les micro-segments (< 0,25 s) pour éviter le clignotement
    propres = [seq[0]]
    for s in seq[1:]:
        if s[0] - propres[-1][0] < 0.25:
            propres[-1][1] = s[1]
            propres[-1][2] = s[2]
        else:
            propres.append(s)

    def image_de(page):
        return images.get(page) or images[min(images)]

    concat = dossier_travail / "concat.txt"
    with open(concat, "w", encoding="utf-8") as f:
        for (t0, t1, page) in propres:
            f.write("file '%s'\nduration %.3f\n" % (image_de(page), max(0.05, t1 - t0)))
        f.write("file '%s'\n" % image_de(propres[-1][2]))   # spec concat : dernière image répétée

    vf = "scale=%d:%d" % taille_video
    if fichier_ass:
        vf += ",ass='%s'" % Path(fichier_ass).name          # cwd = dossier_travail

    if fmt == "mpeg":
        codec = ["-c:v", "mpeg2video", "-b:v", "3000k", "-c:a", "mp2", "-b:a", "192k"]
    else:
        codec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                 "-c:a", "aac", "-b:a", "160k"]

    cmd = (["ffmpeg", "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", concat.name,
            "-i", str(Path(chemin_audio).resolve()), "-vf", vf, "-r", str(fps),
            "-pix_fmt", "yuv420p"] + codec +
           ["-shortest", str(Path(chemin_sortie).resolve())])
    print("  rendu FFmpeg en cours (≈ 3 à 4 x la durée de l'audio sur CPU)…")
    lancer(cmd, cwd=str(dossier_travail))


# ============================================================================
# SECTION 8 — Rapports : timing.csv + rapport_alignement.json
# ============================================================================

def ecrire_rapports(mots_ref, repetitions, ancres, dossier_sortie: Path):
    """timing.csv  : mot;debut;fin;page;position;texte (un mot par ligne)
    rapport.json : statistiques + liste des répétitions détectées."""
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    csv_path = dossier_sortie / "timing.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        f.write("mot;debut;fin;page;position;texte\n")
        for m in mots_ref:
            if m.recite:
                f.write("%s;%.2f;%.2f;%d;%d;%s\n"
                        % (m.texte, m.debut or 0, m.fin or 0, m.page, m.position, m.texte))
    rapport = {
        "mots_reference": len(mots_ref),
        "mots_recites": sum(1 for m in mots_ref if m.recite),
        "ancres": len(ancres),
        "repetitions_detectees": repetitions,
    }
    json_path = dossier_sortie / "rapport_alignement.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)
    return csv_path, json_path


# ============================================================================
# SECTION 9 — Ligne de commande
# ============================================================================

EXT_AUDIO = (".mp3", ".wav", ".mpeg", ".mpg", ".m4a", ".ogg", ".opus", ".flac")


def trouver_fichier(dossier: Path, indique: str, extensions, quoi: str):
    """Retrouve un fichier : celui indiqué, ou le seul qui correspond."""
    if indique:
        c = dossier / indique
        if not c.exists():
            sys.exit("ERREUR : %s introuvable : %s" % (quoi, c))
        return c
    candidats = [f for f in sorted(dossier.iterdir())
                 if f.is_file() and f.suffix.lower() in extensions
                 and not f.name.startswith(".")]
    if not candidats:
        return None
    if len(candidats) > 1:
        print("Note : plusieurs %s trouvés, j'utilise %s" % (quoi, candidats[0].name))
    return candidats[0]


def main():
    p = argparse.ArgumentParser(
        description="Création automatique d'une vidéo Darsi synchronisée "
                    "(transcription Whisper + détection des répétitions + pages + surlignage).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dossier", required=True,
                   help="dossier du darsi (audio + pdf/texte + images)")
    p.add_argument("--audio", help="nom du fichier audio (sinon auto-détection)")
    p.add_argument("--pdf", help="nom du PDF du livre (sinon auto-détection)")
    p.add_argument("--texte", help="fichier .txt de référence découpé par « === PAGE N === » (si pas de PDF)")
    p.add_argument("--images", default="images",
                   help="dossier des images pageN.jpg (défaut : <dossier>/images)")
    p.add_argument("--langue", help="code langue principal : ar, so, fr… (défaut : détection auto)")
    p.add_argument("--modele", default="small",
                   help="modèle Whisper : tiny / base / small / medium / large-v3 (défaut : small)")
    p.add_argument("--surligner", action="store_true",
                   help="surligner les mots en jaune mot à mot (nécessite le PDF du livre)")
    p.add_argument("--seuil-run", type=int, default=4,
                   help="nb minimal de mots consécutifs pour valider une récitation (défaut 4)")
    p.add_argument("--min-cluster", type=int, default=3,
                   help="nb minimum de mots consécutifs pour surligner (défaut 3) : "
                        "supprime les mots isolés (faux positifs)")
    p.add_argument("--gap-cluster", type=float, default=2.5,
                   help="silence max (s) entre deux mots d'une même lecture (défaut 2.5)")
    p.add_argument("--pont", type=float, default=0.6,
                   help="écart max (s) comblé entre deux mots pour un surlignage continu (défaut 0.6)")
    p.add_argument("--duree-max-mot", type=float, default=1.6,
                   help="durée max (s) d'un mot surligné (défaut 1.6)")
    p.add_argument("--res", type=int, default=1080, help="hauteur de la vidéo (défaut 1080)")
    p.add_argument("--fps", type=int, default=25, help="images par seconde (défaut 25)")
    p.add_argument("--format", choices=("mp4", "mpeg"), default="mp4",
                   help="mp4 = H.264 (recommandé) ; mpeg = MPEG-2 .mpg")
    p.add_argument("--sortie", help="chemin de la vidéo finale (défaut : <dossier>/sortie/Darsi.mp4)")
    args = p.parse_args()

    dossier = Path(args.dossier).resolve()
    if not dossier.exists():
        sys.exit("ERREUR : dossier introuvable : " + str(dossier))
    dossier_travail = dossier / "travail"
    dossier_sortie = dossier / "sortie"
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    t_debut = time.time()

    # ---- 1) fichiers d'entrée ------------------------------------------------
    chemin_audio = trouver_fichier(dossier, args.audio, EXT_AUDIO, "fichier audio")
    if not chemin_audio:
        sys.exit("ERREUR : aucun fichier audio trouvé dans " + str(dossier))
    chemin_pdf = trouver_fichier(dossier, args.pdf, (".pdf",), "PDF du livre")
    chemin_txt = trouver_fichier(dossier, args.texte, (".txt",), "texte de référence")
    print("Audio : " + chemin_audio.name)
    verifier_dependances(necessite_pdf=bool(chemin_pdf or args.surligner))

    # ---- 2) texte de référence + images des pages -----------------------------
    if chemin_pdf:
        print("Livre : " + chemin_pdf.name + " -> extraction des mots et des coordonnées…")
        mots_par_page, tailles_pages = reference_depuis_pdf(str(chemin_pdf))
        images = charger_images_existantes(dossier / args.images)
        if not images:
            print("  aucune image trouvée -> génération depuis le PDF…")
            images = pdf_vers_images(str(chemin_pdf), dossier / args.images)
    elif chemin_txt:
        print("Texte : " + chemin_txt.name + " (découpe par « === PAGE N === »)")
        mots_par_page, tailles_pages = reference_depuis_txt(str(chemin_txt))
        images = charger_images_existantes(dossier / args.images)
        if not images:
            sys.exit("ERREUR : sans PDF, les images page1.jpg, page2.jpg… sont obligatoires "
                     "dans " + str(dossier / args.images))
    else:
        sys.exit("ERREUR : fournir un PDF du livre OU un fichier texte de référence (--texte).")
    mots_ref = liste_plate(mots_par_page)
    print("  %d pages, %d mots de référence" % (len(mots_par_page), len(mots_ref)))

    # ---- 3) transcription -----------------------------------------------------
    print("1/4 Transcription Whisper (mots horodatés)…")
    mots_trans = transcrire_audio(str(chemin_audio), dossier_travail,
                                  args.modele, args.langue)
    print("  %d mots transcrits, audio de %.0f s" % (len(mots_trans), duree_audio(str(chemin_audio))))

    # ---- 4) alignement + détection des répétitions -----------------------------
    print("2/4 Alignement avec le texte de référence…")
    runs, ancres = aligner_transcription(mots_trans, mots_ref, args.seuil_run)
    repetitions = detecter_repetitions(runs, mots_trans, mots_ref)
    print("  %d répétition(s) / retour(s) en arrière détecté(s)" % len(repetitions))

    # ---- 5) pages + surlignage --------------------------------------------------
    print("3/4 Séquence des pages…")
    sequence_pages = construire_sequence_pages(runs, mots_trans, mots_ref)

    fichier_ass, echelle = None, None
    if args.surligner:
        if not chemin_pdf:
            print("  AVERTISSEMENT : --surligner nécessite le PDF -> surlignage désactivé.")
        else:
            evenements = []
            for run in runs:
                evenements.extend(inserer_mots_interpoles(run, mots_trans, mots_ref))
            evenements.sort(key=lambda e: e[0])
            evenements, stats_net = nettoyer_evenements(
                evenements, args.min_cluster, args.gap_cluster, args.duree_max_mot, args.pont)
            print("  nettoyage surlignage : %(entree)d -> %(sortie)d mots "
                  "(%(isoles)d isolés supprimés, %(plafonnes)d durées plafonnées, "
                  "%(chevauchements)d chevauchements corrigés, %(ponts)d transitions lissées)" % stats_net)
            if not evenements:
                print("  aucun mot avec coordonnées -> surlignage impossible.")
            else:
                w_page, h_page = tailles_pages[min(tailles_pages)]
                W = int(round(args.res * w_page / h_page / 2.0)) * 2
                taille_video = (W, args.res)
                echelle = (W / w_page, args.res / h_page)
                fichier_ass = dossier_travail / "surlignage.ass"
                fichier_ass.parent.mkdir(parents=True, exist_ok=True)
                with open(fichier_ass, "w", encoding="utf-8") as f:
                    f.write(generer_ass(evenements, echelle[0], echelle[1], taille_video))
                print("  %d rectangles de surlignage écrits" % len(evenements))
    if not fichier_ass:
        if images:
            w0, h0 = taille_image(images[min(images)])
            taille_video = (int(round(args.res * w0 / h0 / 2.0)) * 2, args.res)
        else:
            taille_video = (int(args.res * 0.707), args.res)

    # ---- 6) rendu ----------------------------------------------------------------
    print("4/4 Rendu de la vidéo…")
    ext = ".mpg" if args.format == "mpeg" else ".mp4"
    chemin_sortie = Path(args.sortie) if args.sortie else dossier_sortie / ("Darsi" + ext)
    rendre_video(sequence_pages, chemin_audio, images, dossier_travail,
                 chemin_sortie, taille_video, fichier_ass, args.fps, args.format)

    # ---- 7) rapports ---------------------------------------------------------------
    csv_path, json_path = ecrire_rapports(mots_ref, repetitions, ancres, dossier_sortie)

    print("")
    print("==============================================")
    print("Vidéo : %s" % chemin_sortie)
    print("Timing des mots lus : %s" % csv_path)
    print("Rapport d'alignement : %s" % json_path)
    print("Durée totale : %.0f min" % ((time.time() - t_debut) / 60))
    print("==============================================")


if __name__ == "__main__":
    main()
