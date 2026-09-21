# -*- coding: utf-8 -*-
"""Test : reconstruction de l'ordre de lecture par tri spatial des caractères."""
import fitz, re

TASHKEEL = re.compile(r'[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]')

def normaliser(t):
    t = TASHKEEL.sub('', t)
    for a, b in (('أ','ا'),('إ','ا'),('آ','ا'),('ٱ','ا'),('ى','ي'),('ة','ه'),('ؤ','و'),('ئ','ي')):
        t = t.replace(a, b)
    return re.sub(r'[^\u0621-\u064A]', '', t)

doc = fitz.open('/home/z/my-project/download/synchronisation-recitation/demo/livre.pdf')
page = doc[0]
d = page.get_text('rawdict', flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES)

# collecter les caractères par ligne (bloc, ligne)
lignes = {}
for bi, bloc in enumerate(d['blocks']):
    if bloc.get('type') != 0:
        continue
    for li, line in enumerate(bloc.get('lines', [])):
        for span in line.get('spans', []):
            for ch in span.get('chars', []):
                cle = (bi, li)
                lignes.setdefault(cle, []).append((ch['bbox'], ch['c']))

print('nb lignes brutes:', len(lignes))
for cle in sorted(lignes, key=lambda k: min(b[1] for b, _ in lignes[k])):
    chars = lignes[cle]
    if not any(c.strip() for _, c in chars):
        continue
    y = min(b[1] for b, _ in chars)
    # tri spatial RTL : x1 décroissant (marge d'incertitude pour les diacritiques)
    chars_tries = sorted(chars, key=lambda t: (-(t[0][2] // 3), t[0][0]))
    texte = ''.join(c for _, c in chars_tries)
    norm = ' '.join(normaliser(m) for m in texte.split() if normaliser(m))
    if norm:
        print(f'y={y:6.1f} | {norm[:80]}')
