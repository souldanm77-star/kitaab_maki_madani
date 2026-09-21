# -*- coding: utf-8 -*-
"""
Fonctions communes au pipeline de synchronisation (projet v2).
"""
import json
import re
from pathlib import Path

# tashkeel + signes coraniques + tatweel
RE_TASHKEEL = re.compile(r'[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]')
RE_LETTRAGE = re.compile(r'[\u0621-\u064A]')

SUBSTITUTIONS = (('أ', 'ا'), ('إ', 'ا'), ('آ', 'ا'), ('ٱ', 'ا'),
                 ('ى', 'ي'), ('ة', 'ه'), ('ؤ', 'و'), ('ئ', 'ي'))


def normaliser(texte: str) -> str:
    """Forme canonique d'un mot arabe : sans tashkeel, lettres unifiées.
    Seules les lettres arabes survivent (chiffres, ornements -> '')."""
    if not texte:
        return ""
    t = RE_TASHKEEL.sub('', texte)
    for a, b in SUBSTITUTIONS:
        t = t.replace(a, b)
    t = t.replace('\u0621', '')          # hamza isolée
    t = re.sub(r'[^\u0621-\u064A]', '', t)
    return t


def est_recitable(texte: str) -> bool:
    """True si le token contient au moins une lettre arabe (mot prononcé)."""
    return bool(RE_LETTRAGE.search(texte or ''))


def similarite(a: str, b: str) -> float:
    """Similarité floue 0..1 entre deux mots normalisés."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # anagrammes : la ligature empilée de الله sort parfois du PDF dans
    # le désordre (لهل, هلل) — mêmes lettres, ordre différent
    if len(a) >= 3 and sorted(a) == sorted(b):
        return 0.9
    # inclusion : Whisper a collé deux mots ou coupé un mot
    if len(a) >= 3 and len(b) >= 3 and (a in b or b in a):
        return 0.85 + 0.1 * min(len(a), len(b)) / max(len(a), len(b))
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


def charger_json(chemin):
    with open(chemin, 'r', encoding='utf-8') as f:
        return json.load(f)


def sauver_json(chemin, objet):
    Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, 'w', encoding='utf-8') as f:
        json.dump(objet, f, ensure_ascii=False, indent=1)


def charger_config(chemin_config):
    cfg = charger_json(chemin_config)
    cfg['_racine'] = str(Path(chemin_config).resolve().parent)
    return cfg


def chemin_projet(cfg, chemin):
    """Résout un chemin relatif par rapport au dossier du fichier de config."""
    if chemin is None:
        return None
    p = Path(chemin)
    return p if p.is_absolute() else Path(cfg['_racine']) / p


def fmt_ass(secondes: float) -> str:
    """Format ASS : h:mm:ss.cc"""
    if secondes is None:
        secondes = 0.0
    secondes = max(0.0, float(secondes))
    h = int(secondes // 3600)
    mn = int(secondes % 3600 // 60)
    s = secondes % 60
    return f"{h:d}:{mn:02d}:{s:05.2f}"


def duree_media(chemin: str) -> float:
    """Durée via ffprobe (0.0 si indisponible)."""
    import subprocess
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(chemin)],
            capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except Exception:
        return 0.0
