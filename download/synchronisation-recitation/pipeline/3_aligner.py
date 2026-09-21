#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÉTAPE 3 — Alignement arabe : mots du livre  ⟷  timestamps Whisper
==================================================================
C'est le MOTEUR du surlignage. Principe :

  1. NORMALISATION des deux côtés : suppression du tashkeel (بِسْمِ → بسم),
     unification des alef/hamza (أ إ آ ٱ → ا), ى→ي, ة→ه.
     → la comparaison devient insensible aux diacritiques et aux variantes.
  2. ALIGNEMENT des deux séquences par programmation dynamique
     (Needleman-Wunsch avec bande) + similarité floue : Whisper peut mal
     entendre un mot, en fusionner deux ou en sauter un — l'alignement survit.
  3. TIMING pour CHAQUE mot du livre :
       - mot apparié à un mot Whisper            → timestamp direct
       - mot sauté / mal reconnu par Whisper     → interpolation entre voisins
       - tokens décoratifs (﴿١﴾, n° de page)     → interpolés, jamais surlignés
  4. EXPORTS :
       - synchronisation.csv            mot;debut;fin;page;position;texte
       - synchronisation_complet.json   + ligne, parle, confiance, source

Usage (un audio = une page) :
  python 3_aligner.py --livre demo/mots_livre.json --whisper demo/transcription.json \
                      --page 1 --audio demo/audio.mp3 \
                      --sortie demo/synchronisation.csv --complet demo/synchronisation_complet.json

Usage (un seul audio pour tout le livre) :
  python 3_aligner.py ... (sans --page)
"""
import argparse
import csv
import json
import re
import subprocess
from difflib import SequenceMatcher

# ---- normalisation arabe -------------------------------------------------
TASHKEEL = re.compile(r'[\u064B-\u065F\u0670\u06D6-\u06ED\u0640\u200E\u200F\u202A-\u202E]')
PONCT = re.compile(r'[^\u0600-\u06FF]')
SUBST = (('أ', 'ا'), ('إ', 'ا'), ('آ', 'ا'), ('ٱ', 'ا'),
         ('ى', 'ي'), ('ة', 'ه'), ('ؤ', 'و'), ('ئ', 'ي'), ('\u0621', ''))


def normaliser(t: str) -> str:
    """Forme canonique d'un mot : sans tashkeel, lettres unifiées."""
    t = TASHKEEL.sub('', t)
    for a, b in SUBST:
        t = t.replace(a, b)
    t = PONCT.sub('', t)
    return t.strip()


