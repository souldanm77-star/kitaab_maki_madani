#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÉTAPE 1 (v3, PDF réel) — Extraction mot à mot du LIVRE avec positions
=======================================================================
Pièges du PDF (généré par Word) et correctifs :

  A. Ligatures lam-alef inversées : « إلا » extrait « إ + ا(zéro-larg) + ل ».
     → l'alef de largeur nulle est repéré puis recollé APRÈS son ل : « إلا ».
  B. Mot الله : glyphe spécial extrait à l'envers (هللا / هلل).
     → dictionnaire : هللا→الله, هلل→لله.
  C. Runs bidi séparés (المك | ية, الن | حاس) : Word coupe les mots en
     plusieurs objets « ligne ». → on collecte TOUS les caractères de la
     page, on les regroupe en lignes VISUELLES par recouvrement y, puis
     on trie RTL et on découpe les mots dans ce flux unifié.
  D. Espaces parasites vs vraies frontières : les espaces ont largeur
     nulle → frontière retenue seulement si espace + vrai gap visuel
     (> 1.2 pt), ou gap énorme sans espace (> 2.6 pt).
  E. Notes de bas de page : tout texte sous la DERNIÈRE ligne horizontale
     de la page est exclu (le trait au-dessus des notes) ; numéro de
     page (y > 735) exclu aussi.

Les diacritiques sont jetés dès la collecte (le texte sert à l'alignement ;
la vidéo affiche la page réelle en image, rien n'est perdu à l'écran).

SORTIES (dans --dossier) :
  livre_mots.json   {meta, mots:[{page, position, ligne, bbox, texte}]}
  lignes.json       lignes visuelles (bbox) pour le surligneur
  pages/page_NN.png rendu de chaque page (zoom 2.0)
"""
import argparse
import json
import os
import re
from collections import defaultdict

import fitz

# ---------------------------------------------------------------- constantes
TASHKEEL = re.compile(r'[\u064B-\u065F\u0670\u06D6-\u06ED\u0640\u200E\u200F'
                      r'\u202A-\u202E\u0610-\u061A]')
GAP_ESPACE = 1.2      # espace + gap > ceci  -> vraie frontière de mot
GAP_SECURITE = 2.6    # gap > ceci sans espace -> frontière quand même
ZEROW = 0.35          # largeur < ceci pt  -> caractère "zéro-largeur"
Y_PIED = 735.0        # au-dessous : numéro de page

FIX_MOTS = [('هللا', 'الله'), ('هلل', 'لله')]


def reparer(t: str) -> str:
    for a, b in FIX_MOTS:
        t = t.replace(a, b)
    return t


def est_alef(c: str) -> bool:
    return c in ('ا', 'أ', 'إ', 'آ', 'ٱ')


def lignes_horizontales(page):
    """Y des traits horizontaux (séparateur de notes, tableaux)."""
    ys = set()
    for d in page.get_drawings():
        for item in d["items"]:
            if item[0] == 'l':
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) < 0.5 and abs(p1.x - p2.x) > 100:
                    ys.add(round(p1.y, 1))
            elif item[0] == 're':
                r = item[1]
                if r.height < 2 and r.width > 100:
                    ys.add(round(r.y0, 1))
    return sorted(ys)


def collecter_chars(page):
    """Tous les caractères utiles de la page, hors notes/pied/tashkeel."""
    seuil_notes = lignes_horizontales(page)
    seuil_notes = seuil_notes[-1] if seuil_notes else 9999.0
    raw = page.get_text("rawdict")
    chars = []
    for bloc in raw["blocks"]:
        if bloc["type"] != 0:
            continue
        for ligne in bloc["lines"]:
            for span in ligne["spans"]:
                for c in span["chars"]:
                    ch = c["c"]
                    y0, y1 = c["bbox"][1], c["bbox"][3]
                    # E. notes de bas de page + numéro de page
                    if y0 > Y_PIED or (y0 > seuil_notes and y0 < Y_PIED):
                        continue
                    if TASHKEEL.match(ch):
                        continue
                    if ch.strip() == '':
                        w = c["bbox"][2] - c["bbox"][0]
                        chars.append((' ', c["bbox"], c["origin"], True, True))
                    else:
                        w = c["bbox"][2] - c["bbox"][0]
                        chars.append((ch, c["bbox"], c["origin"], w < ZEROW,
                                      False))
    return chars


def cluster_lignes(chars):
    """Regroupe des chars (tuples) en lignes visuelles par recouvrement y."""
    tri = sorted(chars, key=lambda c: (c[1][1], -c[2][0]))
    groupes = []
    for c in tri:
        y0, y1 = c[1][1], c[1][3]
        h = max(y1 - y0, 0.1)
        place = False
        for g in groupes:
            ov = min(y1, g["y1"]) - max(y0, g["y0"])
            if ov > 0.4 * min(h, g["y1"] - g["y0"]):
                g["chars"].append(c)
                g["y0"] = min(g["y0"], y0)
                g["y1"] = max(g["y1"], y1)
                place = True
                break
        if not place:
            groupes.append({"y0": y0, "y1": y1, "chars": [c]})
    groupes.sort(key=lambda g: g["y0"])
    return groupes


def mots_de_ligne(groupe):
    """Découpe un groupe de chars (1 ligne visuelle) en mots."""
    chars = sorted(groupe["chars"], key=lambda c: -c[2][0])

    # A. recoller les alefs zéro-largeur sur leur ل  (ordre logique لا)
    bases = [i for i, t in enumerate(chars) if not t[4]]
    for i, idx in enumerate(bases):
        ch, bbox_, orig, zw, _ = chars[idx]
        if zw and est_alef(ch):
            cible = None
            for j in (i + 1, i + 2):
                if j < len(bases):
                    k = bases[j]
                    if not chars[k][3] and '…ا' not in chars[k][0]:
                        if chars[k][0] == 'ل':
                            cible = k
                            break
                        if j == i + 2:
                            break
            if cible is not None:
                chars[cible] = (chars[cible][0] + '…ا', chars[cible][1],
                                chars[cible][2], False, False)
                chars[idx] = None
    flux = [c for c in chars if c is not None]

    # C/D. découpe : frontière si (espace + vrai gap) ou (gap énorme)
    mots, cur = [], []
    dernier = None
    espace_vu = False
    for t in flux:
        ch, bbox_, orig, zw, esp = t
        if esp:
            if cur:
                espace_vu = True
            continue
        nouveau = '…ا' in ch
        if nouveau:
            ch = ch.replace('…ا', '')
        if cur and dernier is not None:
            gap = dernier[0] - bbox_[2]
            if (espace_vu and gap > GAP_ESPACE) or gap > GAP_SECURITE:
                mots.append(cur)
                cur = []
            espace_vu = False
        cur.append((ch, bbox_))
        if nouveau:
            cur.append(('ا', (bbox_[2] - 0.01, bbox_[1], bbox_[2], bbox_[3])))
        dernier = (bbox_[0], bbox_[2])
    if cur:
        mots.append(cur)
    return mots


def extraire_page(page):
    """Mots d'une page : [{texte, bbox}] en ordre de lecture."""
    chars = collecter_chars(page)
    if not chars:
        return []
    mots_page = []
    for gi, groupe in enumerate(cluster_lignes(chars)):
        for cs in mots_de_ligne(groupe):
            texte = reparer(''.join(c[0] for c in cs))
            if not texte.strip():
                continue
            x0 = min(c[1][0] for c in cs)
            x1 = max(c[1][2] for c in cs)
            y0 = min(c[1][1] for c in cs)
            y1 = max(c[1][3] for c in cs)
            mots_page.append({"texte": texte, "bbox": [round(x0, 2),
                                                       round(y0, 2),
                                                       round(x1, 2),
                                                       round(y1, 2)]})
    return mots_page


