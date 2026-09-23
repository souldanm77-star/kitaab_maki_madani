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

---
Task ID: 5
Agent: Super Z (agent principal)
Task: Session « clone GitHub » — l'utilisateur ne voit pas les vidéos ; après inspection, il regarde les ANCIENNES versions (rollback sandbox). Réclamations : dars1 coupure à 1:01 sans surlignage, dars2/dars3 aucun surlignage, dars4 surligne tout + mauvaises pages. Travail demandé DANS le clone GitHub.

Work Log:
- État constaté : mp4 de sortie remplacés par les anciens rendus (tailles/horodatages différents) ; git local corrompu (commits UUID, fetch en erreur). Transcriptions + timing v3 intacts.
- CLONE propre avec le PAT : /home/z/my-project/kitaab_maki_madani (contient pipeline, upload/, transcriptions, timings v3, fonds) ; un commit GitHub Actions distant a été rebase-sans-conflit.
- DIAGNOSTIC par fenêtres glissantes (scripts/diag_trous.py) : les trous dars1 (33-232 s) scorent TOUS < 0,45 → somali réel, comportement correct (règle 3 états).
- MAIS dars2 0-35 s : « قال الإمام السيوطي… قد أثر الناس في المنسوخ من عدّة… آيات لا تنحصر » = VRAIE lecture du PIED DE PAGE p14 (j≈3045), jamais atteinte par la chaîne LIS monotone (cap tête n+400) — le DP remplissait la fenêtre avec des fausses coïncidences 0,45-0,67 dispersées sur p1. L'utilisateur avait raison.
- ALIGNER v4 (pipeline/3_aligner.py) :
    * PASS 0 « contexte d'ancres » : chaque ancre exacte validée INDÉPENDAMMENT par une petite DP locale (voisins temporels vs voisins du livre) → sauts de page/pieds de page détectés ;
    * garde « formules » (lexique صلى الله عليه وسلم…) : fenêtre ⊂ formules rituelles ≠ lecture ;
    * garde « trou temporel » : trou > 2,5 s ENTRE mots appariés = formule récitée de mémoire (ex. salam @6,6 s coincidant avec la du'a finale p23 — éliminé) ;
    * resoudre_conflits (un mot Whisper = un run) ;
    * filtrer_coherence : un îlot P0 (n < 8, mean < 0,85) exige ≥ 2 voisins à ±180 s ET ±150 mots du livre (les coïncidences somali sont orphelines ; les vraies lectures forment des grappes).
- Crash corrigé : runs chevauchants → seq vide dans l'extension + times[j-1] None (gards + continue).
- Résultats v4 (v3 → v4) : dars1 410 → 495 mots (khutba 0-33 s intacte, fenêtres somali toujours vides) ; dars2 141 → 395 (ouverture p14 28 mots moy 0,84 ✅, faux positif p23 @6,6 s éliminé) ; dars3 558 → 684 ; dars4 239 → 577 (pages recentrées 20-23 : 40/64 runs ; îlots p1/p2/p4 écartés par cohérence).
- config_darsi.json re-pointé vers le clone (upload/ du dépôt) — dépôt autonome.
- Commit + push : `e7dc34e..6067577`.
- Test rendu clone OK : dars2 --max 240 → page 10 (0-25,3 s) puis page 14 (25,3 s+) suit la lecture réelle ; 39 événements de surlignage en 240 s (v3 : 4) ; frame t=31-33 s : 1778 px jaunes ✓.
- Chaîne de rendus complète relancée en arrière-plan depuis le clone : dars2 → dars1 → dars3 → dars4 (~90 min à 3,8× RT).

Stage Summary:
- L'utilisateur regardait les ANCIENNES vidéos (rollback sandbox) — mais son signalement dars2 a révélé un vrai bug (ouvertures/sauts hors progression monotone) : corrigé par PASS 0 + gardes v4.
- Les 4 timings v4 régénérés, poussés sur GitHub ; rendus v4 en cours.
- Pièges : frame exactement à t=start d'un événement ASS = faux « pas de surlignage » ; toujours vérifier par séquence fps ≥ 2.

---
Task ID: 6
Agent: Super Z (agent principal)
Task: Session « clone GitHub + 4 bugs signalés » — travail DANS le clone /home/z/my-project/kitaab_maki_madani. Bugs : dars1 plus de surlignage après 1:01 ; dars2/dars3 aucun surlignage visible ; dars4 sur-surlignage + mauvaises pages affichées.

Work Log:
- État au démarrage : sandbox réinitialisée (rendus v4 perdus du disque, MP4 exclus du git) ; clone propre avec PAT = transcriptions + timings v4 + ASS v4 + CSV intacts (495/395/684/577 mots).
- DIAGNOSTIC des 4 bugs sur les timings v4 :
    * BUG PAGES (dars4 surtout, mais les 4 concernés) : 4_video.py triait les fenêtres de pages par NUMÉRO de page alors que la lecture est non linéaire (dars4 : p16@268s, p17@484s, p1 éparpillé 480→5839s, p20/p21 entrelacées) -> fenêtres à durées NÉGATIVES, pages affichées en retard/à l'envers. Exactement « il lit une autre page, on voit les premières pages ».
    * BUG SUR-SURLIGNAGE (dars4) : l'aligneur v4 matchait les formules RÉCITÉES DE MÉMOIRE (chahada, أما بعد, صلى الله عليه وسلم, titre الجامع لأحكام القرآن) sur p1/p2/p4/p12/p15 — clusters 0,3-0,5 s/mot + hésitations entre deux pages (p4@921 vs p15@926 : 2 pages en 8 s = impossible).
    * dars1 « coupure à 1:01 » : vérifié dans la transcription — 1:01→3:52 = vraie explication SOMALI (texte phonétique arabe absurde), la lecture reprend à 232,6 s (« فإن من أنواع علوم القرآن »). Comportement 3 états CORRECT ; l'utilisateur regardait les anciennes vidéos du rollback.
    * dars2/dars3 : cause = vidéos de rollback regardées par l'utilisateur + couverture v4 déjà accrue.
- NOUVEAU : 4_video.py v5 — stabiliser_sessions() (post-traitement rendu, timing.json v4 intact) :
    * visites (même page, trous <= 20 s) -> sessions (chaînage quelconque <= 8 s) -> page dominante par session ;
    * mesure sur DÉBUTS de mots (les fins Whisper sont gonflées) ;
    * écarte : RAPIDE (>= 4 mots à <= 0,55 s/mot = récité), MINUSCULE (< 3 mots), et non-substantielle isolée ;
    * ZONES de lecture : cluster de >= 3 sessions de même page (trous <= 600 s), >= 8 mots, >= 3 mots/min -> TOUTES les sessions du cluster survivent (lectures fragmentées réelles, p19/p20/p21 dars4) ;
    * RELAIS : session faible gardée si voisine vivante de même page forte ;
    * mots des visites non dominantes écartés (rectangle serait sur la mauvaise page) ;
    * fenêtres CHRONOLOGIQUES (bug v3 corrigé), première fenêtre depuis 0 s, contiguïté concat conservée ;
    * re-export de <dars>_synchronisation.csv depuis les mots RÉELLEMENT surlignés.
- Résultats stabilisés : dars1 446 mots (90 %), fenêtres p1[0-893] p2[893-1752] p3[1752-2199] p2[2199-2213] p3[2213-3447] p4[3447-4633] p5[fin] ; dars2 310 (78 %) p14→p15→p16→p17 ; dars3 471 (69 %) p4→p2→p4→p6→p9→p10→p11→p12→p13 ; dars4 423 (73 %) p18→p19→p20<->p21→p22→p23→p12[4757-4921]→p23. 0 mot hors de la fenêtre de sa page, toutes monotones.
- Cas arbitré : GAP_VISITE 20 s réunit le hadith + définitions p12 de dars4 (rythme global 1,07 s/mot = lecture) ; p18@573 dars4 (8 mots, prose) gardée — fenêtre p18 au début de dars4.
- Test rendu dars2 --max 240 : OK 62 s ; séquence fps=2 : 16/36 frames surlignées pendant la lecture p14 (25-51 s), 0/120 pendant le somali (60-120 s) — règle 3 états respectée dans le rendu.
- Chaîne complète v5 lancée en arrière-plan (scripts/chaine_rendus_v5.sh) : dars2 -> dars1 -> dars3 -> dars4.

Stage Summary:
- 3 causes racine traitées : fenêtres par n° de page (-> chronologiques), formules récitées (-> filtrage rapide/isolé), hésitations d'aligneur (-> sessions à page dominante).
- Pipeline de rendu v5 dans le clone ; timings v4 inchangés ; à venir : vérification dense + livraison Darsi-N.mp4 + push.

---
Task ID: 7
Agent: Super Z (agent principal)
Task: Rendus v5 complets + vérification dense + livraison.

Work Log:
- Constaté : les processus de fond (nohup) sont TUÉS à la fin de chaque appel d'outil dans cette session — la chaîne nohup a rendu ~10 s puis mouru. Impossible de rendre un dars entier (12-40 min) en un appel (limite ~9,5 min).
- NOUVEAU : rendu SEGMENTÉ avec reprise dans 4_video.py :
    * --segment L --par-appel N : rend au plus N tranches nouvelles par invocation, saute les segments complets (ffprobe), concat final SANS ré-encodage ;
    * chaque segment = liste concat recadrée sur [t, fin) + ASS décalé à 0 + seek d'entrée AUDIO uniquement (aucun seek vidéo) ;
    * rejeté au passage : seek de sortie (trop lent : 3 min de filtrage pour 2000 s) et input-seek+copyts (PTS négatifs, mux cassé) ;
    * ass_segmentaire() : ASS vide (en-tête seul) pour les segments sans mot lu (grandes explications somali) ;
    * composer_fond(cache=True) : fonds recomposés uniquement s'ils manquent.
- Rendus : dars2 7×400 s ; dars1 4×1500 s ; dars3 3×1500 s ; dars4 7×1500 s — un segment par appel d'outil, ~6-7 min chacun.
- Vérification MOT À MOT (verif_mots.py : sonde fps=10 calée sur chaque mot, seuil proportionnel à la surface du rect à l'échelle 960×540 — piège : un mot court couvre surtout son glyphe sombre, donc peu de pixels jaune-papier ; seuil fixe = faux négatifs) :
    dars1 14/14 · dars2 20/20 · dars3 14/14 · dars4 16/16 mots surlignés VISIBLES à l'écran.
- Vérification SUIVI DES PAGES dars4 (verif_pages.py : comparaison de frames aux fonds composés) :
    500 s→p18, 1700→p19, 2000→p20, 2600→p21, 2750→p20 (retour en arrière CORRECT), 3500→p22, 4100→p23, 4800→p12 (citation), 5000→p23 — la page suit la lecture chronologiquement, y compris les retours.
- Absence de surlignage pendant le somali vérifiée (0/120 frames 60-120 s dars2).
- LIVRAISON : download/Darsi-1.mp4 (80:19, 140 Mo), Darsi-2.mp4 (45:52, 83 Mo), Darsi-3.mp4 (63:55, 113 Mo), Darsi-4.mp4 (2:30:12, 272 Mo) + CSV (synchronisation stabilisée + segments) dans download/csv_verification/.

Stage Summary:
- 4 vidéos v5 livrées et vérifiées : surlignage mot à mot uniquement sur la lecture réelle du livre, pages chronologiques avec retours, somali jamais surligné.
- Pièges nouveaux documentés : processus de fond tués entre appels (rendu segmenté obligatoire), -t en option d'entrée vs sortie, seek concat sans copyts, seuil de détection proportionnel.
