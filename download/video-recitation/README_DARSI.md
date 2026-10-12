# darsi_video.py — Vidéo Darsi synchronisée automatique

Script Python **complet et autonome** qui transforme :

1. **l'audio du Sheikh** (récitation arabe + explications en langue locale),
2. **le PDF du livre** (ou les images des pages + un texte de référence),

en une **vidéo (.mp4 ou .mpg)** où :

- la **page réelle en cours de lecture** est affichée au bon moment ;
- si le Sheikh **revient en arrière et répète** un passage, la vidéo **réaffiche
  automatiquement la page correspondante** ;
- avec `--surligner` : le **mot exact en cours de récitation est surligné en
  jaune, mot par mot**, et **aucun surlignage** n'est fait pendant les
  explications hors livre (règle des « 3 états »).

---

## 1. Installation

```bash
# Python 3.8+
python3 -m pip install faster-whisper PyMuPDF rapidfuzz
# ffmpeg (audio/vidéo) :
sudo apt install ffmpeg        # Debian/Ubuntu
# brew install ffmpeg          # macOS
```

| Paquet | Rôle |
|---|---|
| `faster-whisper` | transcription Whisper 4x plus rapide (horodatage **mot par mot**) |
| `PyMuPDF` | lecture du PDF : texte, coordonnées des mots, rendu des pages en images |
| `rapidfuzz` | similarité entre mots (optionnel mais recommandé) |
| `ffmpeg` | assemblage de la vidéo finale |

> Sans PDF : seuls `faster-whisper` et `ffmpeg` sont nécessaires, mais le
> surlignage mot à mot ne sera pas possible (il faut les coordonnées du PDF).

---

## 2. Organisation des fichiers

Créez **un dossier par darsi**. Deux configurations possibles :

### Configuration A (recommandée) : PDF du livre

```
mon_darsi/
├── audio.mp3        (ou .wav, .mpeg, .m4a, .ogg… : l'audio du Sheikh)
├── LIVRE.pdf        (le PDF du livre : le Darsi complet)
└── (les images des pages sont générées automatiquement dans images/)
```

- Le texte de référence est extrait **directement du PDF** (page par page),
  avec les **coordonnées de chaque mot** → surlignage jaune possible.
- Le PDF est lu même si les glyphes arabes sont dans le désordre
  (reconstruction de droite à gauche, ligatures regroupées, diacritiques rattachés).

### Configuration B : images + texte

```
mon_darsi/
├── audio.mp3
├── texte.txt        (le texte du Darsi découpé par pages)
└── images/
    ├── page1.jpg    (ou page01.jpg, page1.png…)
    ├── page2.jpg
    └── …
```

