#!/bin/bash
# Rendu SEGMENTÉ résumable d'un dars : parts de SEG s, concat final.
# Usage: rendre_segments.sh <dars> <duree_audio> [seg_size]
set -e
cd /home/z/my-project/download/video-recitation || exit 1
D="$1"; DUREE="$2"; SEG="${3:-480}"
BUDGET="${BUDGET_RENDU:-500}"
T0=$(date +%s)
mkdir -p sortie/parts

# nb de segments
NSEG=$(python3 -c "import math; print(math.ceil($DUREE / $SEG))")
echo "=== $D : $NSEG segments de ${SEG}s (durée $DUREE s) ==="

for ((k=0; k<NSEG; k++)); do
  DEB=$(python3 -c "print($k * $SEG)")
  FIN=$(python3 -c "print(min(($k+1) * $SEG, $DUREE))")
  PART="sortie/parts/${D}_part_$(printf '%05d' "$DEB").mp4"
  # part valide ? (terminée proprement = durée ~ FIN-DEB)
  if [ -f "$PART" ]; then
    OK=$(python3 - "$PART" "$DEB" "$FIN" <<'PY'
import sys, subprocess
part, deb, fin = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
try:
    r = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
                        '-of','csv=p=0', part], capture_output=True, text=True)
    d = float(r.stdout.strip())
    print('OUI' if d >= (fin - deb) - 1.5 else 'NON')
except Exception:
    print('NON')
PY
)
    if [ "$OK" = "OUI" ]; then echo "part $k déjà prête"; continue; fi
    rm -f "$PART"
  fi
  MAINT=$(date +%s)
  if [ $((MAINT - T0)) -gt $BUDGET ]; then
    echo "⏸ budget atteint avant segment $k ($k/$NSEG prêts)"; exit 0
  fi
  echo "--- segment $k: [$DEB → $FIN] ---"
  python3 pipeline/4_video.py --config config_darsi.json --dars "$D" \
      --segment "$DEB" "$FIN" >> "sortie/rendu_$D.log" 2>&1
done

# ---- concat final ----
FINAL="sortie/$D.mp4"
if [ ! -f "$FINAL" ] || [ "${FORCE_CONCAT:-0}" = "1" ]; then
  LIST="sortie/parts/${D}_liste.txt"
  : > "$LIST"
  for ((k=0; k<NSEG; k++)); do
    DEB=$(python3 -c "print($k * $SEG)")
    echo "file '$(pwd)/sortie/parts/${D}_part_$(printf '%05d' "$DEB").mp4'" >> "$LIST"
  done
  ffmpeg -nostdin -y -hide_banner -loglevel error -f concat -safe 0 -i "$LIST" \
      -c copy -movflags +faststart "$FINAL"
  echo "=== CONCAT OK -> $FINAL ==="
fi
echo "=== $D TERMINÉ ==="
