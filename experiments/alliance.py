"""Alliance-level comparison: heuristics vs online MCTS under different objectives.

Our alliance and the opponent both field [elite, mid, l1bot] (uncalibrated
profiles). The opponent is an exogenous pre-sampled outcome: 50% of opponents
play "coop" (process 2 ALGAE), 50% play "net" - so our PROCESSOR decision has
to reason about whether Coopertition will actually happen. Every policy is run
on the same world seeds and the same opponent draws (common random numbers);
differences are reported as paired means vs greedy-net.

    .venv/bin/python experiments/alliance.py [--event regular|champs] [--matches 400] [--iters 300]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

from frcsim.reefscape2025 import profiles as P
from frcsim.reefscape2025.policies import (Greedy, MCTSPolicy, NoEarlyTerminal, RolloutPolicy,
                                           rp_seeker)
from frcsim.reefscape2025.sim import GameConfig, Match, OpponentBank, play
from frcsim.stats import mean_ci, paired

ALLIANCE = ("elite", "mid", "l1bot")


def build_bank(cfg, seed0, n):
    profs = [P.PROFILES[x] for x in ALLIANCE]
    coop = OpponentBank(cfg, profs, Greedy("coop"), n=n // 2, seed0=seed0)
    net = OpponentBank(cfg, profs, Greedy("net"), n=n - n // 2, seed0=seed0 + n)
    bank = coop
    bank.outcomes = [o for pair in zip(coop.outcomes, net.outcomes) for o in pair]
    return bank


def _one(args):
    cfg, policy, seed, opp = args
    if hasattr(policy, "reseed"):
        policy.reseed(seed * 104729 + 17)
    m = play(Match(cfg, [P.PROFILES[x] for x in ALLIANCE], seed=seed, opp=opp), policy)
    r = m.result()
    r["algae_removed"] = 6 - m.low - m.high
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", default="regular")
    ap.add_argument("--blocking", default="B")
    ap.add_argument("--matches", type=int, default=400)
    ap.add_argument("--iters", type=int, default=300)
    ap.add_argument("--c", type=float, default=0.5)
    ap.add_argument("--scen", type=int, default=16, help="scenarios per candidate (rollout planner)")
    ap.add_argument("--win-scen", default="32,64", help="extra rollout-win rows (scenario sweep)")
    ap.add_argument("--z", type=float, default=1.0, help="significance gate for the -z rows (fixed a priori)")
    ap.add_argument("--seed-offset", type=int, default=0)
    ap.add_argument("--only", default="", help="comma list of policy names to run (default all)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = ap.parse_args()
    cfg = GameConfig(event=args.event, algae_blocking=args.blocking)
    truth = build_bank(cfg, 7_000_000, 512)
    planner_bank = build_bank(cfg, 8_000_000, 512)
    seeds = list(range(args.seed_offset, args.seed_offset + args.matches))
    opps = [truth[s] for s in seeds]
    # Planners share one base heuristic (greedy-proc, the best RP heuristic here) so
    # rows differ only in the objective they optimise.
    R = lambda obj, n=args.scen, z=0.0: RolloutPolicy(obj, Greedy("proc"), n_scen=n,
                                                       opp_bank=planner_bank, min_z=z)
    policies = [
        Greedy("net"), Greedy("proc"), Greedy("coop"), rp_seeker(),
        R("points"), R("margin"), R("win"), R("rp"),
        *[R("win", int(n)) for n in args.win_scen.split(",") if n],
        R("win", z=args.z), R("rp", z=args.z),
        MCTSPolicy("rp", args.iters, rollout=Greedy("proc"), c=args.c, opp_bank=planner_bank,
                   action_filter=NoEarlyTerminal(25.0)),
    ]
    if args.only:
        keep = set(args.only.split(","))
        policies = [policies[0]] + [p for p in policies[1:] if p.name in keep]
    lines = []

    def emit(s=""):
        print(s)
        lines.append(s)
        sys.stdout.flush()

    opp_pts = mean_ci([o[0] for o in opps])[0]
    opp_proc = mean_ci([o[1] for o in opps])[0]
    emit(f"# Alliance comparison — event `{args.event}`, blocking {args.blocking}, "
         f"{args.matches} matches (CRN, seeds {seeds[0]}..{seeds[-1]}), "
         f"MCTS {args.iters} it/decision, c={args.c}")
    emit(f"\nAlliance {ALLIANCE} vs same-profile opponent (raw {opp_pts:.1f} pts, "
         f"{opp_proc:.2f} ALGAE processed on average; 50% coop-minded).\n")
    emit("| policy | E[points] | P(win) | E[RP] | P(coral RP) | P(barge RP) | P(coop) | "
         "processed | net | algae removed | coral L1/L2/L3/L4 | ΔRP vs greedy-net | ΔP(win) | time |")
    emit("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    base = None
    with ProcessPoolExecutor(args.workers) as ex:
        for pol in policies:
            t0 = time.perf_counter()
            rs = list(ex.map(_one, [(cfg, pol, s, o) for s, o in zip(seeds, opps)], chunksize=4))
            col = {k: [r[k] for r in rs] for k in ("points", "win", "rp", "coral_rp", "barge_rp",
                                                  "coop", "processed", "net", "algae_removed")}
            lv = [sum(r["levels"][i] for r in rs) / len(rs) for i in range(4)]
            if base is None:
                base = col
            d_rp, h_rp = paired(col["rp"], base["rp"])
            d_w, h_w = paired(col["win"], base["win"])
            f = lambda k, d=2: "{:.{d}f} ± {:.{d}f}".format(*mean_ci(col[k]), d=d)
            emit(f"| {pol.name} | {f('points', 1)} | {f('win')} | {f('rp')} | {f('coral_rp')} | "
                 f"{f('barge_rp')} | {f('coop')} | {mean_ci(col['processed'])[0]:.2f} | "
                 f"{mean_ci(col['net'])[0]:.2f} | {mean_ci(col['algae_removed'])[0]:.2f} | "
                 + "/".join(f"{x:.1f}" for x in lv)
                 + f" | {d_rp:+.3f} ± {h_rp:.3f} | {d_w:+.3f} ± {h_w:.3f} | "
                 f"{time.perf_counter() - t0:.0f}s |")
    os.makedirs("results", exist_ok=True)
    with open(f"results/alliance_{args.event}_{args.blocking}.md", "w") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
