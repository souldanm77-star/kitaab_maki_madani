# Worklog multi-agents

---
Task ID: 1
Agent: Super Z (agent principal)
Task: Reconstruire le projet de vidéos de récitation après reset — une vidéo par dars, page réelle du PDF à droite + image cheikh à gauche + rectangle surligneur mot à mot.

Work Log:
- Reçu les 3 réponses utilisateur : (1) seulement le début du livre pour l'instant, 3 autres dars à venir ; (2) une seule vidéo par section ; (3) afficher la PAGE RÉELLE + rectangle surligneur (pas de texte re-composé).
- Constat clé : le choix « page réelle + rectangle » élimine le blocage historique (ToUnicode arabe défaillant) — l'extraction ne sert plus qu'à l'alignement, plus à l'affichage.
- Validé une nouvelle méthode d'extraction sur le PDF démo : reconstruction par CARACTÈRES (rawdict) triés spatialement RTL + clustering en mots par seuil de gap horizontal auto-calibré. Résultat : ordre de lecture correct et mots propres.
- Créé le projet v2 dans /home/z/my-project/download/video-recitation/ : config.json (projet réel), config_demo.json, pipeline/{commun,1_extraire_pdf,2_transcrire,3_aligner,4_video}.py, README.md, demo/.
- DÉBUG MAJEUR : ffmpeg lit stdin par défaut → fix : `-nostdin` + garde `-t durée`. Processus de fond gelés entre les appels d'outils du sandbox (observation de la session précédente).
- Vérification visuelle par extraction de frames : surlignage correct sur démo.

Stage Summary:
- Pipeline complet fonctionnel de bout en bout + démo vidéo `sortie/dars_demo.mp4`.
- Piège à retenir : toujours `-nostdin` sur ffmpeg.

---
Task ID: 2
Agent: Super Z (agent principal)
Task: Corriger la synchronisation du surlignage — audio bilingue (arabe + somali) : surligner UNIQUEMENT les passages où le Cheikh lit le texte du livre, mot à mot ; jamais pendant le somali ni l'arabe hors livre.

Work Log:
- Reçu les 3 fichiers réels : upload/LIVRE.pdf (23 pages TEXTELLES), upload/IMAGE.jpeg (cheikh), upload/Audio darsi-1.mpeg (mp3 80,3 min, 12 kHz).
- PDF : frontières de mots sur LETTRES DE BASE + seuillage bimodal + regroupement des glyphes chevauchants (ligatures) + diacritiques rattachés au mot le plus proche.
- commun.py : similarité anagramme (0.9) pour الله/لهل/هلل.
- 2_transcrire.py : découpage 11 morceaux WAV 480 s, multilingual=True, word_timestamps, reprise par cache morceau_XXX.json. 8490 mots horodatés pour dars1.
- 3_aligner.py v2 : ancrages exacts chaînés par LIS (Fenwick) + DP locales Needleman-Wunsch + runs de lecture + filtre de qualité (≥4 mots, moy ≥0.70, ≥2 s…). 50 runs actifs (232 s de lecture).
- 4_video.py : fenêtres de pages sur mots LUS, surlignage ASS restreint, rendu par DÉMUXEUR CONCAT. Fix ordre filtres : `fps=25,ass=…`.

Stage Summary:
- Pipeline v3 : extraction → transcription → détection lectures → vidéo. dars1.mp4 (80 min) livré.

---
Task ID: 3
Agent: Super Z (agent principal)
Task: Finalisation — corrections de rendu, vérification frame par frame, livraison dars1.mp4.

Work Log:
- BUG 1 : ordre des filtres ffmpeg (`fps=25,ass=…` au lieu de `ass,fps=25`).
- BUG 2 : fenêtres de pages CONTIGUÏES (d1(k) = d0(k+1)) pour éviter la dérive du concat.
- Piège de vérification : seek hybride `-ss T-20 -i v -ss 20` (les seeks simples tombent sur des keyframes rares).
- Vérifications frame par frame : surlignage correct aux 5 points de contrôle.

