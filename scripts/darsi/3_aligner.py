#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÉTAPE 3 v2 — Alignement livre ⟷ Whisper (dars complet, ~80 min)
================================================================
Spécificité d'un DARS : le cheikh lit le livre ET commente. La moitié des
mots Whisper sont des explications absentes du livre → l'aligneur doit
sauter librement les mots Whisper (IW) tout en suivant le fil du texte.

  1. Normalisation arabe (tashkeel supprimé, hamzas unifiées…)
  2. VOL PILOTE : repère la trajectoire de dérive (index livre en fonction
     de l'index Whisper) en cherchant les meilleurs mots-clefs localement.
  3. DP Needleman-Wunsch en bande autour de la trajectoire pilote
     (largeur ±220) → appariements (M) / sauts (IW, IB).
  4. Timing de chaque mot du livre : direct (whisper) ou interpolé ;
     lissage de monotonie.
  5. Export :
       synchronisation.csv         mot;debut;fin;page;position;texte
       synchronisation_complet.json  (+ ligne, bbox, confiance, source)
       lignes_timing.json          [ {page, n, bbox, debut, fin} ]
       couverture.json             diagnostics (pct apparié, pages couvertes)
"""
import argparse
import csv
import json
import re
from difflib import SequenceMatcher

# ---- normalisation arabe --------------------------------------------------
TASHKEEL = re.compile(r'[\u064B-\u065F\u0670\u06D6-\u06ED\u0640\u200E\u200F'
                      r'\u202A-\u202E\u0610-\u061A]')
PONCT = re.compile(r'[^\u0621-\u064A]')   # lettres arabes seules conservées
SUBST = (('أ', 'ا'), ('إ', 'ا'), ('آ', 'ا'), ('ٱ', 'ا'),
         ('ى', 'ي'), ('ة', 'ه'), ('ؤ', 'و'), ('ئ', 'ي'), ('\u0621', ''))


def normaliser(t: str) -> str:
    t = TASHKEEL.sub('', t)
    for a, b in SUBST:
        t = t.replace(a, b)
    t = PONCT.sub('', t)
    return t.strip()


_cache_sim = {}


def similarite(a: str, b: str) -> float:
    if a == b:
        return 1.0 if a else 0.0
    cle = (a, b) if a < b else (b, a)
    v = _cache_sim.get(cle)
    if v is not None:
        return v
    if not a or not b:
        return 0.0
    la, lb = len(a), len(b)
    if abs(la - lb) > 0.7 * max(la, lb):
        v = 0.0
    elif la >= 3 and lb >= 3 and (a in b or b in a):
        v = 0.85 + 0.1 * min(la, lb) / max(la, lb)
    else:
        v = SequenceMatcher(None, a, b).ratio()
    _cache_sim[cle] = v
    return v


SEUIL = 0.52
GAP = -0.30


def passe_pilote(wmots, bmots):
    """Trajectoire approximative j(i) : pour des mots Whisper échantillonnés,
    meilleur correspondant du livre dans une fenêtre glissante.
    Garde-fous :
      - mots longs uniquement (≥ 5 lettres) ;
      - rejet des mots AMBIGUS (≥ 3 correspondances fortes dans la fenêtre,
        ex. المكي / المدني / القرآن qui reviennent à chaque page) ;
      - saut avant plafonné (+60) et retour limité (−40) : la lecture
        avance lentement, une dérive de demi-livre est impossible."""
    n, m = len(wmots), len(bmots)
    if n == 0 or m == 0:
        return [min(int(i * m / max(n, 1)), m - 1) for i in range(n)]
    centres = {}
    c = 0
    pas = 10
    for i in range(0, n, pas):
        if len(wmots[i]) < 5:
            continue
        j0, j1 = max(0, c - 40), min(m, c + 260)
        meilleurs = []
        for j in range(j0, j1):
            if len(bmots[j]) < 4:
                continue
            s = similarite(wmots[i], bmots[j])
            if s >= 0.62:
                meilleurs.append((s, j))
        if not meilleurs:
            continue
        meilleurs.sort(reverse=True)
        if len(meilleurs) >= 3:
            continue                     # ambigu : pas d'ancrage
        s, jc = meilleurs[0]
        if jc > c + 60:
            jc = c + 60
        elif jc < c - 40:
            jc = c - 40
        c = jc
        centres[i] = jc
    if not centres:
        return [min(int(i * m / max(n, 1)), m - 1) for i in range(n)]
    # interpolation linéaire entre points d'ancrage pilotes
    ancres = sorted(centres.items())          # [(i, j), ...] croissant
    traj = []
    ia = 0
    for i in range(n):
        while ia + 1 < len(ancres) and ancres[ia + 1][0] <= i:
            ia += 1
        if i < ancres[0][0]:
            traj.append(ancres[0][1])
        elif ia + 1 >= len(ancres):
            traj.append(ancres[-1][1])
        else:
            (i0, j0), (i1, j1) = ancres[ia], ancres[ia + 1]
            t = (i - i0) / max(1, (i1 - i0))
            traj.append(max(0, min(m - 1, int(j0 + t * (j1 - j0)))))
    return traj


def aligner_dp_bande(wmots, bmots, traj, W=220):
    """DP en bande autour de la trajectoire pilote.
    Renvoie ops : [('M', i, j) | ('IW', i) | ('IB', j)] en ordre chrono."""
    n, m = len(wmots), len(bmots)
    NEG = float('-inf')
    # dp stocké par ligne (dict j->val) + choix pour le retour arrière
    dp_prev = {0: 0.0}
    bt = []            # bt[i] = dict j -> (choix, ...)
    for i in range(1, n + 1):
        c = traj[min(i - 1, n - 1)]
        j0 = max(0, c - W)
        j1 = min(m, c + W)
        cur = {}
        choix = {}
        for j in range(j0, j1 + 1):
            best, ch = NEG, None
            # M : appariement whisper i-1 ↔ livre j-1
            if j > 0:
                v0 = dp_prev.get(j - 1)
                if v0 is not None:
                    s = similarite(wmots[i - 1], bmots[j - 1])
                    if s >= SEUIL and v0 + s > best:
                        best, ch = v0 + s, 'M'
                # IW : mot whisper sauté
                v1 = dp_prev.get(j)
                if v1 is not None and v1 + GAP > best:
                    best, ch = v1 + GAP, 'IW'
                # IB : mot livre sauté (venant de la même ligne)
                v2 = cur.get(j - 1)
                if v2 is not None and v2 + GAP > best:
                    best, ch = v2 + GAP, 'IB'
            else:
                v1 = dp_prev.get(j)
                if v1 is not None and v1 + GAP > best:
                    best, ch = v1 + GAP, 'IW'
            if ch is not None:
                cur[j] = best
                choix[j] = ch
        if not cur:
            # bande perdue : on transporte la meilleure valeur du rang
            # précédent en la dégradant d'un saut (la trajectoire pilote
            # rend ce cas théoriquement impossible, c'est un garde-fou)
            base = (max(dp_prev.values()) if dp_prev else 0.0) + GAP
            cur = {j1: base}
            choix = {j1: 'IW'}
        dp_prev = cur
        bt.append(choix)
    # fin : meilleur j atteignable
    j_fin = max(dp_prev, key=lambda j: dp_prev[j]) if dp_prev else 0
    ops = []
    i, j = n, j_fin
    while i > 0:
        ch = bt[i - 1].get(j)
        if ch == 'M':
            ops.append(('M', i - 1, j - 1))
            i -= 1
            j -= 1
        elif ch == 'IW':
            ops.append(('IW', i - 1))
            i -= 1
        elif ch == 'IB':
            ops.append(('IB', None, j - 1))
            j -= 1
        elif j > 0:                      # hors bande : saut de livre
            ops.append(('IB', None, j - 1))
            j -= 1
        else:                            # hors bande en bordure gauche
            ops.append(('IW', i - 1))
            i -= 1
    ops.reverse()
    return ops


def repartir(a, b, c, longueurs):
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


def construire_timing(parle_normes, whisper_mots, ops, duree):
    times = [None] * len(parle_normes)
    for op, wi, bi in [o for o in ops if o[0] == 'M']:
        wm = whisper_mots[wi]
        conf = similarite(parle_normes[bi], wm['norme'])
        times[bi] = [wm['debut'], wm['fin'], conf, 'whisper']
    longueurs = [len(s) + 1 for s in parle_normes]
    ancrages = [k for k, t in enumerate(times) if t]
    if not ancrages:
        for k, (b, c) in enumerate(repartir(len(parle_normes), 0.0, duree,
                                            longueurs)):
            times[k] = [b, c, 0.0, 'uniforme']
        return times
    k0 = ancrages[0]
    if k0 > 0:
        t0 = min(times[k0][0], duree or times[k0][0])
        for k, (b, c) in enumerate(repartir(k0, 0.0, t0, longueurs[:k0])):
            times[k] = [b, c, 0.0, 'interpole']
    for x in range(len(ancrages) - 1):
        ka, kb = ancrages[x], ancrages[x + 1]
        if kb - ka > 1:
            b, c = times[ka][1], times[kb][0]
            for y, (b2, c2) in enumerate(
                    repartir(kb - ka - 1, b, c, longueurs[ka + 1:kb])):
                times[ka + 1 + y] = [b2, c2, 0.0, 'interpole']
    kd = ancrages[-1]
    if kd < len(parle_normes) - 1:
        b = times[kd][1]
        c = duree if duree > b else b + 2.0
        for y, (b2, c2) in enumerate(
                repartir(len(parle_normes) - 1 - kd, b, c,
                         longueurs[kd + 1:])):
            times[kd + 1 + y] = [b2, c2, 0.0, 'interpole']
    return times


def lisser(times):
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--livre", default="/home/z/my-project/travail/darsi1/livre_mots.json")
    ap.add_argument("--whisper", default="/home/z/my-project/travail/darsi1/transcription.json")
    ap.add_argument("--dossier", default="/home/z/my-project/travail/darsi1")
    ap.add_argument("--W", type=int, default=220, help="demi-largeur de bande")
    args = ap.parse_args()

    livre = json.load(open(args.livre, encoding="utf-8"))
    wh = json.load(open(args.whisper, encoding="utf-8"))
    mots = livre["mots"]
    duree = wh["duree"]

    wmots_bruts = wh["mots"]
    whisper_mots = []
    for w in wmots_bruts:
        n = normaliser(w["mot"])
        if n:
            whisper_mots.append({"norme": n, "debut": w["debut"],
                                 "fin": w["fin"]})

    # mots du livre utiles pour l'alignement (normalisation non vide)
    idx_parle = [i for i, m in enumerate(mots) if normaliser(m["texte"])]
    parle_normes = [normaliser(mots[i]["texte"]) for i in idx_parle]

    print(f"Alignement : {len(parle_normes)} mots livre ⟷ "
          f"{len(whisper_mots)} mots Whisper ({duree/60:.1f} min)...",
          flush=True)

    print("Passe pilote (trajectoire)...", flush=True)
    traj = passe_pilote([w["norme"] for w in whisper_mots], parle_normes)

    print("DP en bande...", flush=True)
    ops = aligner_dp_bande([w["norme"] for w in whisper_mots], parle_normes,
                           traj, W=args.W)
    nb_match = sum(1 for o in ops if o[0] == 'M')

    # ---- post-filtre : garder les matches en « runs » de lecture ---------
    # les matches ISOLÉS (aucun voisin dans ±25 mots du livre) sont du
    # bruit de l'ASR sur les passages en langue étrangère → retirés.
    pos_match = sorted((o[2], o[1]) for o in ops if o[0] == 'M')
    bi_voisins = {}
    for bi, wi in pos_match:
        bi_voisins[bi] = wi
    gardes = set()
    for bi in bi_voisins:
        nb_voisins = sum(1 for bj in bi_voisins if abs(bj - bi) <= 25)
        if nb_voisins >= 3:
            gardes.add(bi)
    ops = [o if (o[0] != 'M' or o[2] in gardes) else ('IB', None, o[2])
           for o in ops]
    nb_bruts = len(pos_match)
    nb_match = len(gardes)
    print(f"Après filtre de runs : {nb_match}/{nb_bruts} matches fiables",
          flush=True)
    print(f"Appariements directs : {nb_match}/{len(parle_normes)} "
          f"({100 * nb_match / max(1, len(parle_normes)):.1f} %)", flush=True)

    times = construire_timing(parle_normes, whisper_mots, ops, duree)
    lisser(times)

    # projection sur TOUS les mots du livre (décoratifs interpolés)
    t_parle = {idx_parle[q]: times[q] for q in range(len(idx_parle))}
    resultat = []
    dernier_fin = 0.0
    for i, m in enumerate(mots):
        if i in t_parle:
            b, c, conf, src = t_parle[i]
            resultat.append({"debut": round(b, 3), "fin": round(c, 3),
                             "confiance": round(conf, 3), "source": src})
            dernier_fin = c
        else:
            suiv = None
            for j in range(i + 1, len(mots)):
                if j in t_parle:
                    suiv = t_parle[j][0]
                    break
            b = dernier_fin
            c = suiv if (suiv and suiv > b) else b + 0.08
            resultat.append({"debut": round(b, 3), "fin": round(c, 3),
                             "confiance": 0.0, "source": "decoratif"})
            dernier_fin = max(dernier_fin, c)

    # ---- timing des LIGNES (unité de surlignage) -------------------------
    lignes_timing = {}
    for i, m in enumerate(mots):
        cle = (m["page"], m["ligne"])
        r = resultat[i]
        if cle not in lignes_timing:
            lignes_timing[cle] = {"page": m["page"], "n": m["ligne"],
                                  "debut": r["debut"], "fin": r["fin"]}
        else:
            L = lignes_timing[cle]
            L["debut"] = min(L["debut"], r["debut"])
            L["fin"] = max(L["fin"], r["fin"])

    # fusion des bbox des lignes (pour le surligneur)
    try:
        geo = json.load(open(args.livre.replace("livre_mots.json",
                                                "lignes.json"),
                             encoding="utf-8"))
        for L in geo["lignes"]:
            cle = (L["page"], L["n"])
            if cle in lignes_timing:
                lignes_timing[cle]["bbox"] = L["bbox"]
    except FileNotFoundError:
        pass

    # ---- exports ----------------------------------------------------------
    with open(f"{args.dossier}/synchronisation.csv", "w", encoding="utf-8",
              newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["mot", "debut", "fin", "page", "position", "texte"])
        for i, m in enumerate(mots):
            r = resultat[i]
            w.writerow([normaliser(m["texte"]), f"{r['debut']:.3f}",
                        f"{r['fin']:.3f}", m["page"], i, m["texte"]])

    complet = {
        "meta": {"duree": duree, "mots_livre": len(mots),
                 "mots_whisper": len(whisper_mots), "appariements": nb_match,
                 "couverture_pct": round(100 * nb_match /
                                         max(1, len(parle_normes)), 1)},
        "mots": [{**m, **resultat[i]} for i, m in enumerate(mots)],
    }
    with open(f"{args.dossier}/synchronisation_complet.json", "w",
              encoding="utf-8") as f:
        json.dump(complet, f, ensure_ascii=False, indent=1)

    with open(f"{args.dossier}/lignes_timing.json", "w",
              encoding="utf-8") as f:
        json.dump(sorted(lignes_timing.values(),
                         key=lambda L: (L["page"], L["n"])), f,
                  ensure_ascii=False, indent=1)

    # pages réellement couvertes (mots appariés à Whisper)
    pages_couv = sorted({mots[i]["page"] for i, r in enumerate(resultat)
                         if r["source"] == "whisper"})
    print(f"Pages couvertes par l'audio : {pages_couv}")
    dernier_mot = [mots[i] for i, r in enumerate(resultat)
                   if r["source"] == "whisper"]
    if dernier_mot:
        dm = dernier_mot[-1]
        print(f"Dernier mot lu : page {dm['page']}, ligne {dm['ligne']} "
              f"« {dm['texte']} » à {resultat[-1]['fin']:.0f}s "
              f"sur {duree:.0f}s d'audio")
    print(f"→ {args.dossier}/synchronisation.csv")
    print(f"→ {args.dossier}/synchronisation_complet.json")
    print(f"→ {args.dossier}/lignes_timing.json ({len(lignes_timing)} lignes)")


if __name__ == "__main__":
    main()
