# Worklog multi-agents

---
Task ID: 1
Agent: Super Z (agent principal)
Task: Reconstruire le projet de vidéos de récitation après reset — une vidéo par dars, page réelle du PDF à droite + image cheikh à gauche + rectangle surligneur mot à mot.

Work Log:
- Reçu les 3 réponses utilisateur : (1) seulement le début du livre pour l'instant, 3 autres dars à venir ; (2) une seule vidéo par section ; (3) afficher la PAGE RÉELLE + rectangle surligneur (pas de texte re-composé).
- Constat clé : le choix « page réelle + rectangle » élimine le blocage historique (ToUnicode arabe défaillant) — l'extraction ne sert plus qu'à l'alignement, plus à l'affichage.
- Validé une nouvelle méthode d'extraction sur le PDF démo : reconstruction par CARACTÈRES (rawdict) triés spatialement RTL + clustering en mots par seuil de gap horizontal auto-calibré (saut max de la distribution). Résultat : ordre de lecture correct et mots propres (بسم الله الرحمن الرحيم…).
- Créé le projet v2 dans /home/z/my-project/download/video-recitation/ : config.json (projet réel), config_demo.json, pipeline/{commun,1_extraire_pdf,2_transcrire,3_aligner,4_video}.py, README.md, demo/ (livre.pdf, audio.mp3 régénéré TTS verset par verset 47,5 s, cheikh_placeholder.png arabesque).
- Étape 1 validée : 2 pages → PNG 200 dpi + mots avec coordonnées (47+32 mots).
- Étape 2 validée : faster-whisper base/int8, 44 mots horodatés.
- Étape 3 validée : DP Needleman-Wunsch + similarité floue, 44/68 appariements directs (64,7 %), interpolation des autres, CSV `mot;debut;fin;page;position;texte`.
- Étape 4 validée : fonds PIL 1920×1080 (cheikh cover-crop gauche + page réelle droite), surligneur ASS (dessins vectoriels \p1, \fad 25 ms, couleur/or opacité réglables), ffmpeg hstack logique par overlays + filtre ass, bascule de page automatique aux débuts de mots.
- DÉBUG MAJEUR : ffmpeg bloquait (0 frame pendant 10 min) puis SIGKILL mystères → cause racine : ffmpeg lit stdin par défaut et bloque la session appelante. Fix : `-nostdin` + garde `-t durée`. Aussi : les processus de fond (nohup/setsid) sont gelés entre les appels d'outils du sandbox → tout rendu doit se terminer dans un seul appel (1,1x temps réel en avant-plan).
- Vérification visuelle par extraction de frames : t=1,2 s → rectangle sur الرَّحْمَٰنِ ✓ ; t=6,9 s → العَالَمِينَ ✓ ; t=30,5 s → bascule page 2 (Al-Ikhlas) + surlignage اللَّهُ ✓.

