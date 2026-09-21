#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÉTAPE 1 — Extraction du PDF : pages réelles (PNG) + mots avec coordonnées
=========================================================================
- Chaque page est rendue en PNG : c'est LA PAGE RÉELLE du livre qui sera
  affichée à droite de la vidéo (aucune remise en page, aucun texte refait).
- Les mots sont reconstruits à partir des CARACTÈRES du PDF triés
  spatialement (de droite à gauche) puis regroupés par écart horizontal.
  → robuste même si le PDF sort les glyphes dans le désordre.
- Les mots servent uniquement à l'ALIGNEMENT avec l'audio ; le texte du
  livre reste la référence exacte.

Sortie :
  travail/pages.json
  travail/pages/page_NNN.png
"""
import argparse
from pathlib import Path

import fitz  # PyMuPDF

from commun import (normaliser, est_recitable, sauver_json,
                    charger_config, chemin_projet)


def grouper_caracteres(page):
    """Collecte les caractères de la page, groupés par objet 'ligne' du PDF."""
    d = page.get_text('rawdict',
                      flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES)
    groupes = []
    for bloc in d.get('blocks', []):
        if bloc.get('type') != 0:
            continue
        for line in bloc.get('lines', []):
            chars = []
            for span in line.get('spans', []):
                for ch in span.get('chars', []):
                    if ch['c'].strip():                      # ignore espaces
                        chars.append((ch['bbox'], ch['c']))
            if chars:
                groupes.append(chars)
    return groupes


def fusionner_en_rangees(groupes, tol=0.5):
    """Fusionne les objets 'ligne' qui se chevauchent verticalement
    (certaines PDFs émettent une ligne par mot) -> rangees visuelles."""
    groupes = sorted(groupes,
                     key=lambda c: min(b[1] for b, _ in c))
    rangees = []
    for chars in groupes:
        y0 = min(b[1] for b, _ in chars)
        y1 = max(b[3] for b, _ in chars)
        placee = False
        for r in rangees:
            # chevauchement vertical > 50% de la plus petite hauteur ?
            ov = min(r['y1'], y1) - max(r['y0'], y0)
            hh = min(r['y1'] - r['y0'], y1 - y0) or 1.0
            if ov > tol * hh:
                r['chars'] += chars
                r['y0'] = min(r['y0'], y0)
                r['y1'] = max(r['y1'], y1)
                placee = True
                break
        if not placee:
            rangees.append({'chars': list(chars), 'y0': y0, 'y1': y1})
    rangees.sort(key=lambda r: r['y0'])
    return rangees


RE_MARQUE = None  # défini ci-dessous via plages Unicode


def est_marque(c):
    """Diacritique / signe coranique (ne fait pas avancer la ligne de base)."""
    o = ord(c)
    return (0x0610 <= o <= 0x061A or 0x064B <= o <= 0x065F or
            o in (0x0670,) or 0x06D6 <= o <= 0x06ED)


def grouper_chevauchement(chars_triees):
    """Regroupe les glyphes dont les bbox se chevauchent fortement
    (ligatures empilées type لله) — l'ordre FLUX est conservé À
    L'INTÉRIEUR d'un groupe, restaurant l'ordre logique même si les
    x sont quasi égaux. À n'utiliser qu'À L'INTÉRIEUR d'un mot."""
    groupes = []
    for bbox, c in chars_triees:
        place = False
        if groupes:
            g = groupes[-1]
            gx0 = min(b[0] for b, _ in g)
            gx1 = max(b[2] for b, _ in g)
            ov = min(gx1, bbox[2]) - max(gx0, bbox[0])
            w = min(gx1 - gx0, bbox[2] - bbox[0])
            if w > 0 and ov > 0.45 * w:
                g.append((bbox, c))
                place = True
        if not place:
            groupes.append([(bbox, c)])
    return groupes


def seuil_otsu(gaps, largeur_med):
    """Seuil de séparation des mots : recherche de la PREMIÈRE séparation
    propre en parcourant les écarts croissants (bimodalité stricte :
    classe haute ≥ 1 pt et ≥ 2× la classe basse + 0,3).
    On veut séparer intra-mot (petit) de inter-mots (grand), même quand
    des trous de ponctuation bien plus grands existent plus haut."""
    pos = sorted(g for g in gaps if g > 0)
    fallback = max(1.0, 0.55 * largeur_med)
    if len(pos) < 3:
        return fallback
    for i in range(1, len(pos)):
        dessous, dessus = pos[:i], pos[i:]
        if min(dessus) >= 1.0 and min(dessus) >= 2.0 * max(dessous) + 0.3:
            return max(1.0, (max(dessous) + min(dessus)) / 2.0)
    return fallback


def seuil_de_rangee(chars, largeur_med):
    """Compatibilité : seuil via Otsu sur les écarts bruts de la rangee."""
    gaps = []
    for (b1, _c1), (b2, _c2) in zip(chars, chars[1:]):
        gaps.append(b1[0] - b2[2])           # x0 precedent - x1 suivant (RTL)
    return seuil_otsu(gaps, largeur_med)


def mots_de_rangee(chars):
    """Reconstruit les mots d'une rangee :
      1. tri spatial RTL des LETTRES DE BASE (tie-break = ordre flux) ;
      2. frontières de mots par seuil d'Otsu sur les écarts entre lettres
         (les diacritiques ne participent JAMAIS aux frontières) ;
      3. à l'intérieur de chaque mot : regroupement des glyphes
         chevauchants (ligatures empilées) pour l'ordre logique ;
      4. les diacritiques sont rattachés au mot le plus proche."""
    base = [t for t in chars if not est_marque(t[1])]
    marques = [t for t in chars if est_marque(t[1])]
    base = sorted(base, key=lambda t: (-t[0][2], t[0][0]))
    if not base:
        return []

    larges = sorted(b[2] - b[0] for b, c in base
                    if '\u0621' <= c <= '\u064A')
    med = larges[len(larges) // 2] if larges else 4.0

    # --- frontières de mots sur les lettres de base -----------------------
    gaps = []
    for (b1, _c1), (b2, _c2) in zip(base, base[1:]):
        gaps.append(b1[0] - b2[2])           # x0 precedent - x1 suivant (RTL)
    seuil = seuil_otsu(gaps, med)

    sacs = []                                # un sac = un mot en construction
    for t in base:
        if sacs and (sacs[-1]['x0'] - t[0][2]) <= seuil:
            s = sacs[-1]
            s['chars'].append(t)
            s['x0'] = min(s['x0'], t[0][0])
            s['x1'] = max(s['x1'], t[0][2])
            s['y0'] = min(s['y0'], t[0][1])
            s['y1'] = max(s['y1'], t[0][3])
        else:
            sacs.append({'chars': [t], 'x0': t[0][0], 'y0': t[0][1],
                         'x1': t[0][2], 'y1': t[0][3]})

    # --- texte de chaque mot : ordre logique via ligatures regroupées ------
    mots = []
    for s in sacs:
        cs = sorted(s['chars'], key=lambda t: (-t[0][2], t[0][0]))
        groupes = grouper_chevauchement(cs)
        texte = ''.join(c for _, c in
                        [t for g in groupes for t in g])
        mots.append({'texte': texte, 'x0': s['x0'], 'y0': s['y0'],
                     'x1': s['x1'], 'y1': s['y1']})

    # --- rattachement des diacritiques ------------------------------------
    for bbox, c in marques:
        cx = (bbox[0] + bbox[2]) / 2.0
        best, best_d = None, None
        for m in mots:
            d = max(m['x0'] - cx, 0.0, cx - m['x1'])
            if best_d is None or d < best_d:
                best, best_d = m, d
        if best is not None and best_d <= med:
            best['texte'] += c
            best['x0'] = min(best['x0'], bbox[0])
            best['y0'] = min(best['y0'], bbox[1])
            best['x1'] = max(best['x1'], bbox[2])
            best['y1'] = max(best['y1'], bbox[3])
    return mots


def extraire_page(page, numero):
    """Une page -> dict {numero, image, mots, lignes}."""
    rangees = fusionner_en_rangees(grouper_caracteres(page))
    mots, lignes = [], []
    for idx, r in enumerate(rangees):
        ms = mots_de_rangee(r['chars'])
        if not ms:
            continue
        x0 = min(m['x0'] for m in ms)
        y0 = min(m['y0'] for m in ms)
        x1 = max(m['x1'] for m in ms)
        y1 = max(m['y1'] for m in ms)
        lignes.append({'index': idx, 'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1,
                       'positions': []})
        for m in ms:
            m['position'] = len(mots)
            m['ligne'] = idx
            lignes[-1]['positions'].append(len(mots))
            mots.append(m)
    return {
        'numero': numero,
        'largeur_pt': round(page.rect.width, 2),
        'hauteur_pt': round(page.rect.height, 2),
        'mots': mots,
        'lignes': lignes,
    }


def main():
    ap = argparse.ArgumentParser(
        description="Extraction pages réelles + mots (étape 1)")
    ap.add_argument('--config', default='config.json')
    ap.add_argument('--pdf', default=None, help='override du PDF de la config')
    ap.add_argument('--debut', type=int, default=None, help='1re page (1-based)')
    ap.add_argument('--fin', type=int, default=None, help='dernière page incluse')
    ap.add_argument('--dpi', type=int, default=None)
    ap.add_argument('--travail', default=None)
    args = ap.parse_args()

    cfg = charger_config(args.config)
    pdf = chemin_projet(cfg, args.pdf or cfg['entree']['livre'])
    travail = chemin_projet(cfg, args.travail or cfg.get('travail', 'travail'))
    dpi = args.dpi or cfg.get('video', {}).get('dpi', 200)

    doc = fitz.open(str(pdf))
    n1 = args.debut or 1
    n2 = min(args.fin or doc.page_count, doc.page_count)
    dossier_pages = Path(travail) / 'pages'
    dossier_pages.mkdir(parents=True, exist_ok=True)

    pages = {'pdf': str(pdf), 'dpi': dpi, 'pages': []}
    total_mots, total_recit = 0, 0
    for pno in range(n1 - 1, n2):
        page = doc[pno]
        pix = page.get_pixmap(dpi=dpi)
        nom_img = f'page_{pno + 1:03d}.png'
        pix.save(str(dossier_pages / nom_img))

        pj = extraire_page(page, pno + 1)
        pj['image'] = f'pages/{nom_img}'
        pages['pages'].append(pj)

        recit = [m for m in pj['mots'] if est_recitable(m['texte'])]
        total_mots += len(pj['mots'])
        total_recit += len(recit)
        echant = ' '.join(normaliser(m['texte']) or '·' for m in recit[:9])
        print(f"  page {pno + 1:>3}: {len(pj['mots']):>4} mots "
              f"({len(recit)} récités) | {echant}")

    pages['stats'] = {'pages': len(pages['pages']), 'mots': total_mots,
                      'recitables': total_recit}
    sauver_json(Path(travail) / 'pages.json', pages)

    if total_mots and total_recit / total_mots < 0.3:
        print("⚠ Moins de 30 % des tokens sont des mots arabes : le PDF est")
        print("  peut-être scanné (images) → il faudra passer par OCR.")
    print(f"OK -> {Path(travail) / 'pages.json'} "
          f"({len(pages['pages'])} pages, images dans {dossier_pages})")


if __name__ == '__main__':
    main()
