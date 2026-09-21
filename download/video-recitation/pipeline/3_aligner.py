#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÉTAPE 3 — Détection des passages lus + alignement MOT À MOT (v3)
=================================================================

L'audio d'un dars contient TROIS types de parole :
  🔵 lecture      : l'arabe récité correspond au texte du livre → SURLIGNAGE
  ⚪ somali       : explication en somali                       → rien
  ⚪ hors_livre   : arabe (intro, explication) sans correspondance → rien

Style réel d'un dars : le cheikh lit UNE PHRASE arabe, puis l'explique en
somali, puis lit la phrase suivante… Whisper transcrit donc des blocs
MIXTES (arabe + somali déguisé en arabe), ce qui fragmente les
appariements. D'où la stratégie en DEUX PASSES :

  PASS 1 (stricte)  — ancrages exacts chaînés (LIS pondéré) + DP locales
                      + filtre de qualité exigeant → runs haute confiance.
  PASS 2 (rattrapage) — chaque « trou » entre deux runs actifs est un
                      candidat CONTINUE DE LECTURE : le cheikh a relu le
                      texte juste après l'endroit où il s'était arrêté.
                      On re-DS le trou contre la PLAGE DU LIVRE qui suit
                      le run précédent (et précède le suivant), avec un
                      seuil RELÂCHÉ + garde-fous anti-somali :
                        * p80 : au moins 25 % de mots appariés à ≥ 0.80
                          (une vraie lecture est bien transcrite en
                          majorité ; le somali déguisé plafonne à ~0.6) ;
                        * ancre_forte : un mot long (≥ 4 lettres)
                          apparié solidement.