`texte.txt` doit séparer les pages ainsi (les numéros = numéros d'images) :

```
=== PAGE 1 ===
texte de la page 1…
=== PAGE 2 ===
texte de la page 2…
```

> Dans cette configuration il n'y a pas de coordonnées → la vidéo suit les
> pages et les répétitions, mais **sans surlignage mot à mot**.

---

## 3. Utilisation

```bash
# complet : page + surlignage jaune mot à mot
python3 darsi_video.py --dossier mon_darsi --langue ar --surligner

# sans surlignage (images + texte)
python3 darsi_video.py --dossier mon_darsi --langue ar

# format MPEG classique (.mpg) au lieu de MP4
python3 darsi_video.py --dossier mon_darsi --format mpeg

# modèle Whisper plus précis (plus lent)
python3 darsi_video.py --dossier mon_darsi --modele medium
```

### Options principales

| Option | Défaut | Description |
|---|---|---|
| `--dossier` | (obligatoire) | dossier du darsi |
| `--audio` | auto-détection | nom du fichier audio |
| `--pdf` | auto-détection | nom du PDF du livre |
| `--texte` | — | texte de référence (si pas de PDF) |
| `--images` | `images` | dossier des images des pages |
| `--langue` | auto | `ar`, `so`, `fr`… (langue principale de l'audio) |
| `--modele` | `small` | `tiny` / `base` / `small` / `medium` / `large-v3` |
| `--surligner` | off | surlignage jaune mot à mot (nécessite le PDF) |
| `--seuil-run` | 4 | nb minimal de mots consécutifs pour valider une récitation |
| `--format` | `mp4` | `mp4` (H.264) ou `mpeg` (MPEG-2 .mpg) |
| `--res` | 1080 | hauteur de la vidéo en pixels |
| `--sortie` | `<dossier>/sortie/Darsi.mp4` | chemin de la vidéo finale |

### Résultats produits

```
mon_darsi/sortie/Darsi.mp4                  la vidéo finale
mon_darsi/sortie/timing.csv                 mot;debut;fin;page;position;texte
mon_darsi/sortie/rapport_alignement.json    statistiques + répétitions détectées
mon_darsi/travail/morceaux/*.json           cache de transcription (reprise auto)
```

**Le script est relançable sans risque** : les morceaux d'audio déjà
transcrits sont mis en cache et ne sont pas recalculés.

---

## 4. L'algorithme de détection des répétitions

Le problème : la transcription Whisper est imparfaite (mots mal reconnus,
mots oubliés) et la lecture **n'est pas linéaire** — le Sheikh s'arrête,
explique en somali, **revient en arrière** et répète des passages.
Un simple « suivi de progression » échoue dès la première répétition.

Le script procède en **4 étapes** (fonctions dans la SECTION 5 du script) :

### Étape A — Ancres n-grammes (`trouver_ancres`)

On cherche les **n-grammes de 5 mots** de la transcription qui apparaissent
**exactement** dans le texte de référence (puis une 2e passe en 3 mots pour
les zones manquées). Une **ancre** = un couple fiable
`(position_dans_audio, position_dans_livre)`.

**Idée clé** : on garde TOUTES les ancres, triées par temps. La suite des
positions du livre dessine la **trajectoire réelle de la lecture** :

```
audio :   t1    t2    t3    t4    t5    t6    t7
livre :    10 →  11 →  12 →  10 →  11 →  13 →  14
                            ↑
                    RETOUR EN ARRIÈRE = RÉPÉTITION
```

Quand la trajectoire **redescend**, le Sheikh a répété : la position du livre
suit réellement la voix, sans jamais forcer une progression monotone.

Ambiguïtés supprimées par `nettoyer_ancres` : un même moment de l'audio ne
peut correspondre qu'à UN endroit du livre (choix du j le plus proche de la
trajectoire en cours). Les vraies répétitions, elles, sont sur des moments
différents → toutes conservées.

### Étape B — Needleman-Wunsch local (`aligner_nw`)

Entre deux ancres consécutives, on aligne la tranche d'audio contre la
**fenêtre de référence qui couvre les deux ancres** — algorithme classique
d'alignement de séquences (comme en bio-informatique) :

- match exact : **+2** ; similaire : **-1 + 3 × similarité** ; gap : **-1** ;
- la similarité est floue (rapidfuzz) avec un cas spécial : les ligatures
  désordonnées du PDF (الله écrit `هلل`) sont des **anagrammes** → 0,95 ;
- si la 2e ancre est **avant** la 1re (répétition), la fenêtre contient
  toute la boucle → les mots intermédiaires se répartissent correctement ;
- garde-fou de progression : la fenêtre en **avant** est plafonnée à
  `5 × (nb de mots audio) + 200` — on ne peut pas « lire » 500 mots en 1 s,
  donc le NW ne peut plus éparpiller les mots à des positions aléatoires.

### Étape C — Interpolation (`inserer_mots_interpoles`)

À l'intérieur d'un run validé, les mots du livre que Whisper a **sautés**
(présents dans le texte, entre deux mots alignés) reçoivent des temps
**interpolés linéairement** entre leurs voisins : ils seront surlignés eux
aussi, le surlignage ne « bipe » pas.

### Étape D — Runs de récitation : la règle des 3 états (`aligner_transcription`)

Un mot aligné n'est pas forcément **récité** (coïncidences dans les
explications, formules répétitives…). Deux garde-fous de plausibilité
coupent les runs :

- **saut en avant impossible** : si `j` avance de plus de
  `8 × Δt + 5` mots → faux alignement, run coupé ;
- **saut en arrière** de plus de 5 mots → c'est une **répétition** :
  le run est coupé, le passage répété forme son propre run.

