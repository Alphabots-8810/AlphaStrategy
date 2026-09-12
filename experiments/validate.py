"""Validation spine on the FULL-size single-robot model (TELEOP only, 135 s).

  V2  DP-optimal policy replayed in the simulator  ~= V*   (DP solves the sim's model)
  V3  every heuristic                                <= V*   (DP is an upper bound)
  V4  planners (CRN rollout, MCTS) vs V* on FRESH seeds (not the seeds used for tuning)

(V1 - DP == brute-force expectimax - is in tests/test_dp.py.)

    .venv/bin/python experiments/validate.py [--profile elite] [--matches 4000]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

from frcsim.reefscape2025 import dp
from frcsim.reefscape2025 import profiles as P
from frcsim.reefscape2025.policies import (Greedy, MCTSPolicy, NoEarlyTerminal, RolloutPolicy,
                                           rp_seeker)
from frcsim.reefscape2025.sim import GameConfig, Match, play
from frcsim.stats import mean_ci, paired

CFG = GameConfig(auto=False, floor_algae=False)


def run(profile, policy, seeds):
    return [play(Match(CFG, [profile], seed=s), policy).value("teleop") for s in seeds]


def _planner_one(args):
    kind, name, budget, c, rollout, prune, seed = args
    if kind == "mcts":
        pol = MCTSPolicy("teleop", n_iter=budget, c=c, seed=seed * 7919 + budget,
                         rollout=Greedy(rollout),
                         action_filter=NoEarlyTerminal(prune) if prune > 0 else None)
    else:
        pol = RolloutPolicy("teleop", Greedy(rollout), n_scen=budget, seed=seed * 31337 + budget)
    return play(Match(CFG, [P.PROFILES[name]], seed=seed), pol).value("teleop")


def trace(profile, policy, seed):
    m = Match(CFG, [profile], seed=seed)
    out = []
    while (r := m.actor()) >= 0:
        a = policy(m, r)
        t = m.busy[r] * CFG.dt
        m.step(a)
        out.append(f"{t:6.2f}s {P.ACTION_NAMES[a]}")
    return out, m.value("teleop")


def behaviour(profile, policy, seeds):
    """Aggregate what the policy does: endgame start time, per-level coral, algae."""
    climb_t, lv, rem, net, proc = [], Counter(), [], [], []
    for s in seeds:
        m = Match(CFG, [profile], seed=s)
        while (r := m.actor()) >= 0:
            a = policy(m, r)
            if a in (P.CLIMB, P.PARK):
                climb_t.append(m.busy[r] * CFG.dt)
            m.step(a)
        for i in (1, 2, 3, 4):
            lv[i] += m.n[i] / len(seeds)
        rem.append(6 - m.low - m.high)
        net.append(m.net_scored)
        proc.append(m.processed)
    return {"endgame_start_s": round(mean_ci(climb_t)[0], 1),
            "coral_per_level": [round(lv[i], 2) for i in (1, 2, 3, 4)],
            "algae_removed": round(mean_ci(rem)[0], 2), "net": round(mean_ci(net)[0], 2),
            "processed": round(mean_ci(proc)[0], 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="elite")
    ap.add_argument("--matches", type=int, default=4000)
    ap.add_argument("--planner-matches", type=int, default=200)
    ap.add_argument("--eval-offset", type=int, default=100_000,
                    help="planner rows use seeds [offset, offset+n): disjoint from tuning seeds")
    ap.add_argument("--scen", default="8,16,32")
    ap.add_argument("--iters", default="200,800,3200")
    ap.add_argument("--c", type=float, default=0.5)
    ap.add_argument("--rollout", default="proc", choices=["net", "proc", "coop"])
    ap.add_argument("--prune", type=float, default=25.0, help="NoEarlyTerminal seconds for MCTS (0=off)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = ap.parse_args()
    prof = P.PROFILES[args.profile]
    lines = []

    def emit(s=""):
        print(s)
        lines.append(s)
        sys.stdout.flush()

    emit(f"# Validation — profile `{prof.name}`, TELEOP only, dt={CFG.dt}s, k={CFG.k}, "
         f"blocking={CFG.algae_blocking}, event={CFG.event}")
    res = dp.solve(prof, CFG)
    v_star = res.value(CFG.start_loc)
    emit(f"\nDP solved in {res.seconds:.1f}s over {dp.N_CONFIGS:,} configs x {CFG.n_steps} steps. "
         f"**V\\* = {v_star:.3f}** expected TELEOP points from the REEF, empty-handed.\n")

    seeds = range(args.matches)
    dpv = run(prof, dp.DPPolicy(res), seeds)
    mu, hw = mean_ci(dpv)
    emit(f"## Heuristics ({args.matches} CRN matches)\n")
    emit("| policy | mean TELEOP pts (95% CI) | paired diff vs DP-optimal | check |")
    emit("|---|---|---|---|")
    emit(f"| DP-optimal (replayed in sim) | {mu:.2f} ± {hw:.2f} | — | "
         f"V2 {'PASS' if abs(mu - v_star) <= hw else 'FAIL'} (|mean−V\\*|={abs(mu - v_star):.2f}) |")
    for pol in (Greedy("net"), Greedy("proc"), Greedy("coop"), rp_seeker()):
        v = run(prof, pol, seeds)
        m_, h_ = mean_ci(v)
        d, dh = paired(v, dpv)
        emit(f"| {pol.name} | {m_:.2f} ± {h_:.2f} | {d:+.2f} ± {dh:.2f} | "
             f"V3 {'PASS' if m_ <= v_star + h_ else 'FAIL'} |")

    pseeds = list(range(args.eval_offset, args.eval_offset + args.planner_matches))
    dp_sub = run(prof, dp.DPPolicy(res), pseeds)
    base = run(prof, Greedy(args.rollout), pseeds)
    emit(f"\n## Planners (fresh seeds {pseeds[0]}..{pseeds[-1]}, base heuristic greedy-{args.rollout}: "
         f"{mean_ci(base)[0]:.2f}, gap {paired(base, dp_sub)[0]:+.2f})\n")
    emit("| planner | mean | paired gap vs DP | vs base heuristic | CPU s/match |")
    emit("|---|---|---|---|---|")
    jobs = [("rollout", int(n)) for n in args.scen.split(",")] + \
           [("mcts", int(n)) for n in args.iters.split(",")]
    with ProcessPoolExecutor(args.workers) as ex:
        for kind, budget in jobs:
            t0 = time.perf_counter()
            v = list(ex.map(_planner_one, [(kind, prof.name, budget, args.c, args.rollout,
                                            args.prune, s) for s in pseeds]))
            g, gh = paired(v, dp_sub)
            b, bh = paired(v, base)
            label = (f"CRN rollout, {budget} scenarios/candidate" if kind == "rollout" else
                     f"MCTS {budget} it (c={args.c}, prune {args.prune:g}s)")
            emit(f"| {label} | {mean_ci(v)[0]:.2f} | {g:+.2f} ± {gh:.2f} ({100 * g / v_star:+.1f}%) | "
                 f"{b:+.2f} ± {bh:.2f} | {(time.perf_counter() - t0) * args.workers / len(pseeds):.1f} |")

    emit("\n## What the optimal policy does (DP, averaged over 500 matches)\n")
    emit(f"`{behaviour(prof, dp.DPPolicy(res), range(500))}`")
    emit(f"\nvs greedy-{args.rollout}: `{behaviour(prof, Greedy(args.rollout), range(500))}`")
    tr, val = trace(prof, dp.DPPolicy(res), seed=0)
    emit(f"\n## DP-optimal trace, seed 0 ({val:.0f} pts)\n")
    emit("```\n" + "\n".join(tr) + "\n```")
    os.makedirs("results", exist_ok=True)
    with open(f"results/validate_{prof.name}.md", "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
