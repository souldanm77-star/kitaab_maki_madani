#!/bin/bash
# Chaîne de transcription dars2 -> dars3 -> dars4, avec reprise automatique.
# Chaque invocation a un budget de 520 s ; on relance jusqu'à complétion.
cd /home/z/my-project/download/video-recitation || exit 1
LOG=sortie/transcription_chaine.log
echo "=== Démarrage chaîne : $(date) ===" >> "$LOG"
for d in dars2 dars3 dars4; do
  N=0
  while [ ! -f "travail_darsi/$d/transcription.json" ]; do
    N=$((N+1))
    echo "--- $d : invocation $N à $(date) ---" >> "$LOG"
    python3 pipeline/2_transcrire.py --config config_darsi.json --dars "$d" --budget 500 >> "sortie/transcription_$d.log" 2>&1
    # sécurité anti-boucle infinie
    if [ "$N" -ge 60 ]; then
      echo "!!! $d : 60 invocations atteintes, abandon" >> "$LOG"
      break
    fi
  done
  echo "=== $d : transcription terminée à $(date) ===" >> "$LOG"
done
echo "=== TOUTES TRANSCRIPTIONS TERMINEES : $(date) ===" >> "$LOG"
