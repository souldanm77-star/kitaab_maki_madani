# -*- coding: utf-8 -*-
"""Test 2 : reconstruction mots par gap horizontal (clustering spatial)."""
import fitz, re

TASHKEEL = re.compile(r'[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]')
LETTRAGE = re.compile(r'[\u0621-\u064A]')

def normaliser(t):
    t = TASHKEEL.sub('', t)
    for a, b in (('أ','ا'),('إ','ا'),('آ','ا'),('ٱ','ا'),('ى','ي'),('ة','ه'),('ؤ','و'),('ئ','ي')):
        t = t.replace(a, b)
    return re.sub(r'[^\u0621-\u064A]', '', t)

doc = fitz.open('/home/z/my-project/download/synchronisation-recitation/demo/livre.pdf')

for pno in range(doc.page_count):
    page = doc[pno]
    d = page.get_text('rawdict', flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES)
    lignes = {}
    for bi, bloc in enumerate(d['blocks']):
        if bloc.get('type') != 0:
            continue
        for li, line in enumerate(bloc.get('lines', [])):
            for span in line.get('spans', []):
                for ch in span.get('chars', []):
                    if ch['c'].strip():
                        lignes.setdefault((bi, li), []).append((ch['bbox'], ch['c']))

    print(f'=== page {pno+1} : {len(lignes)} lignes ===')
    for cle in sorted(lignes, key=lambda k: min(b[1] for b, _ in lignes[k])):
        chars = lignes[cle]
        y0 = min(b[1] for b, _ in chars)
        # tri spatial RTL : bord droit décroissant ; diacritiques collés à leur lettre
        chars = sorted(chars, key=lambda t: (-t[0][2], t[0][0]))
        # largeur médiane des lettres (non diacritiques)
        larg = [b[2]-b[0] for b, c in chars if LETTRAGE.match(c)]
        larg.sort()
        med = larg[len(larg)//2] if larg else 4.0
        seuil = max(1.0, 0.45 * med)
        # clustering en mots par gap horizontal
        mots = []
        for bbox, c in chars:
            if mots and (mots[-1]['x0'] - bbox[2]) <= seuil:
                m = mots[-1]
                m['texte'] += c
                m['x0'] = min(m['x0'], bbox[0]); m['y0'] = min(m['y0'], bbox[1])
                m['x1'] = max(m['x1'], bbox[2]); m['y1'] = max(m['y1'], bbox[3])
            else:
                mots.append({'texte': c, 'x0': bbox[0], 'y0': bbox[1], 'x1': bbox[2], 'y1': bbox[3]})
        normes = [normaliser(m['texte']) for m in mots]
        print(f'y={y0:6.1f} | ' + ' | '.join(n if n else '·' for n in normes))
