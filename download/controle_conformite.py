#!/usr/bin/env python3
"""
controle_conformite.py — audit + correction des CSV de synchronisation des darsi
================================================================================

Règle métier : le surlignage n'est actif QUE si le Cheikh lit réellement le
texte du livre (arabe qui correspond au livre). Jamais pendant le somali ni
pendant un commentaire arabe hors-texte.

Contrôles appliqués à chaque  dars{N}_synchronisation.csv  (mot;debut;fin;page;position;texte) :
  C1  clusters isolés   : < MIN_CLUSTER mots consécutifs  -> supprimés (faux positifs)
  C2  sauts de position : saut > MAX_SAUT mots ou retour arrière dans une même
                          lecture -> la lecture est coupée en deux clusters
  C3  durée excessive   : mot surligné > DUREE_MAX s -> plafonné (pas de
                          surlignage qui « traîne » pendant une pause)
  C4  chevauchements    : deux mots surlignés en même temps -> fin rognée

Sorties (dossier  conformite/) :
  dars{N}_synchronisation_corrige.csv   CSV nettoyé
  rapport_conformite.json / .md         bilan avant/après + liste des mots retirés

Usage :  python3 controle_conformite.py [--dossier .] [--sortie conformite]
"""
import argparse
import csv
import json
from pathlib import Path

MIN_CLUSTER = 3
GAP = 2.5          # silence max (s) entre deux mots d'une même lecture
MAX_SAUT = 8       # saut de position max (mots) dans une même lecture
DUREE_MAX = 1.6    # durée max (s) d'un mot surligné


def lire(chemin):
    with open(chemin, encoding="utf-8-sig", newline="") as f:
        r = list(csv.reader(f, delimiter=";"))
    entete, lignes = r[0], r[1:]
    mots = [dict(mot=l[0], t0=float(l[1]), t1=float(l[2]), page=int(l[3]),
                 pos=int(l[4]), texte=l[5]) for l in lignes if len(l) >= 6]
    return entete, sorted(mots, key=lambda m: (m["t0"], m["t1"]))


def decouper(mots):
    """Clusters = lectures continues (même page, silence <= GAP, position croissante sans gros saut)."""
    if not mots:
        return []
    clusters = [[mots[0]]]
    for a, b in zip(mots, mots[1:]):
        continu = (b["page"] == a["page"] and b["t0"] - a["t1"] <= GAP
                   and 0 <= b["pos"] - a["pos"] <= MAX_SAUT)
        if continu:
            clusters[-1].append(b)
        else:
            clusters.append([b])
    return clusters


def auditer(mots):
    clusters = decouper(mots)
    return {
        "mots": len(mots),
        "clusters": len(clusters),
        "clusters_isoles": sum(1 for c in clusters if len(c) < MIN_CLUSTER),
        "mots_isoles": sum(len(c) for c in clusters if len(c) < MIN_CLUSTER),
        "mots_trop_longs": sum(1 for m in mots if m["t1"] - m["t0"] > DUREE_MAX + 1e-6),
        "chevauchements": sum(1 for a, b in zip(mots, mots[1:]) if b["t0"] < a["t1"] - 1e-3),
    }


def corriger(mots):
    # 1) plafonner d'abord : un mot étiré sur une pause ne doit pas « ponter »
    #    artificiellement deux lectures distinctes
    for m in mots:
        if m["t1"] - m["t0"] > DUREE_MAX:
            m["t1"] = round(m["t0"] + DUREE_MAX, 3)
    # 2) regrouper en lectures continues et retirer les clusters isolés
    clusters = decouper(mots)
    gardes, retires = [], []
    for c in clusters:
        if len(c) >= MIN_CLUSTER:
            gardes.extend(c)
        else:
            retires.extend(c)
    # 3) supprimer les chevauchements (un seul mot surligné à la fois)
    gardes.sort(key=lambda m: (m["t0"], m["t1"]))
    for a, b in zip(gardes, gardes[1:]):
        if a["t1"] > b["t0"]:
            a["t1"] = b["t0"]
    gardes = [m for m in gardes if m["t1"] > m["t0"]]
    return gardes, retires


def avertissements(mots, seuil_pages=5):
    """Sauts de page suspects entre deux lectures consécutives (possible faux raccord)."""
    res = []
    cl = decouper(mots)
    for a, b in zip(cl, cl[1:]):
        d = abs(b[0]["page"] - a[-1]["page"])
        if d >= seuil_pages:
            res.append("saut page %d -> %d entre %ds et %ds (à vérifier à l'écoute)" % (
                a[-1]["page"], b[0]["page"], round(a[-1]["t1"]), round(b[0]["t0"])))
    return res


def ecrire(chemin, entete, mots):
    with open(chemin, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\r\n")
        w.writerow(entete)
        for m in mots:
            w.writerow([m["mot"], "%.3f" % m["t0"], "%.3f" % m["t1"],
                        m["page"], m["pos"], m["texte"]])


def pages_lues(mots):
    """Résumé par page : première/dernière seconde et nombre de mots."""
    res = {}
    for m in mots:
        p = res.setdefault(m["page"], [m["t0"], m["t1"], 0])
        p[0], p[1], p[2] = min(p[0], m["t0"]), max(p[1], m["t1"]), p[2] + 1
    return {k: {"debut_s": round(v[0]), "fin_s": round(v[1]), "mots": v[2]}
            for k, v in sorted(res.items())}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dossier", default=str(Path(__file__).parent))
    ap.add_argument("--sortie", default="conformite")
    a = ap.parse_args()
    dossier, sortie = Path(a.dossier), Path(a.dossier) / a.sortie
    sortie.mkdir(parents=True, exist_ok=True)

    bilan, md = {}, ["# Rapport de conformité du surlignage\n",
                     "Règle : surlignage uniquement sur la vraie lecture du livre.\n",
                     "| Dars | Mots avant | Mots après | Mots isolés retirés | Mots plafonnés | Chevauchements | Pages lues |",
                     "|---|---|---|---|---|---|---|"]
    for csv_in in sorted(dossier.glob("dars*_synchronisation.csv")):
        nom = csv_in.name.split("_")[0]
        entete, mots = lire(csv_in)
        avant = auditer(mots)
        corrige, retires = corriger([dict(m) for m in mots])
        apres = auditer(corrige)
        ecrire(sortie / ("%s_synchronisation_corrige.csv" % nom), entete, corrige)
        bilan[nom] = {
            "avant": avant, "apres": apres,
            "pages_lues": pages_lues(corrige),
            "avertissements": avertissements(corrige),
            "mots_retires": [{"mot": m["texte"], "t": round(m["t0"], 1), "page": m["page"],
                              "pos": m["pos"]} for m in retires],
        }
        md.append("| %s | %d | %d | %d | %d | %d → %d | %s |" % (
            nom, avant["mots"], apres["mots"], len(retires), avant["mots_trop_longs"],
            avant["chevauchements"], apres["chevauchements"],
            ", ".join(str(p) for p in bilan[nom]["pages_lues"])))

    md.append("\n## Avertissements (vérification humaine recommandée)\n")
    for nom, b in bilan.items():
        for w in b["avertissements"]:
            md.append("- **%s** : %s" % (nom, w))
    (sortie / "rapport_conformite.json").write_text(
        json.dumps(bilan, ensure_ascii=False, indent=2), encoding="utf-8")
    (sortie / "rapport_conformite.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    print("\nFichiers écrits dans :", sortie)


if __name__ == "__main__":
    main()
