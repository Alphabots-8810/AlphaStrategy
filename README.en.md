# AlphaStrategy — FRC match strategy simulator (REEFSCAPE 2025 prototype)

[中文](README.md) | English

_Last updated: 2026-09-12_ · By FRC 8810 Alphabots, part of the Alpha* line ([AlphaSim](https://github.com/Alphabots-8810/AlphaSim), [AlphaScout](https://github.com/Alphabots-8810/AlphaScout), [AlphaHarness](https://github.com/Alphabots-8810/AlphaHarness)).

An event-driven FRC match simulator plus three solvers:
- **Exact single-robot DP**: the theoretical optimum of expected TELEOP points under the simulator's own stochastic model — the ground truth;
- **CRN rollout planner**: handles what the DP can't — three-robot alliance coupling, RP thresholds, win probability. It is the practical choice: 1.4% from the DP optimum at 32 scenarios, about 1 CPU·s per match;
- **Closed-loop MCTS**: also works on a single robot and is also validated against the DP, but needs pruning. For equal accuracy it costs about 6× the compute of rollout; at about 12× it gets about 0.4 points closer to the optimum than rollout. At alliance level, MCTS with the RP objective is currently well behind the heuristics, cause not yet found (see "Known, not fixed").

> ⚠️ v0 prototype. Robot profiles (cycle times, success rates, drive times) are **uncalibrated, hand-set values**, so absolute scores mean nothing — **read the differences and sensitivities**. Calibrate with scouting data before using it for decisions.

## Main findings (assuming the model holds; profiles are placeholders)

**1. Among the policies tested, the highest E[RP] all come from win-first play; the policy that deliberately fills every level to the threshold is the lowest.**

Regular-season qualifications, alliance elite + mid + l1bot, opponent with the same profiles and 50% willing to cooperate on Coopertition, 400 matches on fresh seeds. The last column is the paired difference vs greedy-net:

| Policy | P(win) | P(coral RP) | E[RP] | ΔE[RP] vs greedy-net |
|---|---|---|---|---|
| CRN rollout, points objective | 0.71 | 0.51 | 4.38 | +1.365 ± 0.152 |
| **CRN rollout, RP objective, z=1 gate** | **0.70** | 0.50 | **4.32** | +1.302 ± 0.143 |
| greedy-proc (all algae to the processor) | 0.63 | 0.50 | 4.12 | +1.110 ± 0.140 |
| rp-seeker (deliberately fills every level to the threshold) | 0.37 | **1.00** | 3.84 | +0.823 ± 0.119 |

rp-seeker gets the Coral RP every match, but the matches it no longer wins cost it more RP overall. A win is worth 3 RP, far more than one bonus RP.

**How far this conclusion goes**:
- **The RP-objective rollout plays a lot like greedy-proc, but that is not independent evidence.** It sends 8.3 algae to the processor, places only 0.7 coral on L2, and P(coral RP) = P(coop) = 0.50. But it is itself a one-step lookahead on top of greedy-proc: ties keep greedy-proc's action, and the z=1 gate suppresses small deviations. So its resemblance to greedy-proc is partly structural.
- **The ungated version did drift toward the Coral RP**: P(coral RP) 0.70, 3.4 coral on L2 — and E[RP] fell to 3.91. This shows that drifting toward the Coral RP one step at a time doesn't pay; it does not show that no Coral-RP plan pays. A deeper search that can plan several consecutive placements was not tested.
- **It assumes 50% of opponents cooperate.** Sensitivity section D shows that for points-only policies the Coral RP is almost unreachable without coop, so the less cooperative the opponents, the more a deliberate Coral-RP push is worth relative to winning. Where the two cross has not been measured.

**Why most rows of the Championship table match the regular-season table**: same seeds, and these heuristics don't depend on the event type, so they play identically. The two new Championship thresholds barely bind:
- **Coral RP**: when coop is reached, L1, L3 and L4 are almost always all ≥ 7 — replaying greedy-proc, in 198 of 200 coop matches. So whether the threshold is 5 or 7, P(coral RP) ≈ P(coop). In the other 2 matches one level stopped at 6, which is exactly why greedy-proc's P(coral RP) drops from 0.50 to 0.49.
- **Barge RP**: the barge total can only take a few values. elite deep 12 (park 2 on failure), mid shallow 6 (park 2 on failure), l1bot can only park 2. The sum can only be 20, 16, 10 or 6. Replaying greedy-proc's 400 matches: 20 points in 272, 16 in 94, 10 in 32, 6 in 2 — none land at 14–15. So raising the threshold from 14 to 16 changes nothing; P(barge RP) is 0.91–0.92 for every row in both tables.

Only rp-seeker changes visibly: E[RP] 3.84 → 3.54, P(win) 0.37 → 0.27. Every other row's E[RP] moves by at most 0.04.

**2. Processor or net depends on the opponent HP's accuracy.**
- By margin: processing pays when the opponent HP's net accuracy is below about 68%. +6.25 points at 50%, −2.49 at 75%; 68% is a linear interpolation between these two points.
- By RP: because coop lowers the Coral RP threshold, processing is still +0.31 RP at 75% and −0.29 RP at 100%. It turns negative somewhere in between — about 88% by linear interpolation; nothing in between was measured.

**3. Design priorities.** Exact single-robot DP, elite's expected TELEOP points:

| Change | ΔV* |
|---|---|
| Drive time 10% shorter (action times unchanged) | +5.6 |
| L4 success 0.94→0.99 | +2.7 |
| Intake 0.2 s faster | +2.2 |
| L4 placement 0.3 s faster | +2.1 |
| Deep climb 1.5 s faster | +1.2 |
| Deep climb success 0.90→0.97 | +0.65 |
| Shallow cage instead of deep | −3.9 |
| No algae handling at all | −21.5 |

**4. Which weakness in the alliance is worth fixing.** rp-seeker policy, 3000 CRN matches:
- l1bot adds L2: +0.52 RP/match;
- mid goes from shallow to deep climb: +0.52;
- elite drive time 10% shorter: +0.41;
- l1bot adds a shallow climb: +0.17;
- mid adds L4: ≈ 0.

## Quick start

```bash
python3.11 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q                       # 127 tests, ~20 s
.venv/bin/python experiments/validate.py            # single robot: DP vs heuristics vs planners (fresh seeds)
.venv/bin/python experiments/tune_mcts.py --rollouts proc --c 0.5 --prune 0,25 --matches 120 --out results/tune_mcts_prune.md   # MCTS pruning comparison
.venv/bin/python experiments/tune_mcts.py --rollouts proc --c 0.02,0.05,0.1,0.2,0.5 --prune 0 --matches 120 --out results/tune_mcts_sweep.md   # unpruned MCTS, c sweep
.venv/bin/python experiments/alliance.py --seed-offset 200000   # alliance: heuristics vs rollout / MCTS
.venv/bin/python experiments/sensitivity.py --dp    # sensitivities (the deliverable)
.venv/bin/python experiments/tie_rule_ab.py         # effect of the rollout tie rule (lesson 5)
results/run_final.sh                                # rerun every experiment the README cites (no tests; ~1 hour, all cores)
```

## Model

**Rules** (`src/frcsim/reefscape2025/rules.py`) checked line by line against the 2025 Game Manual (Section 5 V4, Section 6 V13, Section 7 V11) and Team Update 21:

| Item | Value |
|---|---|
| Timing | AUTO 15 s, TELEOP 135 s |
| Coral points (AUTO / TELEOP) | L1 3/2, L2 4/3, L3 6/4, L4 7/5 |
| Algae | Processor 6, Net 4 |
| Barge | Park 2, Shallow 6, Deep 12 |
| Branches | 12 per level on L2–L4; L1 (trough) unlimited |
| Possession limit | 1 coral + 1 algae (G409) |
| Coral RP | ≥ 5 per level in regular season / DCMP; ≥ 7 at Championship (TU21); 3 levels once Coopertition is reached |
| Barge RP | 14 points in regular season; 16 at Championship |
| Coopertition | Qualifications only; each alliance processes ≥ 2 |

Algae we process rolls into the opponent's Processor Area, where their HP can throw it into **their own** net for 4 points. The model keeps this coupling.

**Decision structure**: an asynchronous semi-MDP. When a robot finishes its current macro action it becomes the actor and picks the next one from `INTAKE / L1–L4 / REM_LOW / REM_HIGH / NET / PROC / FLOOR / CLIMB / PARK`. Time runs on a dt = 0.25 s grid. Each action's duration = travel + service, modelled as one lognormal and discretised into k equal-probability atoms. The simulator and the DP read **the same duration table**.

**Alliance coupling** (the reasons "add up each robot's points per second" is wrong):
- 2 coral stations, each a queue serving one robot at a time;
- the processor serves one robot at a time;
- reef congestion: the more robots at the reef, the longer the service time;
- branch capacity and staged-algae state are shared by all three robots;
- the floor algae pool is shared.

**Opponent**: v0 has no defense. The opponent is a pre-sampled exogenous outcome (total points, algae processed). It couples to us through only two channels: processor → HP net throws, and Coopertition. 50% of opponents cooperate, so deciding whether to process means inferring whether coop will actually happen this match.

**AUTO** outcomes are sampled from the profile, not optimised. AUTO is a pre-written routine, not a decision problem.

## Solvers

| Module | What it does |
|---|---|
| `dp.py` | Single robot, expected TELEOP points. State = (location, holding coral, holding algae, #L2, #L3, #L4, low/high algae left), 562,432 states; backward induction over 540 time steps, about 50 s vectorised. L1 count, processor count and coop don't affect optimal decisions under this objective, so they are dropped from the state. RP thresholds and win objectives blow up the state; those go to the planners (CRN rollout / MCTS). |
| `mcts.py` | Closed-loop UCT with chance nodes: children are keyed by the exact post-transition state. Expands the heuristic's action first; optional progressive bias and `action_filter` pruning. Only the robot that just became free decides at any moment, so branching is \|A\|, not \|A\|³. |
| `policies.py` | `Greedy`: points-per-second greedy with an endgame time reserve; algae modes net/proc/coop.<br>`rp_seeker`: an RP-chasing variant.<br>**`RolloutPolicy`**: CRN one-step lookahead (Bertsekas rollout) — each candidate action is followed by the base heuristic under the same batch of random scenarios, and the best mean wins.<br>`MCTSPolicy`: re-plans at every decision point in the match; `NoEarlyTerminal` does the pruning. |

Five objectives:
- `teleop`: same as the DP;
- `points`: our score;
- `margin`: ours minus theirs, including the points our processing hands to the opponent HP — the continuous quantity win probability actually depends on monotonically;
- `win`: win probability;
- `rp`: expected RP, 0 in playoffs.

`win` and `rp` are discrete and need the z gate when planning (see lesson 3).

**No planner can peek**: scenario seeds come from the planner's own RNG. When the match has an opponent, opponents are sampled only from the planner's own bank; with an opponent but no bank, planning raises immediately (`_no_peek`). Single-robot experiments have no opponent and need no bank.

**Randomness and CRN**: in the world simulation every uniform random number is a hash of (seed, robot, action, n-th use), so different policies on the same seed get the same luck on the same kind of task (common random numbers), and differences can be compared with paired CIs.

Planning clones can't see the world's future either, but the two planners do it differently:
- **CRN rollout**: scenario clones use the same hash, with the seed replaced by a scenario seed drawn from the planner's own RNG. So within a scenario the candidate actions draw paired numbers — which is also where the exact ties of lesson 5 come from.
- **MCTS**: clones draw directly from the planner's own `random.Random`.

Neither can read the world's seed.

## Validation

Configuration for V2–V4: single elite robot, TELEOP, dt 0.25 s, k 5, algae blocking B, regular season. V1 uses small instances; full size can't be brute-forced.

| Check | Result |
|---|---|
| V1: DP = brute-force expectimax (enumerated with the simulator's own transition function, `tests/test_dp.py`) | All agree within 1e-9:<br>• dt 0.5 s, k 3, 7 s horizon: 11 start states over 4 profiles × blocking readings A/B, 22 cases;<br>• dt 1.0 s, k 2, 16 s horizon with ring-buffer wraparound, 4 cases;<br>• a 9 s endgame window, 1 case. |
| V2: DP-optimal policy replayed in the simulator (4000 matches) | 108.65 ± 0.19, V* = 108.635 ✅ |
| V3: every heuristic ≤ V* | greedy-proc −3.37, greedy-coop −11.5, greedy-net −18.0, rp-seeker −22.2 ✅ |

**V4: how far the planners are from optimal.** Run on fresh seeds (100000–100199), disjoint from the tuning seeds. The base heuristic is greedy-proc, paired gap to the DP −3.54.

| Planner | Paired gap vs DP | vs base | CPU·s/match |
|---|---|---|---|
| CRN rollout, 8 scenarios | −3.00 ± 0.47 (−2.8%) | +0.54 | 0.2 |
| CRN rollout, 16 scenarios | −1.88 ± 0.40 (−1.7%) | +1.67 | 0.5 |
| **CRN rollout, 32 scenarios** | **−1.50 ± 0.39 (−1.4%)** | **+2.04** | **1.1** |
| MCTS 200 iterations (pruned) | −3.63 ± 0.52 (−3.3%) | −0.09 | 0.8 |
| MCTS 800 iterations (pruned) | −1.91 ± 0.42 (−1.8%) | +1.64 | 3.0 |
| MCTS 3200 iterations (pruned) | −1.07 ± 0.34 (−1.0%) | +2.47 | 12.9 |

How to read it:
- **Compute at equal accuracy**: rollout with 16 scenarios (−1.88, 0.5 CPU·s) vs MCTS with 800 iterations (−1.91, 3.0 CPU·s) — MCTS costs about 6×;
- **MCTS can get closer**: 3200 iterations reach −1.07, about 0.4 points closer than rollout with 32 scenarios (−1.50), at about 12× the compute;
- the rollout rows are sensitive to which action is taken on ties — a different tie rule shifts them by about 0.5 points; see lesson 5.

**Five lessons about the planners** (all backed by experiments):

1. **Vanilla UCT loses to its own rollout policy on this problem** — 4.5–11 points below greedy-proc when that is the rollout — and more iterations are not necessarily better. UCT expands every action once at every node, including one-step match-killers like going to PARK/CLIMB at second 10. Those samples are mean-backed-up into every ancestor edge, biased toward different actions, and scramble the action ranking. Adding "ignore endgame actions while more than 25 s remain" removes the loss, and more iterations then help. See `results/tune_mcts_sweep.md` (unpruned, c sweep) and `results/tune_mcts_prune.md` (pruning comparison).
2. **Per-match luck is far larger than the gap between good actions (1–3 points).** Back-computed from the 95% CIs of the validate and alliance tables, the per-match standard deviation is about 6 points for single-robot TELEOP and about 10 for alliance totals. CRN rollout compares every candidate on the same random scenarios, cancelling most of that variance, so it reaches the same accuracy with about 1/6 of MCTS's compute. This generalises to FRC-type problems: for the same compute, paired Monte Carlo comparison beats tree search.
3. **Discrete objectives hit the optimizer's curse.** In the alliance experiments, rollout-win's P(win):

   | Scenarios | 16 | 32 | 64 | 16 with z=1 gate |
   |---|---|---|---|---|
   | P(win) | 0.54 | 0.55 | 0.61 | **0.71** |

   For comparison, its base greedy-proc is 0.63.

   Why: flipping one scenario from loss to win outweighs a 20-point score difference, so the planner leaves the base action because of one scenario's luck. The gate rule: leave the base action only if the paired improvement exceeds 1 standard error. At 16 scenarios it removes the problem with no extra compute. z=1 was fixed in advance, not swept.
4. **Discrete objectives like win and rp need a tie-break.** At most decision points the match is already won or lost in every sampled scenario, so every candidate ties. Without a tie-break the planner takes the first action in legal-list order — L1 before L4, INTAKE before CLIMB. The fix has two parts: keep the base heuristic's action on ties, and add 1e-4 per expected point as a secondary key (`policies.Objective`).

   **Ablation**: current code with only those two parts reverted, nothing else changed. 400 matches from seed 500000, 16 scenarios, results in `results/tie_rule_ab.md`.

   | rollout-win | P(win) | E[RP] |
   |---|---|---|
   | Fixed | 0.52 | 3.88 |
   | Reverted | 0.22 | 2.37 |

   For comparison, its base greedy-proc has P(win) 0.63. Even fixed, rollout-win stays below its base — that is lesson 3's optimizer's curse, which the z gate addresses.
5. **Continuous objectives also tie exactly, often, and the tie rule is worth about 0.5 points** (`experiments/tie_rule_ab.py`, results in `results/tie_rule_ab.md`).

   **Why exact ties happen**: world random numbers are keyed by (seed, robot, action, n-th use). Two candidates that are the same set of actions in a different order — INTAKE then REM_LOW, or the reverse — draw the same luck. By the buzzer they have completed the same set of actions, so they score exactly the same in every scenario.

   **Measured** (rollout, 32 scenarios, 30 matches):
   - of 1214 decisions, 241 (19.9%) tie exactly at the maximum, 232 of them with more than 25 s left;
   - on 115 of them the two rules pick different actions — 47.7% of tied decisions, 9.5% of all decisions. The pre-fix rule takes the first in legal order, mostly INTAKE; the current rule keeps the base action, mostly REM_LOW, REM_HIGH or PROC.

   **A/B** (fresh seeds, paired; positive means the pre-fix rule is better):

   | Setting | Objective | Pre-fix − current |
   |---|---|---|
   | Single robot, seeds 400000–400199, 16 scenarios | TELEOP points | +0.34 ± 0.46 |
   | Single robot, seeds 400000–400199, 32 scenarios | TELEOP points | +0.56 ± 0.37 |
   | Alliance, 400 matches from seed 500000, 16 scenarios | points objective | points +0.56 ± 0.37, P(win) +0.021 ± 0.023, E[RP] +0.005 ± 0.081 |
   | Same | margin objective | margin +0.74 ± 0.44, E[RP] +0.013 ± 0.082 |

   Only the two continuous objectives, points and margin, were measured. Adding these differences to those two rows of the alliance table changes neither row's rank in E[RP] or P(win). The win / rp rows use the same tie rule and were not rerun.

   **The current rule stays**, for two reasons:
   - the pre-fix rule's advantage comes only from INTAKE happening to be first in the action list — there is no reason behind it;
   - the current rule has a stated property (on ties it can't do worse than base), and every alliance-table number was produced with it.

   Switching rules because the numbers look better and then rerunning would be another round of the winner's curse.

   **Takeaways**:
   - one-step lookahead is structurally blind to the value of action order;
   - the tie frequency comes partly from how CRN draws its numbers, not purely from the game.

   So rollout's 1.3–1.5 point gap to the DP is the same order of magnitude as the effect of an arbitrary tie-break (0.3–0.6 points). Improvements are listed under "Next steps".

What the DP-optimal policy does (500-match average):
- nearly fills L4's 12 branches (11.89 on average), plus about 1 L3 per match;
- removes all 6 algae and processes almost all of them ("knock algae off → carry it to the station for coral → process on the way → back to the reef for L4");
- leaves to climb at 124 s.

This behaviour rests on two assumptions: `elite.hold_both=True` (it can hold 1 coral + 1 algae at once), and the own-points objective not seeing the points processing hands to the opponent HP.

## Independent audit (two multi-agent rounds, with adversarial re-checks)

Items and numbers marked † come from one-off audit scripts; neither the scripts nor their outputs are in the repo.

**Confirmed correct**:
- Rule constants checked line by line against the manual and TUs — all correct.
- † **DP and the single-robot simulator are equivalent at full size**: forward probability-mass propagation computes the DP policy's exact value in the simulator, over 1,818,682 merged states. It differs from V* by 1.4e-10 — floating-point accumulation.
- † **246 further small cases against brute-force expectimax**: many profile variants plus 24 random profiles, with REEF, STATION and random start states. With queue state that can't bind, the maximum deviation is 3.6e-15.
- Planners can't peek: neither the world seed nor the true opponent is readable while planning.
- † **Fuzzing over 2000 random configurations** (random alliance composition, event type, policies, etc.): all invariants hold.

**Fixed**:
- the 3 algae pre-placed on the coral marks were not modelled;
- playoffs still awarded RP;
- PARK scoring was inconsistent with CLIMB;
- endgame actions polluted MCTS's mean backups;
- discrete objectives took the list-order action on ties;
- reef congestion also counted partners who had already left the reef, inflating the congestion effect about 2.6× †;
- a lone robot could hit a "phantom queue";
- after congestion seconds were rounded, the "×2" row was really 2.2× †;
- RolloutPolicy couldn't be pickled;
- tuning and reporting used the same seeds.

**Known, not fixed**:
- HP net throws aren't time-gated: algae processed in the last few seconds still count as throwable by the opponent HP. Measured to have no effect †: over 400 matches for each of three heuristics and 100 for rollout-rp (z=1), zero processor scores completed in the last 5 s; the closest was 16 s from the end.
- At alliance level, MCTS-rp (300 iterations, pruned) is still well behind its heuristic: P(win) 0.23 vs 0.63, E[RP] 3.27 vs 4.12. The cause isn't located — possibly small-budget noise, mean pollution at internal nodes, or c calibrated on the single robot not transferring to the rp objective. Until it is, use CRN rollout at alliance level.

## Assumptions to confirm

1. **Algae blocking**: the manual doesn't say exactly which branches staged algae block. The default is reading B (low algae blocks L2+L3 on its face, high algae blocks L3; 0 L3 available at the start). Reading A: each algae blocks only the pair it rests on (6 left on each of L2/L3). Teams that played 2025 will know which is right — issues welcome.
2. **Profile values**: the travel matrix, action durations, success rates and HP net accuracy (default 50%) are all placeholders. The "about 68%" break-even in finding 2 depends directly on them.
3. **elite can hold 1 coral + 1 algae at once** (`hold_both=True`). The DP-optimal "carry algae to the station" trick depends on it.
4. No defense, fouls or mechanism failures, and dropped coral can't be picked up again. The 3 coral-mark algae are assumed still on the floor at the start of TELEOP (AUTO's effect on them isn't modelled), and their pickup point is approximated as near the reef.

## Next steps

1. **Calibrate with [AlphaScout](https://github.com/Alphabots-8810/AlphaScout)**: TBA's score breakdowns are per alliance, so per-team cycle distributions only come from scouting. With each team's empirical distribution in its profile, the simulator can do pre-match planning (how three teams split the work) and pick lists.
2. **2026 REBUILT**: reuse the engine and rewrite only the game module. Model dumper and turret as two robot profiles (shot time, accuracy vs distance, shooting on the move) and compare them with CRN rollout and sensitivity analysis.
3. **Opponents and defense**: turn the opponent from an exogenous sample into policy archetypes, compute the pairwise win-probability matrix, and solve for the mixed equilibrium with an LP.
4. **The planner's tie rule** (lesson 5): let the planner tell apart "the same actions in a different order". Two candidates: a time-integrated "scoring earlier is better" secondary key, or a two-step lookahead on tied candidates. Each must be validated against the DP before it replaces the current rule.

## Layout

```
src/frcsim/mcts.py                 game-agnostic MCTS (split out along a file boundary only; no generic game interface)
src/frcsim/reefscape2025/          rules / profiles / simulator / DP / policies
experiments/                       validate, planners, tune_mcts, alliance, sensitivity, tie_rule_ab
tests/                             DP vs expectimax (incl. ring-buffer wraparound), simulator invariants, RP logic, planners, MCTS convergence
results/                           experiment outputs: validate_elite.md, alliance_{regular,champs}_B.md, sensitivity.md, tune_mcts_{prune,sweep}.md, tie_rule_ab.md
```

## License

MIT — see [LICENSE](LICENSE).