Stage Summary:
- LIVRABLE : sortie/dars1.mp4 (80 min 19 s, 1920x1080 H.264+AAC) + CSV de contrôle (segments + synchronisation).
- Résiduel : 2-3 micro-runs (formules du'a p23) — visuellement cohérents.

---
Task ID: 4
Agent: Super Z (agent principal)
Task: Session de reprise — (a) push GitHub avec le PAT fourni par l'utilisateur ; (b) corriger « dars2 aucun mot sélectionné » et « dars1 saute des phrases/mots » ; (c) intégrer les audios dars3 et dars4 ; (d) régénérer les 4 vidéos.

Work Log:
- (a) PUSH GITHUB RÉUSSI : remote origin = https://<PAT>@github.com/souldanm77-star/kitaab_maki_madani.git ; push `dc25a75..d02e925 main -> main`. .gitignore couvre déjà mp4/wav/pages/secrets.
- Diagnostic dars2 : la transcription s'était ARRÊTÉE à 3/6 morceaux (contexte précédent interrompu) → timing.json inexistant → aucune vidéo surlignée possible. C'était la cause racine de « AUCUN MOT N'EST SELECTIONNE ».
- Transcriptions complétées avec reprise par cache (--budget 520 par invocation) : dars2 = 4558 mots (45,9 min), dars3 = 6687 mots (63,9 min, 8 morceaux), dars4 = 13227 mots (150,2 min, 19 morceaux !).
- Alignements (3_aligner.py v3 à deux passes : ancrages LIS + DP locales + PASS 2 rattrapage des trous) :
    dars1 : 40 runs, 410 mots surlignés (392 whisper + 18 interpolés), pages 1,2,3,4,6 — progression monotone, interpolation intra-run.
    dars2 : 10 runs, 141 mots, pages 10,14,15,16,17,23, 189 s de lecture (6,9 %) — N'EST PLUS VIDE.
    dars3 : 38 runs, 558 mots, pages 2,4,6..13, 614,6 s (17,7 %) — détection riche (moy 0,9+ sur nombreux runs).
    dars4 : 21 runs, 239 mots, pages 20,21,22,23, 227,9 s (3,3 %).
- Vérification visuelle dars2 : frame t=226 s → page 10 à droite, rectangle jaune sur « لازم » ✓ (premier mot réellement détecté).
- TEST RENDU : 240 s rendus en 62 s (3,9× temps réel) sur 2 cœurs. Les processus nohup SURVIVENT entre les appels d'outils dans cette session (contrairement à l'observation antérieure) → rendus séquentiels en arrière-plan.
- Rendus complets lancés en séquence arrière-plan : dars2.mp4 OK (45,9 min, 80,5 Mo, 2752,2 s), puis dars1 (80,3 min), dars3 (63,9 min), dars4 (150,2 min).
- Vérifications finales sur les vidéos rendues (extraction de frames + détection de pixels jaunes) :
    dars1 t=2,5 s → ونعوذ surligné p1 ✓ ; t=906,0 s → المكيَّ surligné p2 ✓ (une fausse alerte « pas de surlignage » à 906 s était un artefact d'extraction : frame exactement à la frontière t=start où t<end échoue — confirmé par séquence fps=2 : 906,0 → 1128 px jaunes).
    dars2 t=226 s → لازم surligné p10 ✓ (première vidéo dars2 jamais surlignée).
    dars3 t=3414 s → وضعَ surligné p13 ✓ (1713 px).
    dars4 t=4681 s → surlignage actif p23 ✓ (1313 px).
- Vérifié aussi la CONTIGUÏTÉ intra-run dars1 : run 1 (khutba) couvre les positions livre 2→57 sans trou (3 mots interpolés seulement).
- Push GitHub : `d02e925..3111ee0` (transcriptions + timings + CSV des 4 dars).

Stage Summary:
- CAUSE RACINE dars2 identifiée et corrigée (transcription incomplète).
- LIVRABLES FINAUX dans download/video-recitation/sortie/ : dars1.mp4 (80,3 min, 140 Mo), dars2.mp4 (45,9 min, 80 Mo), dars3.mp4 (63,9 min, 112 Mo), dars4.mp4 (150,2 min, 274 Mo) — 1920×1080 H.264+AAC, cheikh à gauche / page réelle à droite, surlignage mot à mot uniquement sur la lecture réelle du livre.
- Statistiques de surlignage : dars1 = 410 mots (40 runs, pages 1-6), dars2 = 141 mots (10 runs, pages 10-23), dars3 = 558 mots (38 runs, pages 2-13), dars4 = 239 mots (21 runs, pages 20-23).
- CSV de contrôle pour vérification humaine : sortie/darsN_segments.csv (chronologie lecture/somali/hors_livre) et sortie/darsN_synchronisation.csv (mots surlignés horodatés).
- Piège documenté : l'extraction d'une frame EXACTEMENT à t=start d'un événement ASS peut rater le rectangle (frontière flottante) — toujours vérifier avec une séquence fps≥2.
