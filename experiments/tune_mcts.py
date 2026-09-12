"""Tune MCTS on the full-size single-robot model with the exact DP as ground truth.

Every config plays the same world seeds as the DP-optimal policy (CRN), so the
paired gap to DP is measured with far less noise than the raw means.

    .venv/bin/python experiments/tune_mcts.py --c 0.02,0.05,0.1,0.2,0.5 --iters 200,800 \
        --rollouts net,proc --prior 0,0.3 --matches 160
"""
from __future__ import annotations

import argparse
import itertools
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

from frcsim.reefscape2025 import dp
from frcsim.reefscape2025 import profiles as P
from frcsim.reefscape2025.policies import Greedy, MCTSPolicy, NoEarlyTerminal
from frcsim.reefscape2025.sim import GameConfig, Match, play
from frcsim.stats import mean_ci, paired

CFG = GameConfig(auto=False, floor_algae=False)


def _one(args):
    name, n_iter, c, rollout, prior, seed, prune = args
    pol = MCTSPolicy("teleop", n_iter=n_iter, c=c, rollout=Greedy(rollout),
                     prior_weight=prior, seed=seed * 7919 + n_iter,
                     action_filter=NoEarlyTerminal(prune) if prune > 0 else None)
    return play(Match(CFG, [P.PROFILES[name]], seed=seed), pol).value("teleop")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="elite")
    ap.add_argument("--c", default="0.02,0.05,0.1,0.2,0.5")
    ap.add_argument("--iters", default="200,800")
    ap.add_argument("--rollouts", default="net,proc")
    ap.add_argument("--prior", default="0")
    ap.add_argument("--prune", default="0", help="NoEarlyTerminal seconds (0 = off), comma list")
    ap.add_argument("--matches", type=int, default=160)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--out", default="results/tune_mcts.md")
    args = ap.parse_args()
    prof = P.PROFILES[args.profile]
    res = dp.solve(prof, CFG)
    v_star = res.value(CFG.start_loc)
    seeds = list(range(args.matches))
    dpv = [play(Match(CFG, [prof], seed=s), dp.DPPolicy(res)).value("teleop") for s in seeds]
    greedy = {r: [play(Match(CFG, [prof], seed=s), Greedy(r)).value("teleop") for s in seeds]
              for r in args.rollouts.split(",")}
    lines = [f"# MCTS tuning — `{prof.name}`, TELEOP only, V* = {v_star:.2f}, {len(seeds)} CRN matches\n",
             "Rollout baselines (the heuristic alone): " + ", ".join(
                 f"greedy-{r} {mean_ci(v)[0]:.2f} (gap {paired(v, dpv)[0]:+.2f})" for r, v in greedy.items()),
             "", "| rollout | prior | prune s | c | iters | mean | paired gap vs DP | vs its rollout | s |",
             "|---|---|---|---|---|---|---|---|---|"]
    print("\n".join(lines))
    grid = list(itertools.product(args.rollouts.split(","), [float(x) for x in args.prior.split(",")],
                                  [float(x) for x in args.prune.split(",")],
                                  [float(x) for x in args.c.split(",")],
                                  [int(x) for x in args.iters.split(",")]))
    with ProcessPoolExecutor(args.workers) as ex:
        for rollout, prior, prune, c, n in grid:
            t0 = time.perf_counter()
            v = list(ex.map(_one, [(prof.name, n, c, rollout, prior, s, prune) for s in seeds]))
            g, gh = paired(v, dpv)
            r, rh = paired(v, greedy[rollout])
            row = (f"| greedy-{rollout} | {prior:g} | {prune:g} | {c:g} | {n} | {mean_ci(v)[0]:.2f} | "
                   f"{g:+.2f} ± {gh:.2f} | {r:+.2f} ± {rh:.2f} | {time.perf_counter() - t0:.0f} |")
            print(row)
            sys.stdout.flush()
            lines.append(row)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
