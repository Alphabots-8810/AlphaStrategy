#!/bin/bash
# Re-run every experiment on the fixed code, sequentially (each uses all worker cores).
cd "$(dirname "$0")/.."
PY=.venv/bin/python
echo "[$(date +%T)] validate start";    $PY experiments/validate.py --matches 4000 --planner-matches 200 > results/validate_elite.log 2>&1; echo "[$(date +%T)] validate exit $?"
echo "[$(date +%T)] alliance-regular";  $PY experiments/alliance.py --event regular --matches 400 --iters 300 --scen 16 > results/alliance_regular.log 2>&1; echo "[$(date +%T)] alliance-regular exit $?"
echo "[$(date +%T)] alliance-champs";   $PY experiments/alliance.py --event champs --matches 400 --iters 300 --scen 16 > results/alliance_champs.log 2>&1; echo "[$(date +%T)] alliance-champs exit $?"
echo "[$(date +%T)] sensitivity";       $PY experiments/sensitivity.py --dp --matches 3000 > results/sensitivity.log 2>&1; echo "[$(date +%T)] sensitivity exit $?"
echo "[$(date +%T)] ALL DONE"
