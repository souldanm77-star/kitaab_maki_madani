#!/bin/bash
# Chaîne de rendus complète v5 — un dars après l'autre
cd /home/z/my-project/kitaab_maki_madani/download/video-recitation

for d in dars2 dars1 dars3 dars4; do
    echo "=== $(date '+%H:%M:%S') rendu $d ===" >> sortie/rendu_chaine_v5.log
    python3 pipeline/4_video.py --config config_darsi.json --dars $d \
        >> "sortie/rendu_$d.log" 2>&1
    code=$?
    echo "=== $(date '+%H:%M:%S') $d fini (code $code) ===" >> sortie/rendu_chaine_v5.log
    if [ $code -ne 0 ]; then
        echo "ERREUR sur $d — arrêt de la chaîne" >> sortie/rendu_chaine_v5.log
        exit $code
    fi
done
echo "=== CHAÎNE COMPLETE TERMINÉE $(date '+%H:%M:%S') ===" >> sortie/rendu_chaine_v5.log
