#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÉTAPE 4 — Livre HTML interactif (audio + surlignage mot par mot)
=================================================================
Lit mots_livre.json + synchronisation_complet.json + l'audio, et produit un
fichier HTML AUTONOME (police Amiri et audio intégrés en base64 → marche
hors ligne, double-clic suffit).

Fonctionnalités :
  - lecture / pause, vitesse (0,75× / 1× / 1,25×), barre de progression
  - surlignage doré du mot récité, teinte ambrée des mots déjà passés
  - clic sur un mot → l'audio saute à ce mot
  - défilement automatique de la page pendant la récitation
  - affichage du texte EXACT du PDF (tashkeel conservé)

Usage :
  python 4_generer_html.py --livre demo/mots_livre.json \
          --timing demo/synchronisation_complet.json \
          --audio demo/audio.mp3 --sortie demo/livre_interactif.html \
          --titre "سُورَةُ الْفَاتِحَة" --sous "Livre synchronisé — démo"
"""
import argparse
import base64
import json
import os


def embarquer(fichier, mime, limite_mo=30):
    """Renvoie une data-URI base64 si le fichier tient dans la limite."""
    if not fichier or not os.path.exists(fichier):
        return None
    taille = os.path.getsize(fichier)
    if taille > limite_mo * 1024 * 1024:
        return None
    with open(fichier, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode('ascii')}"


def construire_pages(livre, timing_par_pos):
    """Génère le HTML des pages/lignes/mots."""
    lignes = livre["lignes"]
    mots = {m["position"]: m for m in livre["mots"]}
    pages_html = []
    pages = sorted({l["page"] for l in lignes})
    for pno in pages:
        blocs = []
        for l in lignes:
            if l["page"] != pno:
                continue
            spans = []
            for pos in l["mots"]:
                m = mots[pos]
                t = timing_par_pos.get(pos)
                if m["parle"]:
                    cls = "m" if t else "m sans-audio"
                else:
                    cls = "m dec"
                data = (f' data-s="{t["debut"]}" data-e="{t["fin"]}"'
                        if t else "")
                spans.append(f'<span class="{cls}"{data}>{m["texte"]}</span>')
            blocs.append(f'<p class="ligne">{"".join(spans)}</p>')
        pages_html.append(
            f'<section class="page" id="page{pno}">'
            f'<h2>الصفحة {pno}</h2>{"".join(blocs)}</section>')
    return "\n".join(pages_html)


CSS = """
@font-face{font-family:'Amiri';src:url(data:font/ttf;base64,__FONT__) format('truetype');font-display:swap}
:root{--parchemin:#f7f1e1;--encre:#2b2118;--or:#c8961e;--or-clair:#efd9a0;--emeraude:#0e6e5c}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(180deg,#f9f4e6,#efe5cc);color:var(--encre);
     font-family:'Amiri','Scheherazade New','Noto Naskh Arabic',serif}
header{text-align:center;padding:20px 12px 4px}
h1{font-size:30px;margin:0;color:var(--emeraude)}
.sous{color:#7a6a4f;font-size:15px;margin-top:4px}
#barre{position:sticky;top:0;z-index:9;background:rgba(247,241,225,.95);
       backdrop-filter:blur(4px);border-bottom:2px solid #e2d5b4;
       padding:10px 14px;display:flex;gap:12px;align-items:center;justify-content:center}
#btn{width:46px;height:46px;border-radius:50%;border:none;background:var(--emeraude);
     color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;flex:none}
#btn:hover{background:#0a5a4a}
#btn svg{width:20px;height:20px;fill:#fff}
#piste{flex:1;max-width:520px;height:8px;background:#e4d8ba;border-radius:6px;cursor:pointer;position:relative}
#progres{position:absolute;inset-inline-start:0;top:0;bottom:0;width:0;background:var(--or);border-radius:6px}
#temps{font-size:13px;color:#7a6a4f;min-width:92px;text-align:center;direction:ltr}
select{font-family:inherit;border:1px solid #d6c89f;border-radius:8px;background:#fffdf6;
       padding:5px 8px;color:var(--encre);font-size:14px}
