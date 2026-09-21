#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÉTAPE 1 — Extraction mot à mot du livre PDF
============================================
Lit le PDF page par page, découpe le texte en mots et produit un fichier
JSON structuré qui devient la RÉFÉRENCE UNIQUE du texte pour toute la
synchronisation (on ne demande jamais à Whisper de réécrire le livre).

Sortie : mots_livre.json
{
  "meta":   {...},
  "lignes": [ {"page":1, "ligne":0, "texte":"...", "mots":[1,2,3]}, ... ],
  "mots":   [ {"page":1,"position":1,"ligne":0,"texte":"بِسْمِ","parle":true}, ... ]
}
- position : index GLOBAL du mot (1-based), dans l'ordre de lecture
- ligne    : index GLOBAL de la ligne
- parle    : false pour les tokens décoratifs (n° de verset ﴿١﴾, numéros de
             page, lignes sans lettre arabe) -> non alignés, interpolés.

Usage :
  python 1_extraire_pdf.py --pdf demo/livre.pdf --sortie demo/mots_livre.json
  Options utiles :
    --ordre rtl     : si le PDF sort les mots en ordre visuel inversé
                      (PDF mal produit), réordonne de droite à gauche.
    --page N        : n'extraire que la page N
"""
import argparse
import json
import re
import sys

import fitz  # PyMuPDF

# chiffres arabes/orientaux, ornements de versets, ponctuation seule
DECOR = re.compile(r'^[0-9\u0660-\u0669\u066B-\u066D\u06DD﴿﴾۞،,؛;:.!؟?*\-–—()\[\]«»"\'\s]+$')
ARABE = re.compile(r'[\u0600-\u06FF]')
# marques diacritiques isolées en tête de mot (artefact d'extraction fréquent)
MARKS = re.compile(r'^[\u064B-\u065F\u0670\u06D6-\u06ED]+')


def reparer_marques(mot: str) -> str:
    """Certains PDF extraient le premier signe diacritique AVANT sa lettre
    (ex: 'ِبِسْمِ' au lieu de 'بِسْمِ'). On recolle les marques de tête
    juste après la première lettre porteuse."""
    m = MARKS.match(mot)
    if m and len(mot) > len(m.group(0)):
        reste = mot[len(m.group(0)):]
        mot = reste[0] + m.group(0) + reste[1:]
    return mot


def est_decoratif(mot: str) -> bool:
    """True si le token n'est pas un vrai mot prononcé (n° de verset, etc.)."""
    if not ARABE.search(mot):
        return True                      # pas une seule lettre arabe
    if DECOR.match(mot):
        return True                      # uniquement chiffres/ornements/punct
    return False


def extraire(pdf: str, sortie: str, ordre: str = "auto", filtre_page: int | None = None):
    doc = fitz.open(pdf)
    mots, lignes = [], []
    position = 0
    ligne_globale = -1

    for pno, page in enumerate(doc, start=1):
        if filtre_page and pno != filtre_page:
            continue
        brut = page.get_text("words")    # (x0,y0,x1,y1,mot,bloc,ligne,n)
        # regrouper par (bloc, ligne) en conservant l'ordre du flux
        groupes = {}
        for x0, y0, x1, y1, w, bloc, lig, _ in brut:
            if not w.strip():
                continue
            groupes.setdefault((bloc, lig), []).append((x0, y0, x1, y1, w))
        clefs = sorted(groupes.keys(), key=lambda k: (min(t[1] for t in groupes[k]), k[0]))

        ligne_page = -1
        for clef in clefs:
            ws = groupes[clef]
            if ordre == "rtl":           # PDF en ordre visuel inversé
                ws.sort(key=lambda t: -t[0])
            texte_ligne = " ".join(t[4] for t in ws).strip()
            if not texte_ligne:
                continue
            ligne_globale += 1
            ligne_page += 1
            idx_mots_ligne = []
            for _, _, _, _, w in ws:
                w = reparer_marques(w.strip())
                if not w:
                    continue
                position += 1
                idx_mots_ligne.append(position)
                mots.append({
                    "page": pno,
                    "position": position,
                    "ligne": ligne_globale,
                    "texte": w,
                    "parle": not est_decoratif(w),
                })
            lignes.append({
                "page": pno,
                "ligne": ligne_globale,
                "texte": texte_ligne,
                "mots": idx_mots_ligne,
            })

    meta = {
        "pdf": pdf,
        "pages": len({m["page"] for m in mots}) or 0,
        "nb_mots": len(mots),
        "nb_lignes": len(lignes),
        "mots_parles": sum(1 for m in mots if m["parle"]),
        "ordre": ordre,
    }

    # garde-fou : texte probablement illisible (PDF scanné sans OCR ?)
    if meta["nb_mots"] and meta["mots_parles"] / meta["nb_mots"] < 0.3:
        print("⚠ AVERTISSEMENT : moins de 30 % des tokens sont des mots arabes.",
              file=sys.stderr)
        print("  → Le PDF est peut-être scanné (image) : il faut passer par OCR,",
              file=sys.stderr)
        print("    ou essayer --ordre rtl si les mots semblent inversés.",
              file=sys.stderr)

    with open(sortie, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "lignes": lignes, "mots": mots},
                  f, ensure_ascii=False, indent=1)

    print(f"✔ {meta['nb_mots']} mots extraits "
          f"({meta['mots_parles']} prononcés) — {meta['pages']} page(s), "
          f"{meta['nb_lignes']} ligne(s)")
    print(f"→ {sortie}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Extraction mot à mot d'un PDF arabe")
    ap.add_argument("--pdf", required=True, help="fichier PDF du livre")
    ap.add_argument("--sortie", required=True, help="JSON de sortie (mots_livre.json)")
    ap.add_argument("--ordre", choices=["auto", "rtl"], default="auto",
                    help="rtl si le PDF sort les mots en ordre visuel inversé")
    ap.add_argument("--page", type=int, default=None, help="ne traiter que cette page")
    args = ap.parse_args()
    extraire(args.pdf, args.sortie, args.ordre, args.page)
