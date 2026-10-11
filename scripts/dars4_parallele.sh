#!/bin/bash
# dars4 : deux moitiés de morceaux en parallèle (2 cœurs)
cd /home/z/my-project/download/video-recitation || exit 1
mkdir -p sortie
DEB="$1"; MIL="$2"; FIN="$3"     # ex: 5 12 19
( python3 pipeline/2_transcrire.py --config config_darsi.json --dars dars4 --budget 500 --debut "$DEB" --fin "$MIL" >> sortie/transcription_dars4_A.log 2>&1 ) &
PA=$!
( python3 pipeline/2_transcrire.py --config config_darsi.json --dars dars4 --budget 500 --debut "$MIL" --fin "$FIN" >> sortie/transcription_dars4_B.log 2>&1 ) &
PB=$!
wait $PA; RA=$?
wait $PB; RB=$?
echo "fin A=$RA B=$RB $(date +%H:%M:%S)"
N=$(ls travail_darsi/dars4/morceaux/*.json 2>/dev/null | wc -l)
echo "dars4 morceaux faits: $N/19"
