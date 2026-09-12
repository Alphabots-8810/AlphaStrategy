#!/bin/bash
# Re-run alliance comparisons after the discrete-objective tie-break fix.
cd "$(dirname "$0")/.."
PY=.venv/bin/python
for ev in regular champs; do
  echo "[$(date +%T)] alliance-$ev start"
  $PY experiments/alliance.py --event $ev --matches 400 --iters 300 --scen 16 > results/alliance_$ev.log 2>&1
  echo "[$(date +%T)] alliance-$ev exit $?"
done
echo "[$(date +%T)] ALL DONE"
