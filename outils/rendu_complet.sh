#!/bin/bash
# Rendu complet des 4 dars — séquentiel (2 cœurs CPU), rendu segmenté avec reprise
cd /home/z/my-project/kitaab_maki_madani/download/video-recitation
for d in dars2 dars1 dars3 dars4; do
  echo "=== RENDU $d ($(date '+%H:%M:%S')) ===" >> sortie/rendu_v6.log
  python3 pipeline/4_video.py --config config_darsi.json --dars $d \
    --segment 240 --par-appel 999 >> sortie/rendu_v6.log 2>&1
  echo "=== FIN $d ($(date '+%H:%M:%S')) rc=$? ===" >> sortie/rendu_v6.log
done
echo "TOUS LES RENDUS TERMINES $(date '+%H:%M:%S')" >> sortie/rendu_v6.log
