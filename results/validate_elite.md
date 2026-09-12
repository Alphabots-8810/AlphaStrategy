# Validation — profile `elite`, TELEOP only, dt=0.25s, k=5, blocking=B, event=regular

DP solved in 51.0s over 562,432 configs x 540 steps. **V\* = 108.635** expected TELEOP points from the REEF, empty-handed.

## Heuristics (4000 CRN matches)

| policy | mean TELEOP pts (95% CI) | paired diff vs DP-optimal | check |
|---|---|---|---|
| DP-optimal (replayed in sim) | 108.65 ± 0.19 | — | V2 PASS (|mean−V\*|=0.02) |
| greedy-net | 90.68 ± 0.18 | -17.97 ± 0.15 | V3 PASS |
| greedy-proc | 105.28 ± 0.19 | -3.37 ± 0.09 | V3 PASS |
| greedy-coop | 97.13 ± 0.17 | -11.53 ± 0.13 | V3 PASS |
| rp-seeker | 86.49 ± 0.13 | -22.16 ± 0.16 | V3 PASS |

## Planners (fresh seeds 100000..100199, base heuristic greedy-proc: 105.26, gap -3.54)

| planner | mean | paired gap vs DP | vs base heuristic | CPU s/match |
|---|---|---|---|---|
| CRN rollout, 8 scenarios/candidate | 105.80 | -3.00 ± 0.47 (-2.8%) | +0.54 ± 0.37 | 0.2 |
| CRN rollout, 16 scenarios/candidate | 106.92 | -1.88 ± 0.40 (-1.7%) | +1.67 ± 0.31 | 0.5 |
| CRN rollout, 32 scenarios/candidate | 107.31 | -1.50 ± 0.39 (-1.4%) | +2.04 ± 0.30 | 1.1 |
| MCTS 200 it (c=0.5, prune 25s) | 105.17 | -3.63 ± 0.52 (-3.3%) | -0.09 ± 0.48 | 0.8 |
| MCTS 800 it (c=0.5, prune 25s) | 106.89 | -1.91 ± 0.42 (-1.8%) | +1.64 ± 0.31 | 3.0 |
| MCTS 3200 it (c=0.5, prune 25s) | 107.73 | -1.07 ± 0.34 (-1.0%) | +2.47 ± 0.32 | 12.9 |

## What the optimal policy does (DP, averaged over 500 matches)

`{'endgame_start_s': 124.1, 'coral_per_level': [0.0, 0.0, 1.0, 11.89], 'algae_removed': 6.0, 'net': 0.05, 'processed': 5.77}`

vs greedy-proc: `{'endgame_start_s': 120.4, 'coral_per_level': [0.0, 0.01, 0.35, 11.56], 'algae_removed': 6.0, 'net': 0.0, 'processed': 5.82}`

## DP-optimal trace, seed 0 (112 pts)

```
  0.00s INTAKE
  2.50s REM_HIGH
  5.25s L4
  7.25s INTAKE
 10.00s PROC
 13.75s L4
 17.00s REM_LOW
 18.25s INTAKE
 21.00s PROC
 24.50s L4
 27.25s REM_LOW
 29.00s INTAKE
 32.00s PROC
 36.00s L4
 39.50s INTAKE
 42.75s REM_HIGH
 46.00s L4
 48.50s INTAKE
 52.00s L4
 56.25s INTAKE
 59.25s PROC
 64.00s L4
 67.75s INTAKE
 71.00s L4
 74.50s INTAKE
 77.50s L4
 80.75s REM_LOW
 82.00s INTAKE
 84.75s PROC
 88.25s L4
 91.25s INTAKE
 94.75s L4
 98.75s INTAKE
102.00s REM_HIGH
104.75s L4
106.50s INTAKE
109.75s REM_HIGH
113.00s L3
114.50s INTAKE
118.00s PROC
122.25s L4
125.25s CLIMB
```
