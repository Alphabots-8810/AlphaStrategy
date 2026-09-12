#!/bin/bash
# Reruns every experiment whose output the README cites (tests excluded), on the final code.
cd "$(dirname "$0")/.."
PY=.venv/bin/python
echo "[$(date +%T)] validate start"
$PY experiments/validate.py --matches 4000 --planner-matches 200 > results/validate_elite.log 2>&1
echo "[$(date +%T)] validate exit $?"
$PY experiments/tune_mcts.py --rollouts proc --c 0.5 --prune 0,25 --matches 120 \
    --out results/tune_mcts_prune.md > results/tune_mcts_prune.log 2>&1
echo "[$(date +%T)] tune_mcts prune exit $?"
$PY experiments/tune_mcts.py --rollouts proc --c 0.02,0.05,0.1,0.2,0.5 --prune 0 --matches 120 \
    --out results/tune_mcts_sweep.md > results/tune_mcts_sweep.log 2>&1
echo "[$(date +%T)] tune_mcts sweep exit $?"
( $PY experiments/sensitivity.py --dp --matches 3000 > results/sensitivity.log 2>&1; echo "[$(date +%T)] sensitivity exit $?" ) &
echo "[$(date +%T)] alliance-regular start"
$PY experiments/alliance.py --event regular --matches 400 --iters 300 --scen 16 --win-scen 32,64 --z 1 \
    --seed-offset 200000 > results/alliance_regular.log 2>&1
echo "[$(date +%T)] alliance-regular exit $?"
echo "[$(date +%T)] alliance-champs start"
$PY experiments/alliance.py --event champs --matches 400 --iters 300 --scen 16 --win-scen "" --z 1 \
    --seed-offset 200000 \
    --only greedy-proc,greedy-coop,rp-seeker,rollout-points-greedy-proc-16,rollout-margin-greedy-proc-16,rollout-rp-greedy-proc-16-z1 \
    > results/alliance_champs.log 2>&1
echo "[$(date +%T)] alliance-champs exit $?"
wait
echo "[$(date +%T)] tie-rule A/B start"
$PY experiments/tie_rule_ab.py > results/tie_rule_ab.log 2>&1
echo "[$(date +%T)] tie-rule A/B exit $?"
echo "[$(date +%T)] ALL DONE"