def grouper_lignes(mots_page):
    """Regroupe les mots d'une page en lignes visuelles (par recouvrement y)."""
    if not mots_page:
        return []
    tri = sorted(mots_page, key=lambda m: (m["bbox"][1], -m["bbox"][0]))
    lignes = []
    for m in tri:
        y0, y1 = m["bbox"][1], m["bbox"][3]
        place = False
        for L in lignes:
            ov = min(y1, L["y1"]) - max(y0, L["y0"])
            if ov > 0.4 * (y1 - y0):
                L["mots"].append(m)
                L["y0"] = min(L["y0"], y0)
                L["y1"] = max(L["y1"], y1)
                place = True
                break
        if not place:
            lignes.append({"y0": y0, "y1": y1, "mots": [m]})
    lignes.sort(key=lambda L: L["y0"])
    out = []
    for n, L in enumerate(lignes):
        L["mots"].sort(key=lambda m: -m["bbox"][0])       # RTL
        for k, m in enumerate(L["mots"]):
            m["ligne"] = n
            m["dans_ligne"] = k
        out.append({
            "n": n,
            "bbox": [round(min(m["bbox"][0] for m in L["mots"]), 2),
                     round(L["y0"], 2),
                     round(max(m["bbox"][2] for m in L["mots"]), 2),
                     round(L["y1"], 2)],
            "mots": [m["texte"] for m in L["mots"]],
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default="/home/z/my-project/upload/LIVRE.pdf")
    ap.add_argument("--dossier", default="/home/z/my-project/travail/darsi1")
    ap.add_argument("--zoom", type=float, default=2.0)
    ap.add_argument("--apercu", type=int, default=2, help="pages affichées")
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    os.makedirs(os.path.join(args.dossier, "pages"), exist_ok=True)

    tous, lignes_toutes, pos = [], [], 0
    for pno in range(len(doc)):
        page = doc[pno]
        mots_page = extraire_page(page)
        for m in mots_page:
            m["page"] = pno + 1
            m["position"] = pos
            pos += 1
        tous.extend(mots_page)
        gl = grouper_lignes(mots_page)
        for L in gl:
            L["page"] = pno + 1
        lignes_toutes.extend(gl)
        pix = page.get_pixmap(matrix=fitz.Matrix(args.zoom, args.zoom))
        pix.save(os.path.join(args.dossier, "pages", f"page_{pno+1:02d}.png"))

    meta = {"pdf": args.pdf, "pages": len(doc), "nb_mots": len(tous),
            "nb_lignes": len(lignes_toutes)}
    with open(os.path.join(args.dossier, "livre_mots.json"), "w",
              encoding="utf-8") as f:
        json.dump({"meta": meta, "mots": tous}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(args.dossier, "lignes.json"), "w",
              encoding="utf-8") as f:
        json.dump({"meta": meta, "lignes": lignes_toutes}, f,
                  ensure_ascii=False, indent=1)

    print(f"✔ {len(doc)} pages, {len(tous)} mots, {len(lignes_toutes)} lignes")
    print(f"→ {args.dossier}/livre_mots.json, lignes.json, pages/*.png")

    for pno in range(min(args.apercu, len(doc))):
        mp = [m for m in tous if m["page"] == pno + 1]
        print(f"\n--- Page {pno+1} : {len(mp)} mots ---")
        courante, ligne = None, []
        for m in mp:
            if m.get("ligne") != courante and ligne:
                print("   " + " | ".join(ligne))
                ligne = []
            courante = m.get("ligne")
            ligne.append(m["texte"])
        if ligne:
            print("   " + " | ".join(ligne))


if __name__ == "__main__":
    main()
