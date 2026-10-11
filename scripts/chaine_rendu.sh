#!/bin/bash
# Chaîne de rendu des 4 vidéos (les dars déjà rendus sont sautés).
# Chaque vidéo est rendue dans un .part.mp4 puis renommée une fois terminée.
cd /home/z/my-project/download/video-recitation || exit 1
LOG=sortie/rendu_chaine.log
echo "=== Démarrage chaîne de rendu : $(date) ===" >> "$LOG"
for d in dars2 dars3 dars4 dars1; do
  if [ -f "sortie/$d.mp4" ]; then
    echo "--- $d : déjà rendu, sauté ---" >> "$LOG"
    continue
  fi
  echo "--- $d : rendu démarré à $(date) ---" >> "$LOG"
  python3 pipeline/4_video.py --config config_darsi.json --dars "$d" \
      --sortie "sortie/${d}.part.mp4" >> "sortie/rendu_$d.log" 2>&1
  if [ -f "sortie/${d}.part.mp4" ]; then
    mv "sortie/${d}.part.mp4" "sortie/${d}.mp4"
    echo "--- $d : OK à $(date) ---" >> "$LOG"
  else
    echo "--- $d : ÉCHEC à $(date) ---" >> "$LOG"
  fi
done
echo "=== CHAÎNE DE RENDU TERMINÉE : $(date) ===" >> "$LOG"
