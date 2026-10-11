#!/usr/bin/env python3
"""Inspection des fichiers réels : PDF (texte + boxes), audio (durée), image."""
import fitz  # PyMuPDF
import json, subprocess, sys

PDF = "/home/z/my-project/upload/LIVRE.pdf"

doc = fitz.open(PDF)
print(f"=== PDF : {len(doc)} pages ===")

total_words = 0
for i, page in enumerate(doc):
    words = page.get_text("words")  # (x0, y0, x1, y1, mot, bloc, ligne, num_mot)
    text = page.get_text("text")
    n = len(words)
    total_words += n
    preview = text[:120].replace("\n", " | ")
    print(f"Page {i+1}: {n} mots, {len(text)} chars | début: {preview}")
    if i == 0:
        # détail des 15 premiers mots avec boxes
        print("  --- 15 premiers mots (x0,y0,x1,y1,mot,bloc,ligne,wpos) ---")
        for w in words[:15]:
            print(f"  ({w[0]:.0f},{w[1]:.0f},{w[2]:.0f},{w[3]:.0f}) b{w[5]} l{w[6]} w{w[7]}: {w[4]!r}")

print(f"\nTOTAL mots extraits: {total_words}")

# Taille des pages
p0 = doc[0]
print(f"Taille page 1: {p0.rect.width:.0f} x {p0.rect.height:.0f} pts")

# Test export PNG de la page 1 pour vérifier le rendu
pix = doc[0].get_pixmap(dpi=150)
pix.save("/home/z/my-project/scripts/test_page1.png")
print(f"Page 1 rendue en PNG: {pix.width}x{pix.height}")

# Durée audio
r = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1",
     "/home/z/my-project/upload/Audio darsi-1.mpeg"],
    capture_output=True, text=True)
print(f"\n=== Audio : durée = {r.stdout.strip()} s ===")

# Métadonnées ID3 (parfois le titre contient le nom du dars)
r2 = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "default=nw=1",
                     "/home/z/my-project/upload/Audio darsi-1.mpeg"], capture_output=True, text=True)
print(r2.stdout)
