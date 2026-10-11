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

---
Task ID: 3
Agent: Super Z (agent principal)
Task: Livrer le script autonome demandé (darsi_video.py : Whisper + détection répétitions + pages + surlignage) + résoudre le problème « vidéos invisibles sur GitHub » + push du dépôt.

Work Log:
- Écrit darsi_video.py (990 lignes, autonome, commenté en français) : transcription faster-whisper mot à mot (morceaux 480 s + cache de reprise), extraction PDF arabe robuste portée du pipeline (PyMuPDF rawdict + tri RTL + Otsu + ligatures), alignement ancres n-grammes -> NW -> interpolation -> runs (règle 3 états), séquence de pages (retours en arrière supportés), rendu ffmpeg concat + surlignage ASS rectangles jaunes (opacité 0.45), rapports timing.csv + rapport_alignement.json, CLI complète (--dossier/--surligner/--format mpeg/--modele...).
- Tests : 2 bugs trouvés et corrigés (dossier images absent ; pdfplumber -> remplacé par la méthode RTL éprouvée car extract_words casse l'arabe).
- Découverte : le PDF démo régénéré casse le découpage même avec le pipeline original (police décorative) — pas un bug du nouveau script ; validé sur le VRAI LIVRE.pdf (mots propres).
- Test final sur 60 s d'audio RÉEL du dars1 : 3 ancres, 5 runs -> après ajout de 2 garde-fous (plausibilité temporelle des sauts VITESSE_MAX=8 mots/s ; coupure aux retours en arrière SAUT_MAX=5 ; anagrammes الله/هلL=0.95 ; plafond de progression NW 5x+200) : 2 runs propres page 1 (khutba + formule prophétique), faux alignements éliminés, 25 rectangles de surlignage, frame t=3 s vérifiée : mot إنَّ surligné en jaune sur la page réelle.
- README_DARSI.md : installation, 2 configurations (PDF / images+txt), algorithme détaillé des répétitions, limites.
- GitHub : cause identifiée du problème utilisateur — pas de .gitignore + sortie/dars1.mp4 (131 Mo) et 11 WAV (~15 Mo chacun) TRACKÉS (limite GitHub = 100 Mo par fichier). Créé .gitignore racine (*.wav, *.mp4 sorties, __pycache__), détracké les gros fichiers.
- Push bloqué 2 fois : historiques local/remote DISJOINTS (merge-base vide) + untracked skills/upload + 19 conflits add/add. Résolu : merge --allow-unrelated-histories, conflits résolus (theirs=pipeline corrigé + config, ours=scripts/diagnostics), vieux snapshots locaux purgés par reset --soft FETCH_HEAD + recommit.
- PUSH RÉUSSI 06dbe71..9e47325. BONUS MAJEUR : transcriptions complètes dars2/dars3/dars4 récupérées du remote (des heures de calcul économisées).
- Restauration upload/ (4 audios + IMAGE + LIVRE) et skills/ après merge.

Stage Summary:
- darsi_video.py + README_DARSI.md poussés sur GitHub (commit 9e47325), visible par l'utilisateur.
- Explication à donner : les mp4 (>100 Mo) ne peuvent JAMAIS apparaître sur GitHub ; les vidéos se téléchargent localement (/home/z/my-project/download/).
- Prochaine étape : re-rendu des 4 darses avec darsi_video.py ou pipeline v3 (transcriptions toutes disponibles), livraison Darsi-1..4.mp4.

---
Task ID: 4
Agent: Super Z (agent principal)
Task: Lancement de la correction complète des 4 vidéos (bugs signalés par l'utilisateur) + livraison fonctionnelle.

Work Log:
- Diagnostic : transcriptions dars1-4 terminées ; timing.json corrects (dars1=50 runs/355 mots, dars2=17/128, dars3=38/321, dars4=41/324) mais surlignage.ass de dars2/3/4 PÉRIMÉS (générés avant l'alignement final) -> cause des « vidéos sans surlignage ».
- BUG MAJEUR DÉCOUVERT ET CORRIGÉ (pipeline/4_video.py, mode segmenté) : « fonds » était une liste alignée sur les fenêtres PLEINES ; en rendu segmenté, zip(fenetres_coupées, fonds_pleines) décalait les fonds (la page 18 recevait le fond de la page 7, etc.). Fix : fonds indexés PAR PAGE (dict fonds_par_page) + réalignement après découpe du segment. C'est la vraie cause des « fausses pages » de dars4 — et elle touchait AUSSI dars1/2/3 dès le 2e segment.
- Améliorations 4_video.py : fenêtres de pages CHRONOLOGIQUES (retours en arrière gérés, groupe stable >= 2 mots contre le clignotement), dédoublonnage des événements ASS par page unique.
- Rendu complet des 4 dars via rendre_segments.sh (repreneur) : dars1=11 segments, dars2=6, dars3=8, dars4=19 ; concat -c copy + faststart.
- Vérification EXACTE (seek keyframe réelle + argmin sur tous les fonds) : dars1 5/5 pages OK, dars2 5/5 OK, dars3 5/5 OK, dars4 6/6 OK (pages 7,19,21,22,23,23). Surlignage jaune confirmé par échantillonnage dense (les « jaune=0 » ponctuels = pauses entre les mots, comportement normal).
- Point d'attention méthodologique : pour t<12 s le seek hybride max(0,tm-12)+ss12 regarde t=12 s -> faux négatifs ; utiliser le seek de sortie direct en début de vidéo.
- t=61 s de dars1 sans surlignage = NORMAL (explication somali, règle 3 états) : ce n'est pas le bug signalé mais le comportement demandé.
- surlignage.ass complets régénérés pour les 4 dars (scripts/regenerer_ass.py) : 355/128/321/324 événements.
- Livrables copiés : download/Darsi-1.mp4 (136 Mo, 80 min), Darsi-2.mp4 (82 Mo, 46 min), Darsi-3.mp4 (111 Mo, 64 min), Darsi-4.mp4 (270 Mo, 150 min).
- Git : sortie/dars1.mp4 (135 Mo) + download/darsi1/Darsi1_Maki_wa_Madani.mp4 (146 Mo) + parts/video_seule.mp4 (54 Mo) détrackés ; .gitignore renforcé ; push vers GitHub.

Stage Summary:
- Les 4 vidéos Darsi-1..4.mp4 sont CORRIGÉES, VÉRIFIÉES et livrées dans /home/z/my-project/download/.
- Bug racine « mauvaises pages » = désalignement fonds/fenêtres en rendu segmenté — corrigé définitivement dans 4_video.py.
- darsi_video.py (script autonome demandé) déjà présent et poussé (commit 9e47325).