def similarite(a: str, b: str) -> float:
    """Similarité floue 0..1 entre deux mots normalisés."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # inclusion (Whisper a collé deux mots ou coupé un mot)
    if len(a) >= 3 and len(b) >= 3 and (a in b or b in a):
        return 0.85 + 0.1 * min(len(a), len(b)) / max(len(a), len(b))
    return SequenceMatcher(None, a, b).ratio()


SEUIL = 0.45     # en dessous : l'appariement est interdit
GAP = -0.28      # pénalité de saut (mot ignoré d'un côté ou de l'autre)


def aligner_dp(wmots, bmots, bande=None):
    """Programmation dynamique : aligne la séquence Whisper (i) sur la
    séquence livre (j). Renvoie la liste d'opérations dans l'ordre :
       ('M', i, j)  appariement
       ('IW', i)    mot Whisper sans correspondance (ignoré)
       ('IB', j)    mot du livre sans audio direct (interpolé ensuite)
    """
    n, m = len(wmots), len(bmots)
    if n == 0 or m == 0:
        return [('IW', i) for i in range(n)] + [('IB', j) for j in range(m)]
    if bande is None:
        bande = max(60, int(0.4 * max(n, m)))

    NEG = float('-inf')
    dp = [[NEG] * (m + 1) for _ in range(n + 1)]
    bt = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0

    for i in range(n + 1):
        j0 = max(0, i - bande)
        j1 = min(m, i + bande)
        for j in range(j0, j1 + 1):
            if i == 0 and j == 0:
                continue
            best, choix = NEG, None
            if i > 0 and j > 0:
                s = similarite(wmots[i - 1], bmots[j - 1])
                if s >= SEUIL and dp[i - 1][j - 1] > NEG:
                    v = dp[i - 1][j - 1] + s
                    if v > best:
                        best, choix = v, 'M'
            if i > 0 and dp[i - 1][j] > NEG:
                v = dp[i - 1][j] + GAP
                if v > best:
                    best, choix = v, 'IW'
            if j > 0 and dp[i][j - 1] > NEG:
                v = dp[i][j - 1] + GAP
                if v > best:
                    best, choix = v, 'IB'
            dp[i][j] = best
            bt[i][j] = choix

    if dp[n][m] == NEG:                       # bande trop étroite : on ouvre
        return aligner_dp(wmots, bmots, bande=max(n, m) + 2)

    ops, i, j = [], n, m
    while i > 0 or j > 0:
        c = bt[i][j]
        if c == 'M':
            ops.append(('M', i - 1, j - 1)); i -= 1; j -= 1
        elif c == 'IW':
            ops.append(('IW', i - 1)); i -= 1
        elif c == 'IB':
            ops.append(('IB', None, j - 1)); j -= 1
        else:                                  # bord hors bande
            if i > 0:
                ops.append(('IW', i - 1)); i -= 1
            else:
                ops.append(('IB', None, j - 1)); j -= 1
    ops.reverse()
    return ops


def duree_audio(chemin: str) -> float:
    """Durée via ffprobe (ffmpeg est requis de toute façon pour la vidéo)."""
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', chemin],
            capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def repartir(a: int, b: float, c: float, longueurs):
    """Répartit l'intervalle [b, c] sur `a` mots proportionnellement aux
    longueurs ; renvoie une liste de (debut, fin)."""
    if a <= 0:
        return []
    if c - b < 0.06 * a:
        c = b + 0.06 * a
    total = sum(longueurs) or a
    out, cur = [], b
    for L in longueurs:
        d = (c - b) * (L / total)
        out.append((cur, cur + d))
        cur += d
    return out


def construire_timing(parle_mots, whisper_mots, ops, duree):
    """Timestamps pour les mots PARLÉS du livre à partir des opérations DP.
    Renvoie times[k] = (debut, fin, conf, source) ou None."""
    times = [None] * len(parle_mots)
    for op, wi, bi in [o for o in ops if o[0] == 'M']:
        wm = whisper_mots[wi]
        conf = similarite(parle_mots[bi]['norme'], wm['norme'])
        times[bi] = (wm['debut'], wm['fin'], conf, 'whisper')

    # interpolation des trous entre ancrages
    longueurs = [len(w['norme']) + 1 for w in parle_mots]
    ancrages = [k for k, t in enumerate(times) if t]
    if not ancrages:
        # aucun appariement : répartition uniforme sur toute la durée
        for k, (b, c) in enumerate(repartir(len(parle_mots), 0.0, duree, longueurs)):
            times[k] = (b, c, 0.0, 'uniforme')
        return times

    # tête (mots avant le 1er ancrage)
    k0 = ancrages[0]
    if k0 > 0:
        t0 = min(times[k0][0], duree or times[k0][0])
        for k, (b, c) in enumerate(repartir(k0, 0.0, t0, longueurs[:k0])):
            times[k] = (b, c, 0.0, 'interpole')
    # corps
    for x in range(len(ancrages) - 1):
        ka, kb = ancrages[x], ancrages[x + 1]
        if kb - ka > 1:
            b = times[ka][1]
            c = times[kb][0]
            for y, (b2, c2) in enumerate(
                    repartir(kb - ka - 1, b, c, longueurs[ka + 1:kb])):
                times[ka + 1 + y] = (b2, c2, 0.0, 'interpole')
    # queue
    kd = ancrages[-1]
    if kd < len(parle_mots) - 1:
        b = times[kd][1]
        c = duree if duree > b else b + 2.0
        for y, (b2, c2) in enumerate(
                repartir(len(parle_mots) - 1 - kd, b, c,
                         longueurs[kd + 1:])):
            times[kd + 1 + y] = (b2, c2, 0.0, 'interpole')
    return times


def lisser(times):
    """Garantit la monotonie : debut>=fin du précédent, fin>debut."""
    prev_fin = 0.0
    for t in times:
        if not t:
            continue
        b, c = t[0], t[1]
        if b < prev_fin:
            decal = prev_fin - b
            b, c = b + decal, max(c + decal, b + 0.06)
        if c <= b:
            c = b + 0.06
        t[0], t[1] = b, c
        prev_fin = t[1]


def main():
    ap = argparse.ArgumentParser(description="Alignement livre ⟷ Whisper")
    ap.add_argument("--livre", required=True, help="mots_livre.json (étape 1)")
    ap.add_argument("--whisper", required=True, help="transcription.json (étape 2)")
    ap.add_argument("--audio", default=None, help="audio source (pour la durée)")
    ap.add_argument("--sortie", required=True, help="CSV synchronisation.csv")
    ap.add_argument("--complet", default=None,
                    help="JSON détaillé (pour HTML/ASS) [défaut: <sortie>.json]")
    ap.add_argument("--page", type=int, default=None,
                    help="aligner uniquement cette page (audio = 1 page)")
    ap.add_argument("--page-debut", type=int, default=1,
                    help="page de début si l'audio commence à mi-livre")
    args = ap.parse_args()

    livre = json.load(open(args.livre, encoding="utf-8"))
    wh = json.load(open(args.whisper, encoding="utf-8"))

    mots = livre["mots"]
    if args.page:
        mots = [m for m in mots if m["page"] == args.page]

    duree = wh.get("duree") or (duree_audio(args.audio) if args.audio else 0.0)
    if not duree:
        raise SystemExit("Durée audio inconnue : passez --audio ou utilisez "
                         "le JSON de l'étape 2.")

    # préparation : mots parlés du livre, normalisés
    parle_idx = [i for i, m in enumerate(mots) if m["parle"]]
    parle_mots = [{"norme": normaliser(m["texte"]), "m": m} for i, m in
                  enumerate(mots) if m["parle"]]

    # mots Whisper normalisés (les tokens vides/pur ponctuation sont écartés)
    whisper_mots = []
    for w in wh["mots"]:
        n = normaliser(w["mot"])
        if n:
            whisper_mots.append({"norme": n, "debut": w["debut"], "fin": w["fin"]})

    print(f"Alignement : {len(parle_mots)} mots du livre ⟷ "
          f"{len(whisper_mots)} mots Whisper ({duree:.1f}s)...")
    ops = aligner_dp([w["norme"] for w in whisper_mots],
                     [p["norme"] for p in parle_mots])
    nb_match = sum(1 for o in ops if o[0] == 'M')

    times = construire_timing(parle_mots, whisper_mots, ops, duree)
    lisser(times)

    # reconstitution de la liste complète (parlés + décoratifs interpolés)
    pos_vers_time = {parle_mots[q]["m"]["position"]: q for q in range(len(parle_mots))}
    resultat = []
    dernier_fin = 0.0
    for i, m in enumerate(mots):
        if m["parle"]:
            b, c, conf, src = times[pos_vers_time[m["position"]]]
            resultat.append({"debut": round(b, 3), "fin": round(c, 3),
                             "confiance": round(conf, 3), "source": src})
            dernier_fin = c
        else:
            # décoratif : entre le mot parlé précédent et le suivant
            suiv = None
            for j in range(i + 1, len(mots)):
                if mots[j]["parle"]:
                    q = pos_vers_time.get(mots[j]["position"])
                    if q is not None:
                        suiv = times[q][0]
                    break
            b = dernier_fin
            c = suiv if (suiv and suiv > b) else b + 0.08
            resultat.append({"debut": round(b, 3), "fin": round(c, 3),
                             "confiance": 0.0, "source": "decoratif"})

    # ---- exports ---------------------------------------------------------
    complet_path = args.complet or (args.sortie.rsplit('.', 1)[0] + "_complet.json")
    complet = {
        "meta": {
            "livre": args.livre,
            "whisper": args.whisper,
            "audio": args.audio or wh.get("audio", ""),
            "page": args.page or "toutes",
            "duree": round(duree, 3),
            "mots_livre": len(mots),
            "mots_whisper": len(whisper_mots),
            "appariements": nb_match,
            "couverture_pct": round(100 * nb_match / max(1, len(parle_mots)), 1),
        },
        "mots": [
            {
                "page": m["page"],
                "position": m["position"],
                "ligne": m["ligne"],
                "mot": normaliser(m["texte"]),
                "texte": m["texte"],
                "parle": m["parle"],
                **resultat[i],
            }
            for i, m in enumerate(mots)
        ],
    }
    with open(complet_path, "w", encoding="utf-8") as f:
        json.dump(complet, f, ensure_ascii=False, indent=1)

    with open(args.sortie, "w", encoding="utf-8", newline="") as f:
        wcsv = csv.writer(f, delimiter=";")
        wcsv.writerow(["mot", "debut", "fin", "page", "position", "texte"])
        for i, m in enumerate(mots):
            r = resultat[i]
            wcsv.writerow([complet["mots"][i]["mot"],
                           f"{r['debut']:.3f}", f"{r['fin']:.3f}",
                           m["page"], m["position"], m["texte"]])

    # ---- aperçu ----------------------------------------------------------
    meta = complet["meta"]
    print(f"✔ appariements directs : {nb_match}/{len(parle_mots)} "
          f"({meta['couverture_pct']} %) — le reste est interpolé")
    print(f"→ {args.sortie}")
    print(f"→ {complet_path}")
    print("\nAperçu (12 premiers mots parlés) :")
    print(f"  {'texte':<20}{'debut':>9}{'fin':>9}  {'conf':>5}  source")
    vu = 0
    for i, m in enumerate(mots):
        if not m["parle"] or vu >= 12:
            continue
        r = resultat[i]
        print(f"  {m['texte']:<20}{r['debut']:>9.3f}{r['fin']:>9.3f}"
              f"  {r['confiance']:>5.2f}  {r['source']}")
        vu += 1


if __name__ == "__main__":
    main()
