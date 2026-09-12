# MCTS tuning — `elite`, TELEOP only, V* = 108.63, 120 CRN matches

Rollout baselines (the heuristic alone): greedy-proc 105.13 (gap -3.81)

| rollout | prior | prune s | c | iters | mean | paired gap vs DP | vs its rollout | s |
|---|---|---|---|---|---|---|---|---|
| greedy-proc | 0 | 0 | 0.5 | 200 | 100.62 | -8.32 ± 0.86 | -4.52 ± 0.79 | 9 |
| greedy-proc | 0 | 0 | 0.5 | 800 | 98.89 | -10.05 ± 1.00 | -6.24 ± 0.94 | 35 |
| greedy-proc | 0 | 25 | 0.5 | 200 | 105.70 | -3.24 ± 0.71 | +0.57 ± 0.61 | 10 |
| greedy-proc | 0 | 25 | 0.5 | 800 | 106.41 | -2.53 ± 0.50 | +1.27 ± 0.49 | 42 |
