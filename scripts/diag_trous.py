#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostic : pour chaque TROU entre runs actifs, score de similarité
glissant (fenêtres de 8 s) contre la plage du livre correspondante.
But : distinguer (a) somali/hors-livre réel (scores bas ~<0.55)
     (b) RÉCITATION MANQUÉE (scores moyens 0.55-0.75 que le filtre a rejetés).
Sortie : rapport texte + CSV par dars.
"""
import json, sys, unicodedata
from pathlib import Path

PROJET = Path(__file__).resolve().parent.parent / "download" / "video-recitation"
sys.path.insert(0, str(PROJET / "pipeline"))
from commun import normaliser, similarite  # noqa


def charger(dars):
    trav = PROJET / "travail_darsi" / dars
    timing = json.load(open(trav / "timing.json"))
    trans = json.load(open(trav / "transcription.json"))
    pages = json.load(open(PROJET / "travail_darsi" / "pages.json"))["pages"]
    return timing, trans, pages


def main(dars):
    timing, trans, pages = charger(dars)
    mots_livre = []           # [(page, position, normalisé)]
    for p in pages:
        for w in p["mots"]:
            mots_livre.append((p["numero"], w["position"], normaliser(w["texte"])))
    wm = [normaliser(m["mot"]) for m in trans["mots"] if m["mot"].strip()]
    wt = [(m["debut"], m["fin"]) for m in trans["mots"] if m["mot"].strip()]

    runs = timing["runs"]
    # trous entre runs (et avant le 1er / après le dernier)
    trous = []
    prev_fin = 0.0
    prev_page = 1
    for r in runs:
        if r["debut"] - prev_fin > 20:
            trous.append((prev_fin, r["debut"], prev_page, r["page_debut"]))
        prev_fin = r["fin"]
        prev_page = r["page_fin"]
    if timing["duree"] - prev_fin > 20:
        trous.append((prev_fin, timing["duree"], prev_page, prev_page))

    rapport = [f"=== {dars} : {len(trous)} trous de >20 s ==="]
    for (d0, d1, pg0, pg1) in trous:
        # plage livre candidate : autour de la page précédente
        idx0 = next((i for i, (p, pos, _) in enumerate(mots_livre) if p == pg0), 0)
        idx1 = next((i for i, (p, pos, _) in enumerate(mots_livre) if p >= pg1 + 1), len(mots_livre))
        plage = [(p, pos, n) for (p, pos, n) in mots_livre[max(0, idx0 - 40): min(len(mots_livre), idx1 + 40)]]
        # fenêtres de 8 s dans le trou
        lignes = []
        t = d0
        while t < d1:
            t2 = min(t + 8, d1)
            wmots = [wm[i] for i in range(len(wm)) if wt[i][0] >= t - 0.5 and wt[i][1] <= t2 + 0.5]
            if len(wmots) >= 4:
                # meilleur score glissant sur la plage livre (fenêtre de même taille)
                best, bp = 0.0, None
                n = len(wmots)
                for j in range(0, max(1, len(plage) - n), 3):
                    cand = plage[j:j + n]
                    if len(cand) < n:
                        break
                    s = sum(similarite(a, c[2]) for a, c in zip(wmots, cand)) / n
                    if s > best:
                        best, bp = s, (cand[0][0], cand[0][1])
                lignes.append((t, t2, len(wmots), best, bp))
            t = t2
        if lignes:
            rapport.append(f"TROU {d0:7.1f} → {d1:7.1f}  (pages {pg0}→{pg1})")
            for (t, t2, n, best, bp) in lignes:
                flag = " ⚠️LECTURE?" if best >= 0.55 else ""
                pos_txt = f"@p{bp[0]}pos{bp[1]}" if bp else "@?"
                rapport.append(f"   {t:7.1f}-{t2:7.1f}  {n:3d}m  best={best:.2f} {pos_txt}{flag}")
    out = PROJET.parent.parent / "scripts" / f"trous_{dars}.txt"
    out.write_text("\n".join(rapport), encoding="utf-8")
    print(f"→ {out}")
    print("\n".join(rapport[:60]))


if __name__ == "__main__":
    main(sys.argv[1])
