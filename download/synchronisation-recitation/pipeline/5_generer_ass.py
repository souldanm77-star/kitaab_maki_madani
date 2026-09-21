#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÉTAPE 5 — Sous-titres ASS karaoké (surlignage mot à mot pour le montage)
=========================================================================
Produit un fichier .ass où CHAQUE mot est un segment de karaoké {\k} :
avant son heure, le mot est en couleur « encre » ; dès que le cheikh le
prononce, il passe automatiquement en couleur « or ». C'est exactement
l'effet bismi / الله / الرحمن / الرحيم vu dans le brief.

Deux styles de sortie :
  --style panneau  : grand format centré, pour le panneau صفحة الكتاب
                     à côté de la vidéo du cheikh (défaut, 768x1080)
  --style video    : sous-titres bas d'écran pour une vidéo 1920x1080

Le rendu bidi/shaping est assuré par le lecteur (libass, Premiere, DaVinci),
le texte reste donc le texte EXACT du PDF, tashkeel compris.

Usage :
  python 5_generer_ass.py --livre demo/mots_livre.json \
          --timing demo/synchronisation_complet.json \
          --sortie demo/sous_titres.ass --style panneau
"""
import argparse
import json

ENTETE = """[Script Info]
; Livre synchronisé — karaoké mot à mot (généré par 5_generer_ass.py)
Title: {titre}
ScriptType: v4.00+
WrapStyle: 2
YCbCr Matrix: TV.709
PlayResX: {rx}
PlayResY: {ry}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karo,Amiri,{taille},&H001CA8E3,&H001A2833,&H00DDEFF6,&H80000000,{gras},0,0,0,100,100,0,0,1,{contour},1,{align},40,40,{margev},1
Style: Info,Amiri,{info_taille},&H007A6A4F,&H007A6A4F,&H00DDEFF6,&H80000000,0,0,0,0,100,100,0,0,1,0,0,{align},40,40,{info_margev},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

STYLES = {
    "panneau": dict(rx=768, ry=1080, taille=58, gras=1, contour=0, align=5,
                    margev=40, info_taille=30, info_margev=60),
    "video":   dict(rx=1920, ry=1080, taille=62, gras=0, contour=3, align=2,
                    margev=52, info_taille=34, info_margev=110),
}


def ts(t: float) -> str:
    """Secondes -> H:MM:SS.CS (format ASS)."""
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def main():
    ap = argparse.ArgumentParser(description="ASS karaoké mot à mot")
    ap.add_argument("--livre", required=True)
    ap.add_argument("--timing", required=True, help="synchronisation_complet.json")
    ap.add_argument("--sortie", required=True)
    ap.add_argument("--style", choices=list(STYLES), default="panneau")
    ap.add_argument("--titre", default="Livre synchronisé")
    ap.add_argument("--etiquette", default="",
                    help='ex: "سُورَةُ الْفَاتِحَة" — ligne d\'info affichée au-dessus')
    args = ap.parse_args()

    livre = json.load(open(args.livre, encoding="utf-8"))
    timing = json.load(open(args.timing, encoding="utf-8"))
    par_pos = {m["position"]: m for m in timing["mots"]}

    st = STYLES[args.style]
    sortie = [ENTETE.format(titre=args.titre, **st)]
    if args.etiquette:
        # ligne d'info décorative en layer 1, pleine durée
        duree = max((m["fin"] for m in timing["mots"]), default=2.0)
        sortie.append(f"Dialogue: 1,{ts(0)},{ts(duree)},Info,,0,0,0,,{args.etiquette}")

    nb_events = nb_mots = 0
    for ligne in livre["lignes"]:
        tokens, premier, dernier = [], None, None
        for pos in ligne["mots"]:
            m = par_pos.get(pos)
            if not m:
                continue
            cs = max(1, round((m["fin"] - m["debut"]) * 100))
            if m["parle"]:
                tokens.append(f"{{\\k{cs}}}{m['texte']}")
                nb_mots += 1
            else:
                # décoratif (﴿١﴾...) : couleur forcée encre -> jamais doré
                tokens.append(f"{{\\k{cs}}}{{\\c&H1A2833&}}{m['texte']}")
            if premier is None:
                premier = m["debut"]
            dernier = m["fin"]
        if premier is None or dernier is None or dernier <= premier:
            continue
        texte = "".join(tokens)
        sortie.append(
            f"Dialogue: 0,{ts(premier)},{ts(dernier + 0.15)},Karo,,0,0,0,,"
            f"{{\\fad(60,0)}}{texte}")
        nb_events += 1

    with open(args.sortie, "w", encoding="utf-8") as f:
        f.write("\n".join(sortie) + "\n")

    print(f"✔ ASS généré : {nb_events} lignes, {nb_mots} mots karaoké "
          f"(style {args.style}) → {args.sortie}")
    print("  Astuce ffmpeg : -vf \"ass=sous_titres.ass:fontsdir=assets\" "
          "(police Amiri requise)")


if __name__ == "__main__":
    main()