Puis un run n'est **validé** que si :

- **≥ 4 mots consécutifs** alignés (`--seuil-run`) ;
- durée **≥ 2 s** ;
- similarité **moyenne ≥ 0,70** (les vraies récitations font ≥ 0,90 ;
  les coïncidences plafonnent à ~0,65).

Conséquences visibles dans la vidéo :

| État | Affichage |
|---|---|
| Récitation du livre (run validé) | mot surligné en jaune, page suit la lecture |
| Explication hors livre | **aucun surlignage**, la dernière page lue reste affichée |
| Répétition (retour en arrière) | **la page précédente réapparaît**, surlignage reprend |

### Étape E — Pages et rendu

- La page change **au moment où le premier mot d'une nouvelle page commence**
  à être récité (jamais au milieu d'une explication) ;
- les micro-changements (< 0,25 s) sont fusionnés (pas de clignotement) ;
- le rendu utilise le **démuxeur concat** de ffmpeg (gère 1 h+ d'audio) :
  `ffmpeg -f concat -i concat.txt -i audio.mp3 -vf "scale=…,ass=surlignage.ass" …` ;
- le surlignage est un fichier de **sous-titres ASS** : un **rectangle jaune
  semi-transparent** (opacité 0,45) dessiné en mode vectoriel `{\p1}` sur
  les coordonnées du mot (converties des points PDF vers les pixels vidéo).

---

## 5. Limites connues et conseils

- **PDF scanné (images)** : aucun texte extractible → il faut un OCR, ou
  utiliser la configuration B (images + texte tapé).
- **Pages de titre décoratives** (grande calligraphie) : les mots peuvent y
  être mal découpés ; l'alignement s'appuie sur les pages normales.
- **`--modele`** : `small` est un bon compromis ; `medium`/`large-v3`
  améliorent la transcription des accents (plus lent).
- Le débit de rendu est ≈ **3 à 4 × la durée de l'audio** sur CPU
  (un darsi de 80 min → ~4 à 5 h de rendu).

---

## 6. Pourquoi les vidéos ne sont pas sur GitHub ?

GitHub **refuse les fichiers de plus de 100 Mo**. Les vidéos Darsi
(130+ Mo) ne peuvent donc **pas** être poussées sur le dépôt : elles sont
exclues par le `.gitignore`. Le dépôt contient tout le reste : les scripts,
le texte extrait, les transcriptions, les timings CSV et les rapports
d'alignement. Les vidéos se téléchargent depuis l'espace de travail
(`/home/z/my-project/download/Darsi-N.mp4`).

---

## Lancement automatique : `lancer_darsi.py`

```
python lancer_darsi.py --liste          # montre ce qui est détecté (audios + PDF), ne lance rien
python lancer_darsi.py --installer      # installe faster-whisper/rapidfuzz/PyMuPDF si besoin, puis rend
python lancer_darsi.py --seulement 1    # un seul darsi (numéro de LEÇON)
python lancer_darsi.py --modele medium  # small (défaut) | medium | large-v3 (plus précis, plus lent)
```

* Détecte le PDF et les audios `darsi-N` (ignore `extrait_test.wav`, `*_16k_mono.wav`…).
* **Leçons 2 et 3 échangées par défaut** : l'audio « darsi-3 » est la 2ᵉ leçon du cours
  (pages 6-13), « darsi-2 » la 3ᵉ (pages 14-17). `--sans-echange` pour désactiver.

## Qualité du surlignage (régularisation)

Appliquée automatiquement avant la génération ASS, dans `darsi_video.py` **et** `pipeline/4_video.py` :

| Règle | Effet | Réglage |
|---|---|---|
| Mots isolés | < 3 mots consécutifs = faux positif, supprimé | `--min-cluster` |
| Durée plafonnée | un mot ne reste jamais jaune pendant une pause | `--duree-max-mot` (1,6 s) |
| Surlignage continu | le jaune passe d'un mot au suivant sans clignoter | `--pont` (0,6 s) |
| Anti-chevauchement | un seul mot surligné à la fois | — |

`download/controle_conformite.py` audite/corrige les CSV sans relancer Whisper
(rapport : `download/conformite/rapport_conformite.md`).