.page{max-width:840px;margin:20px auto;padding:28px 34px 34px;background:var(--parchemin);
      border:1px solid #e0d3b0;border-radius:14px;box-shadow:0 6px 24px rgba(90,70,30,.12)}
.page h2{text-align:center;color:var(--emeraude);font-size:24px;margin:0 0 14px;
         border-bottom:1px solid #e0d3b0;padding-bottom:10px;font-weight:700}
.ligne{font-size:34px;line-height:2.15;text-align:center;margin:0 0 8px}
.m{padding:3px 7px;border-radius:9px;cursor:pointer;transition:background .12s,color .12s}
.m:hover{background:#eee2c0}
.m.sans-audio{cursor:default;color:#8a7a5f}
.m.passe{background:var(--or-clair)}
.m.actif{background:var(--or);color:#fff;box-shadow:0 2px 10px rgba(200,150,30,.55)}
.dec{color:var(--emeraude);font-size:.72em}
footer{text-align:center;color:#8a7a5f;font-size:13px;padding:14px 0 26px}
"""

JS = """
const AUDIO=document.getElementById('audio'),BTN=document.getElementById('btn'),
      PISTE=document.getElementById('piste'),PROGRES=document.getElementById('progres'),
      TEMPS=document.getElementById('temps'),VITESSE=document.getElementById('vitesse');
const SVG_PLAY='<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>';
const SVG_PAUSE='<svg viewBox="0 0 24 24"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>';
// liste des mots horodatés, dans l'ordre du livre
const LISTE=[...document.querySelectorAll('.m[data-s]')].map(el=>({
  s:+el.getAttribute('data-s'), e:+el.getAttribute('data-e'), el}));
let actif=null, ligne=null, minuterie=null;
function fmt(t){t=Math.max(0,t|0);return (t/60|0)+':'+String(t%60).padStart(2,'0');}
function majLecture(){
  const t=AUDIO.currentTime; let k=-1;
  let lo=0,hi=LISTE.length-1;
  while(lo<=hi){const m=(lo+hi)>>1; if(LISTE[m].s<=t){k=m;lo=m+1;}else hi=m-1;}
  let cible=k;
  if(cible>=0 && LISTE[cible].el.classList.contains('dec')){
    cible=actif;   // token décoratif : on garde le dernier mot parlé actif
  }
  if(cible!==actif){
    LISTE.forEach((x,i)=>{
      x.el.classList.toggle('actif',i===cible);
      x.el.classList.toggle('passe',i<cible);
    });
    actif=cible;
    if(cible>=0){
      const L=LISTE[cible].el.closest('.ligne');
      if(L && L!==ligne){ligne=L;L.scrollIntoView({block:'center',behavior:'smooth'});}
    }
  }
  PROGRES.style.width=(AUDIO.duration?100*t/AUDIO.duration:0)+'%';
  TEMPS.textContent=fmt(t)+' / '+fmt(AUDIO.duration||0);
}
function demarrer(){clearInterval(minuterie);minuterie=setInterval(majLecture,80);}
BTN.innerHTML=SVG_PLAY;
BTN.onclick=()=>{AUDIO.paused?AUDIO.play():AUDIO.pause();};
AUDIO.onplay=()=>{BTN.innerHTML=SVG_PAUSE;demarrer();};
AUDIO.onpause=()=>{BTN.innerHTML=SVG_PLAY;clearInterval(minuterie);};
AUDIO.onended=()=>{BTN.innerHTML=SVG_PLAY;clearInterval(minuterie);};
AUDIO.ontimeupdate=majLecture;
VITESSE.onchange=()=>AUDIO.playbackRate=parseFloat(VITESSE.value);
PISTE.onclick=e=>{
  const r=PISTE.getBoundingClientRect();
  const frac=(e.clientX-r.left)/r.width;
  AUDIO.currentTime=frac*(AUDIO.duration||0);
};
document.querySelectorAll('.m[data-s]').forEach(el=>{
  el.addEventListener('click',()=>{
    AUDIO.currentTime=parseFloat(el.getAttribute('data-s'))+0.01;AUDIO.play();});
});
document.addEventListener('keydown',e=>{
  if(e.code==='Space'&&e.target.tagName!=='SELECT'){e.preventDefault();BTN.click();}
});
"""

HTML_GABARIT = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITRE__ — livre synchronisé</title>
<style>__CSS__</style>
</head>
<body>
<header><h1>__TITRE__</h1><div class="sous">__SOUS__</div></header>
<div id="barre">
  <button id="btn" aria-label="Lecture / pause"></button>
  <div id="temps">0:00 / 0:00</div>
  <div id="piste"><div id="progres"></div></div>
  <select id="vitesse">
    <option value="0.75">×0,75</option>
    <option value="1" selected>×1</option>
    <option value="1.25">×1,25</option>
  </select>
</div>
__AUDIO__
<main>
__PAGES__
</main>
<footer>Texte : référence PDF exacte · Surlignage : synchronisation mot à mot</footer>
<script>__JS__</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="Génère le livre HTML interactif")
    ap.add_argument("--livre", required=True)
    ap.add_argument("--timing", required=True, help="synchronisation_complet.json")
    ap.add_argument("--audio", required=True)
    ap.add_argument("--sortie", required=True)
    ap.add_argument("--titre", default="الكتاب المُزامَن")
    ap.add_argument("--sous", default="Livre interactif synchronisé mot à mot")
    ap.add_argument("--police", default=None,
                    help="TTF Amiri à intégrer (défaut: ../assets/Amiri-Regular.ttf)")
    ap.add_argument("--audio-externe", action="store_true",
                    help="référencer l'audio au lieu de l'intégrer (fichiers volumineux)")
    args = ap.parse_args()

    livre = json.load(open(args.livre, encoding="utf-8"))
    timing = json.load(open(args.timing, encoding="utf-8"))

    timing_par_pos = {m["position"]: m for m in timing["mots"]}

    # timing plat pour le JS (seulement les mots avec audio)
    plat = [{"p": m["page"], "pos": m["position"],
             "s": m["debut"], "e": m["fin"], "par": m["parle"]}
            for m in timing["mots"]]
    js = JS.replace("__TIMING__", json.dumps(plat, ensure_ascii=False))

    # police Amiri intégrée
    police = args.police or os.path.join(
        os.path.dirname(os.path.abspath(args.sortie)), "..", "assets", "Amiri-Regular.ttf")
    font_b64 = ""
    if police and os.path.exists(police):
        with open(police, "rb") as f:
            font_b64 = base64.b64encode(f.read()).decode("ascii")

    # audio intégré ou externe
    data_uri = None if args.audio_externe else embarquer(args.audio, "audio/mpeg")
    if data_uri:
        balise = f'<audio id="audio" src="{data_uri}" preload="auto"></audio>'
    else:
        chemin = os.path.abspath(args.audio)
        balise = (f'<audio id="audio" src="file://{chemin}" preload="auto"></audio>'
                  '<p class="note" style="text-align:center;color:#8a7a5f">'
                  'Audio externe : ouvrez ce fichier dans le même dossier que '
                  f'{os.path.basename(args.audio)} si le son ne démarre pas.</p>')

    html = (HTML_GABARIT
            .replace("__CSS__", CSS.replace("__FONT__", font_b64))
            .replace("__JS__", js)
            .replace("__AUDIO__", balise)
            .replace("__TITRE__", args.titre)
            .replace("__SOUS__", args.sous)
            .replace("__PAGES__", construire_pages(livre, timing_par_pos)))

    with open(args.sortie, "w", encoding="utf-8") as f:
        f.write(html)

    taille = os.path.getsize(args.sortie) / 1024
    print(f"✔ livre_interactif généré ({taille:.0f} Ko) → {args.sortie}")
    print(f"  mots horodatés : {sum(1 for m in timing['mots'] if m['debut'] is not None)}")


if __name__ == "__main__":
    main()
