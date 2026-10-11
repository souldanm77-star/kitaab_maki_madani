#!/bin/bash
# Transcription PARALLÈLE : 2 dars en même temps (2 cœurs CPU)
cd /home/z/my-project/download/video-recitation || exit 1
mkdir -p sortie
A="$1"; B="$2"      # ex: dars2 dars3
( python3 pipeline/2_transcrire.py --config config_darsi.json --dars "$A" --budget 500 >> "sortie/transcription_$A.log" 2>&1 ) &
PA=$!
( python3 pipeline/2_transcrire.py --config config_darsi.json --dars "$B" --budget 500 >> "sortie/transcription_$B.log" 2>&1 ) &
PB=$!
wait $PA; RA=$?
wait $PB; RB=$?
echo "fin $A=$RA $B=$RB $(date +%H:%M:%S)"
tail -1 "sortie/transcription_$A.log" 2>/dev/null
tail -1 "sortie/transcription_$B.log" 2>/dev/null