Ensuite : interpolation des mots sautés, lissage, classification des
segments, timing.json + CSV (formats inchangés pour l'étape 4).
"""
import argparse
import csv
from pathlib import Path

from commun import (normaliser, similarite, est_recitable, charger_json,
                    sauver_json, charger_config, chemin_projet, duree_media)

# ------------------------------ PASS 1 (stricte, comme avant mais souple) --
SEUIL = 0.45           # similarité minimale d'un appariement DP
GAP = -0.28            # pénalité de saut (mot non apparié)
MIN_MOTS_RUN = 3
MIN_DUREE_RUN = 1.5
QUEUE = 0.6            # maintien du surlignage après le dernier mot (s)
EXT_MAX = 2.5          # extension max d'un mot jusqu'au suivant (s)
BANDE = 90             # demi-largeur de bande du DP local

# ------------------------------ PASS 2 (rattrapage des continuations) ------
SEUIL2 = 0.36          # seuil DP relâché
MEAN1 = 0.62           # filtre pass 1 : moyenne des similarités
MEAN2 = 0.55           # filtre pass 2 : moyenne des similarités
P80_MIN = 0.25         # part de mots appariés à ≥ 0.80 (garde anti-somali)
ANCRE_SC = 0.80        # score d'un appariement « solide »
LONGS1 = 0.50          # part de mots longs (≥3 lettres) — pass 1
LONGS2 = 0.42          # pass 2
SPAN1 = 1.45           # contiguïté max span/n — pass 1
SPAN2 = 1.75           # pass 2
MIN_MOTS2 = 3
MIN_DUREE2 = 1.2
TROU_WHISPER = 4       # mots Whisper non appariés tolérés dans un run
TROU_LIVRE = 3         # mots du livre sautés tolérés dans un run
MARGE_PLAGE = 60       # marge autour de la plage du livre pour la passe 2


# ------------------------------------------------------------ ancrages ---
def chercher_ancrages(w_norms, b_norms):
    """Chaîne monotone optimale de mots identiques (i↑, j↑).
    Renvoie [(i, j), …] triée par i. LIS pondéré (poids = 1 + longueur)."""
    pos_livre = {}
    for j, n in enumerate(b_norms):
        if len(n) >= 3:          # évite les fragments courts du somali déformé
            pos_livre.setdefault(n, []).append(j)

    candidats = []
    for i, n in enumerate(w_norms):
        if n and len(n) >= 3:
            for j in pos_livre.get(n, ()):
                candidats.append((i, j))
    candidats.sort()
    if not candidats:
        return []

    M = len(b_norms)
    fen_val = [0.0] * (M + 1)
    fen_idx = [None] * (M + 1)

    def query(j):                      # max poids avec j' <= j
        s, idx = 0.0, None
        k = j + 1
        while k > 0:
            if fen_val[k] > s:
                s, idx = fen_val[k], fen_idx[k]
            k -= k & (-k)
        return s, idx

    def maj(j, val, idx):
        k = j + 1
        while k <= M:
            if val > fen_val[k]:
                fen_val[k], fen_idx[k] = val, idx
            k += k & (-k)

    total = {}                          # idx_candidat -> (poids, prev_idx)
    n_c = len(candidats)
    debut = 0
    while debut < n_c:
        fin = debut
        while fin < n_c and candidats[fin][0] == candidats[debut][0]:
            fin += 1
        # 1) évaluer tout le groupe i avec l'état Fenwick courant
        for c in range(debut, fin):
            i, j = candidats[c]
            poids, prev = query(j - 1)
            total[c] = (poids + 1 + len(w_norms[i]), prev)
        # 2) puis injecter le groupe dans le Fenwick
        for c in range(debut, fin):
            i, j = candidats[c]
            maj(j, total[c][0], c)
        debut = fin

    # reconstruction de la meilleure chaîne
    best_c, best_w = None, 0.0
    for c, (w, _p) in total.items():
        if w > best_w:
            best_w, best_c = w, c
    chaine = []
    while best_c is not None:
        i, j = candidats[best_c]
        chaine.append((i, j))
        best_c = total[best_c][1]
    chaine.reverse()
    return chaine


# ---------------------------------------------------------- DP locale ----
def dp_locale(wmots, bmots, seuil=SEUIL, gap=GAP, bande=None):
    """Alignement local (Needleman-Wunsch sous bande).
    Renvoie des opérations : ('M', wi_local, bj_local) / ('IW', wi) /
    ('IB', bj). Les indices sont LOCAUX (0-based dans les sous-listes)."""
    n, m = len(wmots), len(bmots)
    if n == 0 or m == 0:
        return [('IW', i) for i in range(n)] + [('IB', j) for j in range(m)]
    if bande is None:
        bande = max(BANDE, int(0.4 * max(n, m)))

    NEG = float('-inf')
    dp = [[NEG] * (m + 1) for _ in range(n + 1)]
    bt = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for j in range(1, min(m, bande) + 1):
        dp[0][j] = dp[0][j - 1] + gap
        bt[0][j] = 'IB'
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] + gap
        bt[i][0] = 'IW'

    for i in range(1, n + 1):
        j0 = max(1, i - bande)
        j1 = min(m, i + bande)
        for j in range(j0, j1 + 1):
            best, choix = NEG, None
            if dp[i - 1][j - 1] > NEG:
                s = similarite(wmots[i - 1], bmots[j - 1])
                if s >= seuil:
                    v = dp[i - 1][j - 1] + s
                    if v > best:
                        best, choix = v, 'M'
            if dp[i - 1][j] > NEG:
                v = dp[i - 1][j] + gap
                if v > best:
                    best, choix = v, 'IW'
            if dp[i][j - 1] > NEG:
                v = dp[i][j - 1] + gap
                if v > best:
                    best, choix = v, 'IB'
            dp[i][j] = best
            bt[i][j] = choix

    if dp[n][m] == NEG:
        bande2 = max(n, m) + 2
        if bande2 > bande:
            return dp_locale(wmots, bmots, seuil, gap, bande2)

    ops, i, j = [], n, m
    while i > 0 or j > 0:
        c = bt[i][j]
        if c == 'M':
            ops.append(('M', i - 1, j - 1)); i -= 1; j -= 1
        elif c == 'IW':
            ops.append(('IW', i - 1)); i -= 1
        elif c == 'IB':
            ops.append(('IB', j - 1)); j -= 1
        else:
            if i > 0:
                ops.append(('IW', i - 1)); i -= 1
            else:
                ops.append(('IB', j - 1)); j -= 1
    ops.reverse()
    return ops


def repartir(a, b, c, longueurs):
    """Répartit [b, c] sur `a` mots proportionnellement à leurs longueurs."""
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


def lisser(times):
    """Monotonie : debut >= fin du précédent, fin > debut."""
    prev_fin = 0.0
    for idx, t in enumerate(times):
        if not t:
            continue
        b, c = t[0], t[1]
        if b < prev_fin:
            decal = prev_fin - b
            b, c = b + decal, max(c + decal, b + 0.06)
        if c <= b:
            c = b + 0.06
        times[idx] = (b, c) + tuple(t[2:])
        prev_fin = c


# -------------------------------------------------- qualité d'un run -----
def qualite_run(ps, w_mots, b_norms):
    """ps = [(wi, bj, sc)] trié par wi. Renvoie le dictionnaire de mesures."""
    n = len(ps)
    d0 = w_mots[ps[0][0]]['debut']
    d1 = w_mots[ps[-1][0]]['fin']
    mean = sum(sc for _w, _b, sc in ps) / n
    p80 = sum(1 for _w, _b, sc in ps if sc >= 0.80) / n
    dur = d1 - d0
    j0, j1 = ps[0][1], ps[-1][1]
    span = j1 - j0 + 1
    longs = sum(1 for _w, bj, _s in ps if len(b_norms[bj]) >= 3) / n
    ancre_forte = any(len(b_norms[bj]) >= 4 and sc >= ANCRE_SC
                      for _w, bj, sc in ps)
    return {'n': n, 'debut': d0, 'fin': d1, 'mean': mean, 'p80': p80,
            'dur': dur, 'span': span, 'longs': longs,
            'ancre_forte': ancre_forte}


def filtre_strict(q):
    """PASS 1 : critères exigeants (coïncidences isolées jamais activées)."""
    return ((q['n'] >= 4 and q['mean'] >= MEAN1 and q['dur'] >= 2.0
             and q['span'] / q['n'] <= SPAN1 and q['longs'] >= LONGS1
             and q['ancre_forte'])
            or
            (q['n'] == 3 and q['mean'] >= 0.90 and q['p80'] >= 0.66
             and q['dur'] >= 1.5 and q['span'] / q['n'] <= SPAN1
             and q['longs'] >= LONGS1 and q['ancre_forte']))


def filtre_souple(q):
    """PASS 2 : relâché MAIS protégé contre le somali déguisé en arabe.
    Une vraie lecture = la majorité des mots bien transcrits (p80 élevé),
    un faux positif somali = quelques coïncidences noyées dans du bruit."""
    return (q['n'] >= MIN_MOTS2 and q['mean'] >= MEAN2
            and q['dur'] >= MIN_DUREE2
            and q['span'] / q['n'] <= SPAN2
            and q['longs'] >= LONGS2
            and q['p80'] >= P80_MIN
            and q['ancre_forte'])


# ------------------------------------------------- runs par temps --------
def construire_runs(paires_dict, w_mots):
    """Regroupe les appariements en runs par CONTINUITÉ TEMPORELLE et
    monotonie dans le livre — pas par comptage de trous.
    Deux appariements (w1,b1) → (w2,b2) restent dans le même run si :
      * dt = w2.début − w1.fin ≤ 6 s   (la récitation continue) ;
      * le livre avance : b2 ≥ b1 − 2 (léger bruit d'ordre toléré) ;
      * la vitesse de progression est plausible : b2 − b1 ≤ dt/0.15 + 5
        (lecture rapide ≈ 6–7 mots/s max).
    Un mot « poubelle » de Whisper (somali déguisé) entre deux mots lus ne
    casse PLUS le run — c'est ce qui fragmentait tout en n=1."""
    runs = []
    for wi, (bj, sc) in sorted(paires_dict.items()):
        if runs:
            pw, pb, _psc = runs[-1][-1]
            dt = w_mots[wi]['debut'] - w_mots[pw]['fin']
            dj = bj - pb
            if dt <= 6.0 and dj >= -2 and dj <= dt / 0.15 + 5:
                runs[-1].append((wi, bj, sc))
                continue
        runs.append([(wi, bj, sc)])
    return runs


def fusionner_runs_proches(runs, w_mots):
    """Fusionne les runs voisins (gap temporel ≤ 6 s, avance du livre ≤ 20
    mots, pas de retour en arrière) : réassemble les fragments d'une même
    phrase séparés par quelques mots non transcrits."""
    out = []
    for r in runs:
        if out:
            dern = out[-1][-1]
            prem = r[0]
            dt = w_mots[prem[0]]['debut'] - w_mots[dern[0]]['fin']
            dj = prem[1] - dern[1]
            if dt <= 6.0 and 0 <= dj <= 20:
                out[-1] += r
                continue
        out.append(list(r))
    return out


# ------------------------------------------------------------- main ------
def main():
    ap = argparse.ArgumentParser(
        description="Détection des lectures + alignement (étape 3)")
    ap.add_argument('--config', default='config.json')
    ap.add_argument('--dars', required=True)
    ap.add_argument('--travail', default=None)
    args = ap.parse_args()

    cfg = charger_config(args.config)
    travail = chemin_projet(cfg, args.travail or cfg.get('travail', 'travail'))
    a_cfg = cfg.get('alignement', {})
    global SEUIL, GAP, MIN_MOTS_RUN, MIN_DUREE_RUN, QUEUE
    global SEUIL2, MEAN1, MEAN2, P80_MIN, ANCRE_SC
    SEUIL = a_cfg.get('seuil', SEUIL)
    GAP = a_cfg.get('gap', GAP)
    MIN_MOTS_RUN = a_cfg.get('min_mots_run', MIN_MOTS_RUN)
    MIN_DUREE_RUN = a_cfg.get('min_duree_run', MIN_DUREE_RUN)
    QUEUE = a_cfg.get('queue', QUEUE)
    SEUIL2 = a_cfg.get('seuil2', SEUIL2)
    MEAN1 = a_cfg.get('mean1', MEAN1)
    MEAN2 = a_cfg.get('mean2', MEAN2)
    P80_MIN = a_cfg.get('p80_min', P80_MIN)
    ANCRE_SC = a_cfg.get('ancre_sc', ANCRE_SC)

    pages = charger_json(Path(travail) / 'pages.json')
    trans = charger_json(Path(travail) / args.dars / 'transcription.json')

    dars = cfg['darses'][args.dars]
    p1, p2 = dars['pages']
    duree = trans.get('duree') or duree_media(trans.get('audio', ''))

    # ---- mots du livre sur la plage de la section ------------------------
    mots = []
    for p in pages['pages']:
        if not (p1 <= p['numero'] <= p2):
            continue
        for m in p['mots']:
            m['page'] = p['numero']
            mots.append(m)
    parle_idx = [i for i, m in enumerate(mots)
                 if est_recitable(m['texte']) and normaliser(m['texte'])]
    b_norms = [normaliser(mots[i]['texte']) for i in parle_idx]
    parle_pos = {idx_book: q for q, idx_book in enumerate(parle_idx)}
    parle_set = set(parle_idx)

    # ---- mots Whisper ------------------------------------------------------
    w_mots = trans['mots']
    w_norms = []
    for w in w_mots:
        n = normaliser(w['mot'])
        w_norms.append(n if (n and est_recitable(w['mot'])) else None)
    N, M = len(w_norms), len(b_norms)
    print(f"« {args.dars} » : {M} mots du livre (pages {p1}–{p2}) ⟷ "
          f"{N} mots Whisper ({duree / 60:.1f} min)")

    # =========================== PASS 1 =====================================
    ancrages = chercher_ancrages(w_norms, b_norms)
    print(f"[P1] ancrages exacts chaînés : {len(ancrages)}")

    paires = {}                     # wi -> (bj, score)
    bornes = [(-1, -1)] + [tuple(a) for a in ancrages] + [(N, M)]
    for (i1, j1), (i2, j2) in zip(bornes, bornes[1:]):
        w_r = list(range(i1 + 1, i2))
        b_r = list(range(j1 + 1, j2))
        if not w_r or not b_r:
            continue
        n_r = len(w_r)
        if (i1, j1) == (-1, -1):            # tête : garder la FIN
            b_r = b_r[-(n_r + 400):] if len(b_r) > n_r + 400 else b_r
        else:                               # intervalle / queue : garder le DÉBUT
            b_r = b_r[:n_r + 400] if len(b_r) > n_r + 400 else b_r
        sous_w = [w_norms[i] for i in w_r]
        sous_b = [b_norms[j] for j in b_r]
        ops = dp_locale(sous_w, sous_b, seuil=SEUIL)
        for op in ops:
            if op[0] == 'M':
                paires[w_r[op[1]]] = (b_r[op[2]],
                                      similarite(sous_w[op[1]],
                                                 sous_b[op[2]]))
    for i, j in ancrages:
        paires[i] = (j, 1.0)
    print(f"[P1] appariements totaux : {len(paires)}")

    # ---- runs de pass 1 (continuité temporelle + fusion des fragments) ----
    runs = construire_runs(paires, w_mots)
    runs = fusionner_runs_proches(runs, w_mots)

    actifs = []
    for r in runs:
        ps = sorted(r, key=lambda x: x[0])
        q = qualite_run(ps, w_mots, b_norms)
        r_dict = {'paires': ps, **q}
        r_dict['actif'] = filtre_strict(q)
        if r_dict['actif']:
            actifs.append(r_dict)
    print(f"[P1] runs : {len(runs)} au total, {len(actifs)} ACTIVÉS")

    # =========================== PASS 2 =====================================
    # Chaque trou Whisper entre deux runs actifs (ou avant le 1er / après
    # le dernier) est re-DSé contre la plage du livre qui suit/précède.
    paires2 = {}
    ancres_actifs = sorted(
        [(min(w for w, _b, _s in r['paires']),
          max(w for w, _b, _s in r['paires']),
          min(b for _w, b, _s in r['paires']),
          max(b for _w, b, _s in r['paires'])) for r in actifs])

    zones = []                       # (wi_a, wi_b, bj_a, bj_b) candidats
    if ancres_actifs:
        # tête
        w0 = ancres_actifs[0][0]
        if w0 > 0:
            zones.append((0, w0 - 1, 0, max(0, ancres_actifs[0][2] - 1)))
        # intervalles
        for (wa0, wa1, ba0, ba1), (wb0, wb1, bb0, bb1) in \
                zip(ancres_actifs, ancres_actifs[1:]):
            if wb0 - wa1 - 1 > 0:
                zones.append((wa1 + 1, wb0 - 1, min(M - 1, ba1 + 1),
                              max(0, bb0 - 1)))
        # queue
        wL = ancres_actifs[-1][1]
        if wL < N - 1:
            zones.append((wL + 1, N - 1, min(M - 1, ancres_actifs[-1][3] + 1),
                          M - 1))

    n_new = 0
    for wi_a, wi_b, bj_a, bj_b in zones:
        if bj_b < bj_a:
            continue
        # plage du livre élargie (le cheikh peut avoir sauté quelques lignes)
        bj_a2 = max(0, bj_a - MARGE_PLAGE)
        bj_b2 = min(M - 1, bj_b + MARGE_PLAGE)
        w_r = list(range(wi_a, wi_b + 1))
        b_r = list(range(bj_a2, bj_b2 + 1))
        if len(b_r) > len(w_r) + 600:      # borne le coût
            if wi_a == 0:                  # tête : le début du dars est près
                b_r = b_r[-(len(w_r) + 600):]   # du 1er run (position finale)
            else:                          # intervalle / queue : près du run
                b_r = b_r[:len(w_r) + 600]      # précédent (position initiale)
        sous_w = [w_norms[i] for i in w_r]
        sous_b = [b_norms[j] for j in b_r]
        ops = dp_locale(sous_w, sous_b, seuil=SEUIL2)
        loc = {}
        for op in ops:
            if op[0] == 'M':
                loc[w_r[op[1]]] = (b_r[op[2]],
                                   similarite(sous_w[op[1]], sous_b[op[2]]))
        if not loc:
            continue
        ps = sorted([(wi, bj, sc) for wi, (bj, sc) in loc.items()])
        # découpe + fusion par continuité temporelle
        sous_runs = construire_runs({wi: (bj, sc) for wi, bj, sc in ps},
                                    w_mots)
        sous_runs = fusionner_runs_proches(sous_runs, w_mots)
        for psr in sous_runs:
            q = qualite_run(psr, w_mots, b_norms)
            if filtre_souple(q):
                actifs.append({'paires': psr, **q, 'actif': True,
                               'passe': 2})
                paires2.update({wi: (bj, sc) for wi, bj, sc in psr})
                n_new += 1
    if n_new:
        actifs.sort(key=lambda r: r['debut'])
    print(f"[P2] continuations récupérées : {n_new} runs supplémentaires")

    # ---- fusion des runs voisins (pass 1 + pass 2) --------------------------
    tous = [list(r['paires']) for r in actifs]
    fusionnes = fusionner_runs_proches(tous, w_mots)
    # re-évalue la qualité après fusion
    actifs = []
    for r in fusionnes:
        ps = sorted(r, key=lambda x: x[0])
        q = qualite_run(ps, w_mots, b_norms)
        r_dict = {'paires': ps, **q}
        r_dict['actif'] = filtre_strict(q) or filtre_souple(q)
        if r_dict['actif']:
            actifs.append(r_dict)
    print(f"[F] runs ACTIVÉS après fusion : {len(actifs)}")
    total_lecture = sum(r['dur'] for r in actifs)
    print(f"[F] temps de lecture détecté : {total_lecture:.0f}s "
          f"({100 * total_lecture / max(duree, 1):.1f} % de {duree / 60:.0f} min)")
    for k, r in enumerate(actifs):
        j0, j1 = r['paires'][0][1], r['paires'][-1][1]
        pg0 = mots[parle_idx[j0]]['page']
        pg1 = mots[parle_idx[j1]]['page']
        print(f"   🔵 run {k + 1}: {r['debut']:7.1f}s → {r['fin']:7.1f}s  "
              f"pages {pg0}–{pg1}  ({r['n']} mots, moy {r['mean']:.2f}, "
              f"p80 {r['p80']:.2f})")

    # ---- 4) timing des mots à l'intérieur des runs actifs -----------------
    times = [None] * M
    run_of = [None] * M
    for k, r in enumerate(actifs):
        ps = sorted(r['paires'], key=lambda x: x[1])
        for wi, bj, sc in ps:
            times[bj] = (w_mots[wi]['debut'], w_mots[wi]['fin'], sc, 'whisper')
            run_of[bj] = k
        # interpolation des mots du livre sautés à l'intérieur du run
        for (wia, bja, _), (wib, bjb, _) in zip(ps, ps[1:]):
            trou = bjb - bja - 1
            if trou > 0:
                t0 = w_mots[wia]['fin']
                t1 = w_mots[wib]['debut']
                seg = range(bja + 1, bjb)
                L = [len(b_norms[j]) + 1 for j in seg]
                for y, (b, c) in enumerate(repartir(trou, t0, t1, L)):
                    j = bja + 1 + y
                    if times[j] is None:
                        times[j] = (b, c, 0.0, 'interpole')
                        run_of[j] = k
        # lissage dans l'ordre du livre
        idxs = [bj for _wi, bj, _ in ps]
        for j in range(idxs[0], idxs[-1] + 1):
            if run_of[j] == k and times[j] is None:
                times[j] = (times[j - 1][1], times[j - 1][1] + 0.06,
                            0.0, 'interpole')
                run_of[j] = k
        bloc = [times[j] for j in range(idxs[0], idxs[-1] + 1)
                if run_of[j] == k]
        lisser(bloc)
        z = 0
        for j in range(idxs[0], idxs[-1] + 1):
            if run_of[j] == k:
                times[j] = bloc[z]
                z += 1

    # extension : chaque mot tient jusqu'au suivant (pas de clignotement)
    for k, r in enumerate(actifs):
        ps = sorted(r['paires'], key=lambda x: x[1])
        j0, j1 = ps[0][1], ps[-1][1]
        seq = [j for j in range(j0, j1 + 1) if run_of[j] == k]
        for a, b in zip(seq, seq[1:]):
            fa = times[a][1]
            db = times[b][0]
            if db > fa:
                times[a] = (times[a][0], min(fa + EXT_MAX, db),
                            times[a][2], times[a][3])
            elif times[b][1] > fa:
                times[a] = (times[a][0], fa, times[a][2], times[a][3])
        dern = times[seq[-1]]
        times[seq[-1]] = (dern[0], dern[1] + QUEUE, dern[2], dern[3])

    # ---- 5) classification des segments de l'audio ------------------------
    dans_run = set()
    for k, r in enumerate(actifs):
        ps = sorted(r['paires'], key=lambda x: x[0])
        wi0, wi1 = ps[0][0], ps[-1][0]
        for wi in range(wi0, wi1 + 1):     # mots sandwich inclus
            dans_run.add(wi)

    classes = []
    for wi, w in enumerate(w_mots):
        if wi in dans_run:
            classes.append('lecture')
            continue
        mot = w['mot'] or ''
        a_ar = est_recitable(mot)
        a_lat = any('a' <= ch.lower() <= 'z' for ch in mot)
        if a_ar and normaliser(mot):
            classes.append('hors_livre')
        elif a_lat:
            classes.append('somali')
        else:
            classes.append(classes[-1] if classes else 'hors_livre')

    segments = []
    for wi, cl in enumerate(classes):
        w = w_mots[wi]
        if segments and segments[-1]['type'] == cl and \
                w['debut'] - segments[-1]['fin'] < 2.0:
            segments[-1]['fin'] = w['fin']
            segments[-1]['n_mots'] += 1
            if len(segments[-1]['mots_txt']) < 12:
                segments[-1]['mots_txt'].append(w['mot'])
        else:
            segments.append({'type': cl, 'debut': w['debut'],
                             'fin': w['fin'], 'n_mots': 1,
                             'mots_txt': [w['mot']]})

    durees = {'lecture': 0.0, 'somali': 0.0, 'hors_livre': 0.0}
    for s in segments:
        durees[s['type']] += s['fin'] - s['debut']
    tot = sum(durees.values()) or 1.0
    print("chronologie :")
    for t in ('lecture', 'somali', 'hors_livre'):
        print(f"   {t:<11} {durees[t]:7.1f}s ({100 * durees[t] / tot:4.1f} %)")

    # ---- 6) timing.json ----------------------------------------------------
    timing, stats = [], {'whisper': 0, 'interpole': 0, 'hors_lecture': 0,
                         'hors_texte': 0}
    for i, m in enumerate(mots):
        entree = {'page': m['page'],
                  'position': m['position'], 'ligne': m.get('ligne', 0),
                  'texte': m['texte'], 'norme': normaliser(m['texte']),
                  'x0': round(m['x0'], 2), 'y0': round(m['y0'], 2),
                  'x1': round(m['x1'], 2), 'y1': round(m['y1'], 2)}
        q = None
        if i in parle_set:
            q = parle_pos[i]
        if q is not None and times[q] is not None:
            b, c, conf, src = times[q]
            entree.update(debut=round(b, 3), fin=round(c, 3),
                          confiance=round(conf, 3), etat=src,
                          run=(run_of[q] + 1) if run_of[q] is not None else None)
            stats[src] += 1
        elif q is None:
            prec = timing[-1] if timing else None
            b = prec['fin'] if prec and prec.get('fin') else 0.0
            entree.update(debut=round(b, 3), fin=round(b + 0.08, 3),
                          confiance=0.0, etat='hors_texte', run=None)
            stats['hors_texte'] += 1
        else:
            entree.update(debut=None, fin=None, confiance=0.0,
                          etat='hors_lecture', run=None)
            stats['hors_lecture'] += 1
        timing.append(entree)

    resume_runs = []
    for k, r in enumerate(actifs):
        ps = r['paires']
        j0, j1 = ps[0][1], ps[-1][1]
        resume_runs.append({
            'run': k + 1, 'debut': round(r['debut'], 3),
            'fin': round(r['fin'], 3), 'n_mots': len(ps),
            'page_debut': mots[parle_idx[j0]]['page'],
            'page_fin': mots[parle_idx[j1]]['page'],
            'texte': ' '.join(w_mots[wi]['mot'] for wi, _b, _s in ps[:6])})

    sortie = {'dars': args.dars, 'pages': [p1, p2],
              'duree': round(duree, 3),
              'params': {'seuil': SEUIL, 'gap': GAP,
                         'min_mots_run': MIN_MOTS_RUN,
                         'min_duree_run': MIN_DUREE_RUN,
                         'seuil2': SEUIL2, 'mean1': MEAN1, 'mean2': MEAN2,
                         'p80_min': P80_MIN},
              'stats': {'mots_livre': len(mots),
                        'mots_recitables': M, 'mots_whisper': N,
                        'appariements': len(paires) + len(paires2),
                        'runs_actifs': len(actifs), 'etats': stats},
              'runs': resume_runs,
              'segments': [{'type': s['type'], 'debut': round(s['debut'], 3),
                            'fin': round(s['fin'], 3),
                            'n_mots': s['n_mots'],
                            'texte': ' '.join(s['mots_txt'])}
                           for s in segments],
              'mots': timing}
    chemin = Path(travail) / args.dars / 'timing.json'
    sauver_json(chemin, sortie)

    # ---- 7) CSV ------------------------------------------------------------
    dossier_sortie = chemin_projet(cfg, cfg.get('sortie', 'sortie'))
    dossier_sortie.mkdir(parents=True, exist_ok=True)

    csv_sync = dossier_sortie / f"{args.dars}_synchronisation.csv"
    with open(csv_sync, 'w', encoding='utf-8', newline='') as f:
        wc = csv.writer(f, delimiter=';')
        wc.writerow(['mot', 'debut', 'fin', 'page', 'position', 'texte'])
        for t in timing:
            if t['etat'] in ('whisper', 'interpole') and t['debut'] is not None:
                wc.writerow([t['norme'], f"{t['debut']:.3f}",
                             f"{t['fin']:.3f}", t['page'], t['position'],
                             t['texte']])

    csv_seg = dossier_sortie / f"{args.dars}_segments.csv"
    with open(csv_seg, 'w', encoding='utf-8', newline='') as f:
        wc = csv.writer(f, delimiter=';')
        wc.writerow(['type', 'debut', 'fin', 'n_mots', 'texte'])
        for s in segments:
            wc.writerow([s['type'], f"{s['debut']:.2f}", f"{s['fin']:.2f}",
                         s['n_mots'], ' '.join(s['mots_txt'])[:90]])

    nb_surligne = stats['whisper'] + stats['interpole']
    print(f"✔ {nb_surligne} mots du livre seront surlignés "
          f"({stats['whisper']} directs, {stats['interpole']} interpolés) "
          f"sur {M} mots récitable — le reste est laissé sans surlignage")
    print(f"→ {chemin}")
    print(f"→ {csv_sync}")
    print(f"→ {csv_seg}")


if __name__ == '__main__':
    main()
