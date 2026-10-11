#!/bin/bash
# Chaîne de production : rendus dars1+dars2 (alignements prêts),
# puis alignement + rendu de dars3/dars4 dès transcription prête.
cd /home/z/my-project/download/video-recitation

echo "=== rendu dars2 $(date) ==="
python3 pipeline/4_video.py --config config_darsi.json --dars dars2
echo "=== rendu dars1 $(date) ==="
python3 pipeline/4_video.py --config config_darsi.json --dars dars1

for d in dars3 dars4; do
  echo "=== attente transcription $d $(date) ==="
  while [ ! -f "travail_darsi/$d/transcription.json" ]; do sleep 30; done
  echo "=== alignement $d $(date) ==="
  python3 pipeline/3_aligner.py --config config_darsi.json --dars "$d" \
      > "/tmp/align_$d.log" 2>&1
  echo "=== rendu $d $(date) ==="
  python3 pipeline/4_video.py --config config_darsi.json --dars "$d"
done
echo "=== TOUT EST FINI $(date) ==="
