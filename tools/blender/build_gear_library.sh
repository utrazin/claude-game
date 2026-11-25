#!/bin/sh
# Regenerates the wheel library used by the game (module 0.02 m, metres, Y-up).
# Usage: sh tools/blender/build_gear_library.sh
set -e
OUT=game/assets/models/gears
mkdir -p "$OUT"
for T in 12 18 24 30 36 42 48 54 60 66 72 78 84 90 96 102 108 114 120; do
  if [ $T -le 18 ]; then S=0; elif [ $T -le 42 ]; then S=4; elif [ $T -le 84 ]; then S=5; else S=6; fi
  python3 -I tools/blender/gear.py --teeth $T --module 0.02 --thickness 0.05 --spokes $S --rim 0.12 --hub 0.16 --out "$OUT/wheel_$T.glb" | grep tris | sed "s/^/wheel_$T /"
done
python3 -I tools/blender/gear.py --teeth 12 --module 0.02 --thickness 0.14 --spokes 0 --hub 0.3 --out "$OUT/pinion_12.glb" | grep tris | sed "s/^/pinion_12 /"
