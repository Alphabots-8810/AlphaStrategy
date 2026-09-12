# Rollout tie rule

## Probe (elite, TELEOP, 32 scenarios, seeds 100000..100029)

- decisions with ≥ 2 legal actions: 1214
- exact ties at the maximum: 241 (19.9%), {'> 25 s left': 232, '≤ 25 s left': 9}
- pre-fix rule picks differently: 115 (9.5% of decisions, 47.7% of tied decisions)
- (pre-fix → current) picks: {'INTAKE→REM_LOW': 49, 'INTAKE→REM_HIGH': 28, 'INTAKE→PROC': 14, 'INTAKE→CLIMB': 8, 'L3→L4': 8, 'L4→PROC': 8}

## A/B, single robot (elite, TELEOP, fresh seeds 400000..400199, paired, same planner seed per match)

| scenarios | gap vs DP, ties keep base (current) | gap vs DP, legal order (pre-fix) | pre-fix − current |
|---|---|---|---|
| 16 | -1.71 ± 0.48 | -1.36 ± 0.42 | +0.34 ± 0.46 |
| 32 | -1.27 ± 0.44 | -0.71 ± 0.42 | +0.56 ± 0.37 |

## A/B, alliance ('elite', 'mid', 'l1bot') (regular season, seeds 500000..500399, 16 scenarios, opponents / planner bank / reseed as experiments/alliance.py)

| objective | metric | ties keep base (current) | legal order (pre-fix) | pre-fix − current |
|---|---|---|---|---|
| points | points | 208.028 | 208.588 | +0.560 ± 0.371 |
| points | margin | 7.258 | 7.878 | +0.620 ± 0.383 |
| points | win | 0.705 | 0.726 | +0.021 ± 0.023 |
| points | rp | 4.335 | 4.340 | +0.005 ± 0.081 |
| margin | points | 205.653 | 205.433 | -0.220 ± 0.520 |
| margin | margin | 6.593 | 7.332 | +0.740 ± 0.443 |
| margin | win | 0.693 | 0.716 | +0.024 ± 0.024 |
| margin | rp | 4.305 | 4.317 | +0.013 ± 0.082 |

## Discrete objective `win`, same alliance seeds: what the tie fix does

current = ties keep the base action + 1e-4/point tie-break (policies.Objective); pre-fix = first max in legal-action order, no tie-break.

| policy | P(win) | E[RP] | E[points] | ΔP(win) vs greedy-proc |
|---|---|---|---|---|
| greedy-proc | 0.632 | 4.117 | 205.1 | +0.000 ± 0.000 |
| rollout-win-16, current | 0.524 | 3.882 | 196.8 | -0.109 ± 0.037 |
| rollout-win-16, pre-fix | 0.215 | 2.370 | 168.0 | -0.417 ± 0.048 |
