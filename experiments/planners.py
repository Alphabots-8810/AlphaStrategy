"""Single-robot planner comparison against the exact DP (CRN, paired gaps).

    .venv/bin/python experiments/planners.py --scen 8,16,32 --matches 200
"""
from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor

from frcsim.reefscape2025 import dp
from frcsim.reefscape2025 import profiles as P
from frcsim.reefscape2025.policies import Greedy, RolloutPolicy
from frcsim.reefscape2025.sim import GameConfig, Match, play
from frcsim.stats import mean_ci, paired

CFG = GameConfig(auto=False, floor_algae=False)


def _one(args):
    name, base, n_scen, seed = args
    pol = RolloutPolicy("teleop", Greedy(base), n_scen=n_scen, seed=seed * 31337 + n_scen)
    return play(Match(CFG, [P.PROFILES[name]], seed=seed), pol).value("teleop")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="elite")
    ap.add_argument("--scen", default="8,16,32")
    ap.add_argument("--bases", default="proc,net")
    ap.add_argument("--matches", type=int, default=200)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--out", default="results/planners.md")
    args = ap.parse_args()
    prof = P.PROFILES[args.profile]
    res = dp.solve(prof, CFG)
    v_star = res.value(CFG.start_loc)
    seeds = list(range(args.matches))
    dpv = [play(Match(CFG, [prof], seed=s), dp.DPPolicy(res)).value("teleop") for s in seeds]
    lines = [f"# Planner comparison — `{prof.name}`, TELEOP only, V* = {v_star:.2f}, {len(seeds)} CRN matches\n",
             "| planner | mean | paired gap vs DP | vs its base | s/match |", "|---|---|---|---|---|"]
    print("\n".join(lines))
    with ProcessPoolExecutor(args.workers) as ex:
        for b in args.bases.split(","):
            gv = [play(Match(CFG, [prof], seed=s), Greedy(b)).value("teleop") for s in seeds]
            g, gh = paired(gv, dpv)
            row = f"| greedy-{b} | {mean_ci(gv)[0]:.2f} | {g:+.2f} ± {gh:.2f} | — | — |"
            print(row)
            lines.append(row)
            for n in (int(x) for x in args.scen.split(",")):
                t0 = time.perf_counter()
                v = list(ex.map(_one, [(prof.name, b, n, s) for s in seeds]))
                g, gh = paired(v, dpv)
                d, dh = paired(v, gv)
                row = (f"| rollout(greedy-{b}, {n} scen) | {mean_ci(v)[0]:.2f} | {g:+.2f} ± {gh:.2f} | "
                       f"{d:+.2f} ± {dh:.2f} | {(time.perf_counter() - t0) * args.workers / len(seeds):.1f} |")
                print(row, flush=True)
                lines.append(row)
    os.makedirs("results", exist_ok=True)
    with open(args.out, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
