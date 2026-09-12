# Sensitivity analysis (UNCALIBRATED profiles — read the deltas, not the levels)

## A. Exact single-robot DP sensitivities (elite, TELEOP only)

Baseline V* = 108.63 expected TELEOP points (solve 57s).

| change | V* | ΔV* |
|---|---|---|
| L4 place time 1.5→1.2 s | 110.73 | +2.10 |
| intake time 0.8→0.6 s | 110.82 | +2.19 |
| drive 10% faster | 114.25 | +5.62 |
| L4 success 0.94→0.99 | 111.30 | +2.66 |
| deep climb 6.0→4.5 s | 109.80 | +1.17 |
| deep climb success 0.90→0.97 | 109.29 | +0.65 |
| shallow instead of deep (same time/p) | 104.73 | -3.91 |
| no ALGAE handling at all | 87.17 | -21.46 |
| ALGAE blocking reading A | 108.63 | +0.00 |

## B. Alliance sensitivities (rp-seeker policy, 3000 CRN matches, opponent 50% coop-minded)

Baseline: E[RP] 3.785, P(win) 0.356, E[points] 183.0

| change | ΔE[RP] | ΔP(win) | ΔE[points] | ΔP(coral RP) | ΔP(barge RP) |
|---|---|---|---|---|---|
| elite: L4 place 1.5→1.2 s | +0.141 ± 0.024 | +0.046 ± 0.008 | +1.7 ± 0.1 | +0.000 ± 0.000 | +0.000 ± 0.000 |
| elite: drive 10% faster | +0.413 ± 0.036 | +0.137 ± 0.012 | +4.7 ± 0.1 | +0.000 ± 0.000 | +0.000 ± 0.000 |
| mid: add L4 (2.8 s, p .8) | +0.000 ± 0.033 | -0.001 ± 0.011 | +0.1 ± 0.2 | +0.000 ± 0.000 | +0.000 ± 0.000 |
| mid: shallow→deep climb | +0.520 ± 0.037 | +0.143 ± 0.012 | +4.8 ± 0.1 | +0.000 ± 0.000 | +0.087 ± 0.010 |
| l1bot: add shallow climb (8 s, p .75) | +0.174 ± 0.026 | +0.034 ± 0.008 | +1.3 ± 0.1 | +0.000 ± 0.000 | +0.066 ± 0.009 |
| l1bot: add L2 (2.2 s, p .85) | +0.517 ± 0.042 | +0.171 ± 0.014 | +5.7 ± 0.2 | +0.000 ± 0.000 | +0.000 ± 0.000 |
| our HP net 50%→80% | +0.085 ± 0.017 | +0.028 ± 0.006 | +1.1 ± 0.1 | +0.000 ± 0.000 | +0.000 ± 0.000 |
| REEF congestion ×2 | -0.024 ± 0.031 | -0.009 ± 0.010 | -4.7 ± 0.1 | +0.000 ± 0.000 | +0.000 ± 0.000 |
| ALGAE blocking reading A | -0.071 ± 0.036 | -0.024 ± 0.012 | +0.7 ± 0.1 | +0.000 ± 0.000 | +0.000 ± 0.000 |

## C. PROCESSOR vs NET: greedy-proc minus greedy-net, by opponent HP accuracy

Processing scores 6 for us but feeds the opponent HUMAN PLAYER a 4-pt NET throw.

| opp HP net % | Δmargin (ours−theirs) | ΔP(win) | ΔE[RP] |
|---|---|---|---|
| 0 | +23.92 ± 0.23 | +0.516 ± 0.017 | +2.061 ± 0.057 |
| 25 | +15.09 ± 0.29 | +0.390 ± 0.017 | +1.676 ± 0.056 |
| 50 | +6.25 ± 0.30 | +0.181 ± 0.016 | +1.046 ± 0.052 |
| 75 | -2.49 ± 0.28 | -0.063 ± 0.015 | +0.314 ± 0.048 |
| 100 | -11.08 ± 0.21 | -0.266 ± 0.016 | -0.291 ± 0.051 |

## D. Coopertition: greedy-coop minus greedy-net, by opponent coop intent

| opponent coop-minded | P(coop) coop-policy | ΔE[RP] | ΔP(coral RP) | ΔP(win) |
|---|---|---|---|---|
| 0% (regular) | 0.00 | +0.387 ± 0.039 | +0.011 ± 0.004 | +0.125 ± 0.013 |
| 0% (champs) | 0.00 | +0.376 ± 0.039 | +0.000 ± 0.000 | +0.125 ± 0.013 |
| 50% (regular) | 0.50 | +0.889 ± 0.042 | +0.508 ± 0.018 | +0.126 ± 0.013 |
| 50% (champs) | 0.50 | +0.879 ± 0.042 | +0.498 ± 0.018 | +0.126 ± 0.013 |
| 100% (regular) | 1.00 | +1.355 ± 0.037 | +1.000 ± 0.000 | +0.118 ± 0.012 |
| 100% (champs) | 1.00 | +1.350 ± 0.037 | +0.995 ± 0.003 | +0.118 ± 0.012 |

