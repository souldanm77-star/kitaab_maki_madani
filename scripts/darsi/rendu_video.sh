#!/bin/bash
# Pilote de rendu : une tranche par appel (anti-timeout), puis concat.
# Usage : rendu_video.sh <numéro_de_tranche 1..8>
set -e
N=$1
DOS=/home/z/my-project/travail/darsi1
SORTIE=/home/z/my-project/download/darsi1
mkdir -p "$SORTIE"
DUREE=4819.296
TRANCHE=610
DEBUT=$(python3 -c "print(($N-1)*$TRANCHE)")
FIN=$(python3 -c "print(min($N*$TRANCHE, $DUREE))")
cd /home/z/my-project
python3 -u scripts/darsi/5_video.py --debut "$DEBUT" --fin "$FIN" \
    --sortie "$SORTIE/part_$N.mp4"
echo "TRANCHE $N OK"
