#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÉTAPE 6 — Montage vidéo : vidéo du cheikh + panneau page surlignée
===================================================================
Assemble le montage du brief :

  ┌─────────────────────────────┬──────────────┐
  │                             │              │
  │      VIDÉO DU CHEIKH        │  صفحة الكتاب │  ← vraie page du PDF,
  │      (60 % de la largeur)   │  (40 %)      │    karaoké ASS incrusté
  │                             │              │
  └─────────────────────────────┴──────────────┘

Étapes internes :
  1. rend la page du PDF en PNG haute résolution (PyMuPDF)
  2. fabrique le panneau : page PNG + sous-titres ASS karaoké incrustés (ffmpeg)
  3. côte à côte avec la vidéo du cheikh (ffmpeg hstack, audio du cheikh)
     — sans --video-cheikh, un panneau provisoire remplace la vidéo (démo)

Usage :
  python 6_montage_video.py --pdf demo/livre.pdf --page 1 \
          --ass demo/sous_titres.ass --audio demo/audio.mp3 \
          --video-cheikh cheikh.mp3... (optionnel) \
          --sortie demo/video_montage.mp4 [--taille 1920x1080] [--panneau 40]
"""
import argparse
import os
import subprocess
import sys

import fitz

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None


def sh(cmd):
    print("  $", " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1500:], file=sys.stderr)
        raise SystemExit("Commande ffmpeg/outil en échec.")
    return r


def rendre_page(pdf, page, cible_w, cible_h, png):
    """Rend la page PDF sur un canevas parchemin aux dimensions du panneau."""
    doc = fitz.open(pdf)
    pix = doc[page - 1].get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
    pix.save(png)
    doc.close()

    img = Image.open(png).convert("RGB")
    marge = 24
    max_w, max_h = cible_w - 2 * marge, cible_h - 2 * marge
    echelle = min(max_w / img.width, max_h / img.height)
    img = img.resize((int(img.width * echelle), int(img.height * echelle)),
                     Image.LANCZOS)
    toile = Image.new("RGB", (cible_w, cible_h), (247, 241, 225))
    toile.paste(img, ((cible_w - img.width) // 2, (cible_h - img.height) // 2))
    toile.save(png)


def placeholder_cheikh(w, h, png, duree, audio):
    """Panneau de secours (démo) si aucune vidéo du cheikh n'est fournie."""
    if Image is None:
        raise SystemExit("Pillow requis : pip install pillow")
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    haut, bas = (13, 59, 46), (8, 32, 24)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)],
               fill=tuple(int(a + (b - a) * t) for a, b in zip(haut, bas)))
    d.ellipse([w // 2 - 110, h // 2 - 190, w // 2 + 110, h // 2 + 30],
              outline=(240, 215, 138), width=4)
    police = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42) \
        if os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf") \
        else ImageFont.load_default()
    txt = "VIDEO DU CHEIKH"
    bb = d.textbbox((0, 0), txt, font=police)
    d.text(((w - bb[2] + bb[0]) / 2, h // 2 + 70), txt, font=police,
           fill=(240, 215, 138))
    petit = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24) \
        if os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf") \
        else ImageFont.load_default()
    txt2 = "remplacer par la vraie video"
    bb2 = d.textbbox((0, 0), txt2, font=petit)
    d.text(((w - bb2[2] + bb2[0]) / 2, h // 2 + 140), txt2, font=petit,
           fill=(180, 170, 150))
    img.save(png)
    sh(["ffmpeg", "-y", "-loop", "1", "-i", png, "-i", audio,
        "-t", f"{duree:.3f}", "-r", "24",
        "-c:v", "libx264", "-preset", "fast", "-crf", "28",
        "-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p", "placeholder.mp4"])
    return "placeholder.mp4"


def main():
    ap = argparse.ArgumentParser(description="Montage cheikh + livre surligné")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--ass", required=True, help="sous-titres ASS karaoké")
    ap.add_argument("--audio", required=True, help="audio de la récitation")
    ap.add_argument("--video-cheikh", default=None, help="vidéo du cheikh (option)")
    ap.add_argument("--sortie", required=True)
    ap.add_argument("--taille", default="1920x1080")
    ap.add_argument("--panneau", type=int, default=40,
                    help="largeur du panneau livre en % (défaut: 40)")
    ap.add_argument("--fontsdir", default="../assets",
                    help="dossier contenant Amiri-Regular.ttf")
    args = ap.parse_args()

    W, H = (int(x) for x in args.taille.split("x"))
    w_panneau = W * args.panneau // 100
    w_cheikh = W - w_panneau
    ici = os.path.abspath(os.path.dirname(args.sortie)) or "."
    fontsdir = os.path.abspath(args.fontsdir)

    # 1) page PNG du livre aux dimensions du panneau
    png_page = os.path.join(ici, f"_page{args.page}.png")
    print(f"[1/3] rendu de la page {args.page} → {os.path.basename(png_page)}")
    rendre_page(args.pdf, args.page, w_panneau, H, png_page)

    # 2) durée + audio de référence
    r = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", args.audio])
    duree = float(r.stdout.strip())
    if args.video_cheikh:
        gauche = args.video_cheikh
        entrees = ["-i", gauche, "-i", png_page]
        mapp_audio = "-map", "0:a?"
    else:
        print("[2/3] pas de vidéo cheikh → panneau provisoire (démo)")
        ph = placeholder_cheikh(w_cheikh, H, os.path.join(ici, "_cheikh.png"),
                                duree, args.audio)
        gauche = os.path.join(ici, ph)
        entrees = ["-i", gauche, "-i", png_page]
        mapp_audio = "-map", "0:a"

    # 3) panneau livre (page + karaoké) puis hstack final
    print("[3/3] incrustation karaoké + montage côte à côte")
    filtres = (
        f"[0:v]scale={w_cheikh}:{H}:force_original_aspect_ratio=increase,"
        f"crop={w_cheikh}:{H},setsar=1[g];"
        f"[1:v]scale={w_panneau}:{H},setsar=1,"
        f"ass='{os.path.abspath(args.ass)}':fontsdir='{fontsdir}'[p];"
        f"[g][p]hstack=inputs=2[v]"
    )
    sh(["ffmpeg", "-y", *entrees,
        "-i", args.audio,
        "-filter_complex", filtres,
        *mapp_audio, "-map", "[v]",
        "-t", f"{duree:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "aac", "-b:a", "160k", "-shortest", "-pix_fmt", "yuv420p",
        args.sortie])

    for f in (png_page,):
        try:
            os.remove(f)
        except OSError:
            pass
    print(f"✔ vidéo montée → {args.sortie} ({duree:.1f}s, {W}x{H})")


if __name__ == "__main__":
    main()
