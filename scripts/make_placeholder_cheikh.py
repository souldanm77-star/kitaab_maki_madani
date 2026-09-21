# -*- coding: utf-8 -*-
"""Génère une image placeholder digne pour le panneau cheikh (démo).
À REMPLACER par la vraie photo/image du cheikh pour les vidéos réelles."""
import math
from PIL import Image, ImageDraw

W, H = 768, 1080
OR = (203, 164, 74)
OR_SOMBRE = (140, 112, 50)

img = Image.new('RGB', (W, H))
d = ImageDraw.Draw(img)

# dégradé vertical vert profond
for y in range(H):
    t = y / H
    d.line([(0, y), (W, y)],
           fill=(int(14 + 14 * t), int(58 - 18 * t), int(48 - 14 * t)))

# double cadre ornemental
d.rectangle([16, 16, W - 17, H - 17], outline=OR, width=4)
d.rectangle([30, 30, W - 31, H - 31], outline=OR_SOMBRE, width=1)

# étoile à 8 branches + rosace centrale
cx, cy, R = W // 2, 400, 210
pts = []
for k in range(16):
    ang = math.pi * k / 8 - math.pi / 2
    r = R if k % 2 == 0 else R * 0.42
    pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
d.polygon(pts, outline=OR, width=5)
d.ellipse([cx - 92, cy - 92, cx + 92, cy + 92], outline=OR, width=3)
d.ellipse([cx - 60, cy - 60, cx + 60, cy + 60], outline=OR_SOMBRE, width=2)

# petit arc décoratif en bas (mosquée stylisée)
for rx, ry in ((190, 150), (150, 120), (110, 88)):
    d.arc([cx - rx, 700, cx + rx, 700 + 2 * ry], 180, 360, fill=OR_SOMBRE, width=3)
d.line([(cx - 200, 700), (cx + 200, 700)], fill=OR, width=3)

# texte indicatif latin (sans dépendance au modelage arabe)
d.text((W // 2, 950), "P L A C E H O L D E R", anchor='mm', fill=OR)
d.text((W // 2, 990), "remplacer par l'image du cheikh", anchor='mm',
       fill=(150, 130, 90))

img.save('/home/z/my-project/download/video-recitation/demo/cheikh_placeholder.png')
print('placeholder cheikh créé')
