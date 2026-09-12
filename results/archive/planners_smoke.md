# Planner comparison — `elite`, TELEOP only, V* = 108.63, 40 CRN matches

| planner | mean | paired gap vs DP | vs its base | s/match |
|---|---|---|---|---|
| greedy-proc | 104.65 | -4.08 ± 0.70 | — | — |
| rollout(greedy-proc, 8 scen) | 106.00 | -2.73 ± 1.21 | +1.35 ± 1.31 | 0.2 |
| rollout(greedy-proc, 16 scen) | 106.92 | -1.80 ± 1.13 | +2.27 ± 1.07 | 0.5 |
