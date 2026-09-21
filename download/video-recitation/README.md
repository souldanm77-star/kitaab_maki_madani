# Vidéos de récitation — surlignage mot par mot

Crée des vidéos YouTube à partir de **3 ingrédients** :

| Ingrédient | Rôle |
|---|---|
| **PDF du livre** (avec texte) | fournit les **pages réelles** affichées à droite |
| **Audio de la récitation** du cheikh | fournit le son + les moments de chaque mot |
| **Image du cheikh** | affichée fixe à gauche |

Résultat : vidéo 1920×1080 (H.264 + AAC), **une vidéo par section (dars)**,
avec un **rectangle surligneur jaune** qui suit mot à mot (ou ligne à ligne)
le texte réellement récité sur la page réelle du livre.

> Point clé : la page affichée est le **rendu exact du PDF** — aucune remise
> en page, aucun texte refait. Le rectangle est posé par-dessus, à
> l'endroit exact du mot récité.

---

## Installation des fichiers (à faire une fois)

Déposez vos vrais fichiers ici :

```
entree/
  livre.pdf          ← le PDF du livre
  cheikh.jpg         ← l'image du cheikh (png/jpg, de préférence verticale)
  audio/
    dars1.mp3        ← l'enregistrement du dars 1
```

Puis ouvrez `config.json` et ajustez la section `darses` — **une entrée par
vidéo** :

```json
"darses": {
  "dars1": { "titre": "الدرس الأول", "audio": "entree/audio/dars1.mp3",
             "pages": [1, 10] },
  "dars2": { "titre": "الدرس الثاني", "audio": "entree/audio/dars2.mp3",
             "pages": [11, 22] }
}
```

- `pages` : plage de pages du PDF couvertes par CETTE section
  (chaque section doit commencer à un début de page).
- Vous ne possédez pour l'instant que le début du livre ? Pas grave :
  déclarez seulement `dars1` ; les 3 autres dars s'ajouteront plus tard
  en ajoutant simplement des entrées + leurs fichiers audio.

---

## Les 4 commandes (dans l'ordre, depuis ce dossier)

```bash
# 1. Une seule fois (ou quand le PDF change) : pages réelles + mots
python3 pipeline/1_extraire_pdf.py --config config.json

# 2. Pour chaque section : transcription de l'audio (timestamps par mot)
python3 pipeline/2_transcrire.py --config config.json --dars dars1

# 3. Alignement mots du livre ⟷ audio (le moteur du surlignage)
python3 pipeline/3_aligner.py --config config.json --dars dars1

# 4. Montage de la vidéo
python3 pipeline/4_video.py --config config.json --dars dars1
```

La vidéo sort dans `sortie/dars1.mp4`, prête pour YouTube.

### Démo prête à regarder

Une démonstration complète (Fatiha + Ikhlas, audio TTS, image placeholder)
est déjà générée : **`sortie/dars_demo.mp4`**. Pour la refaire :

```bash
python3 pipeline/1_extraire_pdf.py --config config_demo.json
python3 pipeline/2_transcrire.py   --config config_demo.json --dars dars_demo
python3 pipeline/3_aligner.py      --config config_demo.json --dars dars_demo
python3 pipeline/4_video.py        --config config_demo.json --dars dars_demo
```

---

## Réglages utiles (dans config.json)

### Style du surligneur

```json
"surlignage": {
  "mode": "mot",            // "mot" (karaoke) ou "ligne" (ligne entière)
  "couleur": [255, 235, 59], // jaune surligneur (RGB)
  "opacite": 0.45,           // 0 = invisible, 1 = opaque
  "pad": 5                   // débordement du rectangle autour du mot (px)
}
```

Le mode `ligne` est plus robuste si l'extraction de mots du PDF est
imparfaite : la ligne entière reste surlignée tant qu'elle est lue.

### Vitesse de transcription

```json
"whisper": { "modele": "small" }   // base = plus rapide, medium = plus précis
```

Sur une petite machine, `base` suffit souvent ; `medium` améliore les
mots mal prononcés. Le modèle se télécharge tout seul au premier lancement.

---

## Comment lire les résultats

### Le taux de couverture (étape 3)

Le script affiche par ex. `appariements directs : 44/68 (64,7 %)`.
C'est la part de mots du livre **retrouvés dans l'audio par Whisper**.
Les autres sont **interpolés** entre leurs voisins — c'est normal et
voulu (noms propres mal entendus, mots collés…). Le surlignage reste
fluide. Un taux > 50 % donne déjà un très bon résultat ; < 30 %,
vérifiez l'audio et la plage `pages`.

### Le CSV de synchronisation

`sortie/dars1_synchronisation.csv` — format `mot;debut;fin;page;position;texte`.
C'est le **fichier moteur** : chaque mot du livre avec son instant de début
et de fin en secondes. Vous pouvez le corriger à la main (tableur) puis
relancer **uniquement l'étape 4** pour refaire la vidéo.

### Diagnostic extraction (étape 1)

Chaque page affiche ses mots reconnus. Si l'ordre semble inversé ou les
mots absurdes, le PDF est peut-être scanné (images) → il faudra de l'OCR.

---

## Structure du projet

```
video-recitation/
├── config.json            ← VOS réglages (sections, styles)
├── config_demo.json       ← réglages de la démo
├── entree/                ← VOS fichiers (pdf, image, audios)
├── pipeline/
│   ├── commun.py          ← normalisation arabe, utilitaires
│   ├── 1_extraire_pdf.py  ← PDF → pages PNG réelles + mots (coordonnées)
│   ├── 2_transcrire.py    ← audio → Whisper timestamps mot à mot
│   ├── 3_aligner.py       ← alignement DP livre ⟷ audio → timing.json + CSV
│   └── 4_video.py         ← montage : cheikh + page réelle + surligneur ASS
├── demo/                  ← livre/audio d'exemple + placeholder cheikh
├── travail/               ← fichiers intermédiaires (généré)
└── sortie/                ← VIDÉOS + CSV (généré)
```

## Dépendances (déjà installées)

Python : `pymupdf`, `faster-whisper`, `pillow`, `edge-tts` (démo).
Système : `ffmpeg`, `ffprobe`.
