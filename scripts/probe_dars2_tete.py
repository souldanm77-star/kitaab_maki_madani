#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probe : pourquoi la lecture de tête de dars2 (0-40 s) n'est-elle pas
détectée ? Reproduit la chaîne PASS 1 (ancres → DP → runs → filtre) sur
la fenêtre et imprime chaque décision."""
import json, sys
from pathlib import Path

PROJET = Path(__file__).resolve().parent.parent / "download" / "video-recitation"
sys.path.insert(0, str(PROJET / "pipeline"))
from commun import normaliser, similarite, est_recitable, charger_json  # noqa
import importlib
al = importlib.import_module("3_aligner") if False else None

# import du module 3_aligner (nom avec chiffre en tête)
import types
src = (PROJET / "pipeline" / "3_aligner.py").read_text(encoding="utf-8")
mod = types.ModuleType("aligner_v3")
mod.__dict__["__file__"] = str(PROJET / "pipeline" / "3_aligner.py")
exec(compile(src, "3_aligner.py", "exec"), mod.__dict__)

T0, T1 = 0.0, 42.0
travail = PROJET / "travail_darsi"
trans = charger_json(travail / "dars2" / "transcription.json")
pages = charger_json(travail / "pages.json")

w_mots = [m for m in trans["mots"] if T0 <= m["debut"] < T1]
print(f"Whisper {T0}-{T1}s : {len(w_mots)} mots")
w_norms_full = []
for w in trans["mots"]:
    n = normaliser(w["mot"])
    w_norms_full.append(n if (n and est_recitable(w["mot"])) else None)

mots = []
for p in pages["pages"]:
    for m in p["mots"]:
        m['page'] = p['numero']
        mots.append(m)
parle_idx = [i for i, m in enumerate(mots) if est_recitable(m['texte']) and normaliser(m['texte'])]
b_norms = [normaliser(mots[i]['texte']) for i in parle_idx]
print(f"Livre : {len(b_norms)} mots récitable")

# où est « قال الإمام السيوطي » ?
for j, n in enumerate(b_norms):
    if n == "السيوطي":
        print(f"→ السيوطي dans le livre à j={j} (page {mots[parle_idx[j]]['page']}, pos {mots[parle_idx[j]]['position']})")
        print("   contexte:", ' '.join(b_norms[max(0,j-6):j+8]))

# 1) ancres globales
ancrages = mod.chercher_ancrages(w_norms_full, b_norms)
print(f"\nAncres globales : {len(ancrages)} ; dans la fenêtre 0-42 s :",
      [(i, j) for i, j in ancrages if trans['mots'][i]['debut'] < T1][:10])
idx_w = [i for i, m in enumerate(trans['mots']) if T0 <= m['debut'] < T1]
i_lo, i_hi = idx_w[0], idx_w[-1] + 1
prem_ancre = next(((i, j) for i, j in ancrages if i >= i_hi), None)
j_hi = prem_ancre[1] if prem_ancre else len(b_norms)
w_r = list(range(i_lo, i_hi))
b_r = list(range(0, min(j_hi, len(b_norms))))
print(f"Intervalle tête : w {i_lo}..{i_hi} ({len(w_r)} mots), b 0..{j_hi}")

sous_w = [w_norms_full[i] for i in w_r]
sous_b = [b_norms[j] for j in b_r]
ops = mod.dp_locale(sous_w, sous_b, seuil=mod.SEUIL)
paires = [(w_r[o[1]], b_r[o[2]], similarite(sous_w[o[1]], sous_b[o[2]]))
          for o in ops if o[0] == 'M']
print(f"\nDP paires ({len(paires)}) :")
for wi, bj, sc in paires:
    print(f"  w{wi} ({trans['mots'][wi]['mot']:15s} @{trans['mots'][wi]['debut']:6.1f}s)"
          f" → b{bj} ({mots[parle_idx[bj]]['texte']:12s} p{mots[parle_idx[bj]]['page']}"
          f" pos{mots[parle_idx[bj]]['position']})  sc={sc:.2f}")

if paires:
    ps = sorted(paires)
    q = mod.qualite_run(ps, trans['mots'], b_norms)
    print("\nQualité :", {k: (round(v, 2) if isinstance(v, float) else v) for k, v in q.items()})
    print("filtre_strict :", mod.filtre_strict(q))
    print("filtre_souple :", mod.filtre_souple(q))
