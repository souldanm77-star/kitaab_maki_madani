#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fixture de démo — crée demo/livre.pdf (2 pages : Al-Fatiha + Al-Ikhlas).
Génération : HTML -> Chromium (playwright) print-to-PDF.
Chromium écrit le meilleur ToUnicode qui soit pour l'arabe façonné :
le texte reste parfaitement extractible par 1_extraire_pdf.py.
"""
import os
import subprocess

from playwright.sync_api import sync_playwright

ICI = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.join(ICI, "..", "download", "synchronisation-recitation", "demo")

FATIHA = [
    "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
    "الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ",
    "الرَّحْمَٰنِ الرَّحِيمِ",
    "مَالِكِ يَوْمِ الدِّينِ",
    "إِيَّاكَ نَعْبُدُ وَإِيَّاكَ نَسْتَعِينُ",
    "اهْدِنَا الصِّرَاطَ الْمُسْتَقِيمَ",
    "صِرَاطَ الَّذِينَ أَنْعَمْتَ عَلَيْهِمْ غَيْرِ الْمَغْضُوبِ عَلَيْهِمْ وَلَا الضَّالِّينَ",
]
IKHLAS = [
    "قُلْ هُوَ اللَّهُ أَحَدٌ",
    "اللَّهُ الصَّمَدُ",
    "لَمْ يَلِدْ وَلَمْ يُولَدْ",
    "وَلَمْ يَكُن لَّهُ كُفُوًا أَحَدٌ",
]
MARKS = ["١", "٢", "٣", "٤", "٥", "٦", "٧"]


def verset(txt, i):
    n = MARKS[i % len(MARKS)]
    return f'<p class="v">{txt} <span class="m">﴿{n}﴾</span></p>'


HTML_TXT = f"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 0; }}
body {{ font-family: 'Amiri', serif; direction: rtl; text-align: center;
       margin: 0; }}
.feuille {{ width: 210mm; min-height: 297mm; padding: 22mm 20mm;
           box-sizing: border-box; }}
.titre {{ font-size: 30pt; color: #0e6e5c; font-weight: bold;
         border-bottom: 2px solid #c8961e; padding-bottom: 8px;
         margin-bottom: 24px; }}
.page2 {{ page-break-before: always; }}
.basmala {{ font-size: 20pt; color: #7a6a4f; margin: 0 0 18px; }}
.v {{ font-size: 25pt; line-height: 2.3; margin: 0; }}
.m {{ color: #0e6e5c; font-size: 17pt; }}
</style></head><body>
<div class="feuille">
 <p class="titre">سُورَةُ الْفَاتِحَة</p>
 {''.join(verset(t, i) for i, t in enumerate(FATIHA))}
</div>
<div class="feuille page2">
 <p class="titre">سُورَةُ الْإِخْلَاص</p>
 <p class="basmala">بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ</p>
 {''.join(verset(t, i) for i, t in enumerate(IKHLAS))}
</div>
</body></html>"""

os.makedirs(DEMO, exist_ok=True)
html_path = os.path.join(DEMO, "livre.html")
with open(html_path, "w", encoding="utf-8") as f:
    f.write(HTML_TXT)

with sync_playwright() as p:
    nav = p.chromium.launch()
    page = nav.new_page()
    page.goto("file://" + html_path)
    page.emulate_media(media="print")
    page.pdf(path=os.path.join(DEMO, "livre.pdf"), format="A4",
             print_background=True,
             margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
    nav.close()

pdf = os.path.join(DEMO, "livre.pdf")
assert os.path.exists(pdf), "impression Chromium échouée"
print("✔ PDF de démo (Chromium) →", pdf)