Stage Summary:
- Livrable : pipeline complet fonctionnel de bout en bout + démo vidéo `download/video-recitation/sortie/dars_demo.mp4` (47 s, 1920×1080, H.264+AAC) + CSV de synchronisation.
- Le système est prêt pour les vrais fichiers de l'utilisateur : déposer livre.pdf, cheikh.jpg, audio/dars1.mp3 dans entree/ + déclarer le dars dans config.json, puis les 4 commandes du README.
- Pour les 3 dars restants : ajouter simplement entrées dans config.darses + fichiers audio (l'extraction du PDF se fait une fois pour tout le livre).
- Piège à retenir : toujours `-nostdin` sur ffmpeg ; toujours rendre en avant-plan dans ce sandbox.

---
Task ID: 2
Agent: Super Z (agent principal)
Task: Corriger la synchronisation du surlignage — audio bilingue (arabe + somali) : surligner UNIQUEMENT les passages où le Cheikh lit le texte du livre, mot à mot ; jamais pendant le somali ni l'arabe hors livre.

Work Log:
- Reçu les 3 fichiers réels : upload/LIVRE.pdf (23 pages TEXTELLES — pas d'OCR nécessaire), upload/IMAGE.jpeg (cheikh 1080x720), upload/Audio darsi-1.mpeg (mp3 80,3 min, 12 kHz).
- Environnement réinitialisé → réinstallation faster-whisper 1.2.1 (multilingual supporté).
- PDF : l'ancien heuristique « plus grand saut » collait les mots (écarts inter-mots réels ~4,5 pt contre trous de ponctuation ~8-13 pt). Remplacé par : frontières de mots sur LETTRES DE BASE uniquement (hors diacritiques) + seuillage bimodal ascendant (1re séparation propre : classe haute ≥ 1 pt et ≥ 2× classe basse) + regroupement des glyphes chevauchants À L'INTÉRIEUR du mot (ligature empilée لله) + diacritiques rattachés au mot le plus proche. Résultat : séparation correcte des mots sur les pages 1-4 et 9-23 (pages de poésie 5-7 partiellement collées, acceptable).
- commun.py : similarité anagramme (0.9) pour الله/لهل/هلل (ligature désordonnée).
- 2_transcrire.py réécrit : découpage auto en 11 morceaux WAV 480 s, transcription multilingual=True, word_timestamps, VAD, beam 1, reprise par cache morceau_XXX.json, fusion + langue par segment. 8490 mots horodatés. Le somali sort en pseudo-arabe déformé (langue détectée 'ar' partout) — sans importance : le filtrage est textuel, pas linguistique.
- 3_aligner.py ENTIÈREMENT RÉÉCRIT (logique de segmentation) : 1) ancrages exacts chaînés par LIS pondéré (Fenwick, monotone i↑ j↑ — survit aux longues interruptions qui décalent tout) ; 2) DP locales Needleman-Wunsch entre ancrages (bande 90, bornée n+400) ; 3) runs de lecture avec tolérance de trous (2 whisper / 2 livre) ; 4) ACTIVATION d'un run : ≥4 mots + moyenne similarité ≥0.70 + ≥2 s + contiguïté span/n ≤1.45 + ≥60 % mots longs + 1 mot ≥4 lettres à ≥0.85 (ou 3 mots à moyenne ≥0.90). C'est le critère « correspondance réelle avec le livre », pas la langue.
- Calibration sur données réelles : vraies lectures moy ≥0.76 (souvent ≥0.90), coïncidences somali plafonnent à ~0.62. 50 runs actifs retenus (232 s de lecture, 4,8 %) : khutba p1, citations des définitions p1-p4, généalogie de l'auteur p4, hadith p6, etc. Progression monotone p1→p23. Résiduel : 2-3 micro-faux positifs (du'a finale sur p23, formules) — compromis documenté.
- 4_video.py adapté : fenêtres de pages basées sur les mots LUS uniquement (la page reste affichée sans surlignage pendant somali/explications), surlignage ASS restreint aux états whisper/interpole, rendu par DÉMUXEUR CONCAT (au lieu de N entrées -loop — indispensable pour 80 min), ajout --max (test) et --sortie fonctionnel.
- BUG MAJEUR CORRIGÉ : ordre des filtres — avec le concat, `ass` AVANT `fps=25` ne surlignait que la 1re frame de chaque page (une frame VFR de 232 s puis dupliquée). Fix : `fps=25,ass=…` (fps normalise les timestamps D'ABORD). Vérifié par frames : t=2,5 s → rectangle sur ونستعينه ✓ ; t=6,0 s → شرور ✓.
- Rendu complet dars1.mp4 lancé en arrière-plan (nohup), ~3,8× temps réel ≈ 21 min. Piège shell : `A && B &` background TOUTE la chaîne — utiliser (nohup … &) groupé.

Stage Summary:
- Pipeline complet v3 : 1_extraire_pdf (Otsu+ligatures) → 2_transcrire (morceaux+reprise+multilingue) → 3_aligner (ancrages LIS + DP locales + runs + filtre qualité = segmentation lecture/somali/hors_livre) → 4_video (concat+ASS, surlignage mot à mot uniquement sur lecture réelle du livre).
- Livrables : sortie/dars1.mp4 (80 min, 1920x1080), sortie/dars1_synchronisation.csv (355 mots surlignés), sortie/dars1_segments.csv (chronologie lecture/somali/hors_livre horodatée pour vérification humaine).
- Config du dars réel : config_darsi.json (chemins absolus upload/, pages 1-23, whisper small/int8/multilingual).
- Pour les 3 dars suivants : ajouter l'entrée dans config_darsi.json darses + l'audio ; relancer étapes 2→4 (extraction déjà faite pour tout le livre).

---
Task ID: 3
Agent: Super Z (agent principal)
Task: Finalisation — corrections de rendu, vérification frame par frame, livraison dars1.mp4.

Work Log:
- BUG 1 corrigé : ordre des filtres ffmpeg — `ass` AVANT `fps=25` avec le démuxeur concat ne surlignait que la 1re frame de chaque page (frame VFR longue dupliquée par fps). Fix : `fps=25,ass=…` (fps normalise les timestamps D'ABORD).
- BUG 2 corrigé : fenêtres de pages CHEVAUCHANTES (d0 page N+1 = 1er mot − 0,4 s < d1 page N) → le concat accumulait ~0,4 s de dérive par transition ; en fin de vidéo (7 pages) la page 23 s'affichait 2,4 s en retard et ses rectangles tombaient sur la page 10. Fix : fenêtres CONTIGUÏES (d1(k) = d0(k+1), la page suivante apparaît 0,4 s avant son 1er mot lu).
- Piège de vérification : `-ss T -i video` (seek d'entrée) sur cette vidéo donne une frame DÉCALÉE (keyframes rares aux transitions de pages) → les frames « sans surlignage » à 906 s étaient un artefact d'extraction. Méthode fiable : seek hybride `-ss T-20 -i v -ss 20` ou seek de sortie. Tests croisés (fond gris + ASS minimal + seek sortie) ont prouvé que le rendu était correct.
- Rendu final relancé avec fenêtres contiguës : pages affichées 0→886,4→1779,8→2588,2→2992,8→3609,7→4815,0→fin (7 pages : 1,2,3,4,6,10,23).
- Vérifications frame par frame (seek hybride) : t=2,5 s → ونستعينه surligné ✓ ; t=6 s → شرور ✓ ; t=700 s → page 1 affichée SANS surlignage (explication) ✓ ; t=906 s → المكيَّ surligné page 2 ✓ ; t=3200 s → page 6 (poésie) sans surlignage (somali) ✓ ; t=4816 s → page 23 affichée à l'heure + صلى الله surligné ✓.

Stage Summary:
- LIVRABLE FINAL : download/video-recitation/sortie/dars1.mp4 — 80 min 19 s, 1920x1080 H.264+AAC, prêt YouTube.
- Comportement conforme aux 4 règles : surlignage mot à mot UNIQUEMENT quand l'audio correspond au texte du livre affiché ; rien pendant le somali ; rien pendant l'arabe hors livre ; reprise automatique au bon mot après chaque interruption.
- Rapports de contrôle pour l'utilisateur : sortie/dars1_segments.csv (chronologie horodatée lecture/somali/hors_livre) et sortie/dars1_synchronisation.csv (355 mots surlignés avec temps/page/position).
- Résiduel documenté : 2-3 micro-runs de 3-7 mots (du'a finale p23, hadith cité p6) où formules arabes coïncident avec le texte de la page — visuellement cohérent (mots réellement prononcés, page correcte).
- Pour les dars 2-4 : ajouter audio + entrée dans config_darsi.json → étapes 2→4 (l'extraction PDF couvre déjà tout le livre).
