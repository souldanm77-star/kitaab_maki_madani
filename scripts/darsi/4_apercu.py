#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÉTAPE 4 — Aperçu statique du design (validation avant rendu vidéo)
===================================================================
Génère des images 1920×1080 : image du cheikh à gauche, page réelle du
livre à droite, rectangle surligneur jaune sur la ligne en cours.

Usage :
  python 4_apercu.py --t 12.5 45 130.7          # instants à simuler
  python 4_apercu.py --t 12.5 --sans-ligne      # page sans surlignage
"""
import argparse
import json
import os

from PIL import Image, ImageDraw

DOS = "/home/z/my-project/travail/darsi1"
W, H = 1920, 1080
LARGEUR_PAGE = 834            # 1080 × (612/792)
X_PAGE = W - LARGEUR_PAGE     # bord gauche du panneau livre
ECHELLE = H / 792.0           # pt PDF → pixels

COUL_FOND = (18, 20, 24)      # fond panneau cheikh
COUL_SURLIGN = (255, 205, 0)  # jaune surligneur


def charger():
    lignes = json.load(open(f"{DOS}/lignes_timing.json", encoding="utf-8"))
    lignes.sort(key=lambda L: (L["page"], L["n"]))
    return lignes


def ligne_active(lignes, t):
    """Dernière ligne dont le début ≤ t (le cheikh commente → on reste)."""
    courante = None
    for L in lignes:
        if L["debut"] <= t:
            courante = L
        else:
            break
    return courante


def apercu(t, lignes, dest, sheikh="/home/z/my-project/upload/IMAGE.jpeg"):
    img = Image.new("RGB", (W, H), COUL_FOND)

    # --- panneau gauche : cheikh ------------------------------------------
    if os.path.exists(sheikh):
        im = Image.open(sheikh).convert("RGB")
        r = min((W - LARGEUR_PAGE) / im.width, H / im.height)
        nw, nh = int(im.width * r), int(im.height * r)
        im = im.resize((nw, nh), Image.LANCZOS)
        img.paste(im, (0, (H - nh) // 2))

    # --- panneau droit : page du livre -------------------------------------
    L = ligne_active(lignes, t)
    page_no = L["page"] if L else 1
    page = Image.open(f"{DOS}/pages/page_{page_no:02d}.png").convert("RGB")
    page = page.resize((LARGEUR_PAGE, H), Image.LANCZOS)

    d = ImageDraw.Draw(page, "RGBA")
    if L:
        x0, y0, x1, y1 = L["bbox"]
        # coordonnées LOCALES à la page (le rect est dessiné sur `page`
        # avant collage sur le canvas) — PAS de décalage X_PAGE ici
        rx0 = x0 * ECHELLE - 8
        ry0 = y0 * ECHELLE - 5
        rx1 = x1 * ECHELLE + 8
        ry1 = y1 * ECHELLE + 5
        d.rectangle([rx0, ry0, rx1, ry1], fill=COUL_SURLIGN + (70,),
                    outline=COUL_SURLIGN + (200,), width=3)

    img.paste(page, (X_PAGE, 0))
    # fine séparation
    d2 = ImageDraw.Draw(img)
    d2.rectangle([X_PAGE - 3, 0, X_PAGE, H], fill=(60, 55, 40))
    img.save(dest)
    print(f"✔ aperçu t={t:.1f}s page={page_no} "
          f"ligne={L['n'] if L else '?'} → {dest}")


def main():
    global DOS
    ap = argparse.ArgumentParser()
    ap.add_argument("--t", type=float, nargs="+",
                    default=[5, 30, 75, 150, 300, 600],
                    help="instants à prévisualiser")
    ap.add_argument("--dossier", default=DOS)
    ap.add_argument("--sans-ligne", action="store_true")
    args = ap.parse_args()

    DOS = args.dossier
    lignes = charger()
    if args.sans_ligne:
        lignes = []
    os.makedirs(f"{DOS}/apercus", exist_ok=True)
    for t in args.t:
        apercu(t, lignes, f"{DOS}/apercus/apercu_{t:08.2f}s.png")


if __name__ == "__main__":
    main()
