"""How much does the rollout planner's tie rule matter?

World randomness is keyed by (seed, robot, action, n-th use), so two candidates that
are order permutations of the same actions (INTAKE then REM_LOW vs REM_LOW then
INTAKE) draw the same luck, complete the same actions by the buzzer and tie EXACTLY
in every scenario. Four parts:

  probe     single robot (elite, TELEOP): how often candidates tie exactly, and how
            often the two rules pick differently
  A/B       single robot: ties keep the base action (RolloutPolicy, current code) vs
            first max in legal-action order (pre-fix code; INTAKE sorts first),
            paired on fresh seeds
  alliance  the same A/B for the `points` and `margin` objectives, with the world
            seeds / opponents / planner bank / planner reseed of experiments/alliance.py
  discrete  the `win` objective with and without the fix (base-first ties + the
            1e-4/point tie-break of policies.Objective), against its base greedy-proc

    .venv/bin/python experiments/tie_rule_ab.py [--matches 200] [--alliance-matches 400]
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

from alliance import ALLIANCE, build_bank
from frcsim.reefscape2025 import dp
from frcsim.reefscape2025 import profiles as P
from frcsim.reefscape2025.policies import Greedy, Objective, RolloutPolicy, _no_peek
from frcsim.reefscape2025.sim import GameConfig, Match, play
from frcsim.stats import mean_ci, paired

CFG = GameConfig(auto=False, floor_algae=False)


def _totals(pol, m, r, cands):
    """Sum of objective over the same scenarios for every candidate. Draws scenario
    seeds and opponents from the planner RNG in the same order as RolloutPolicy."""
    scen = [(pol.rng.getrandbits(62),
             pol.opp_bank.sample(pol.rng) if pol.opp_bank is not None else None)
            for _ in range(pol.n_scen)]
    tots = {}
    for a in cands:
        tot = 0.0
        for sd, opp in scen:
            c = m.clone()
            c.rng, c.seed, c.opp = None, sd, opp
            c.step(a)
            while (q := c.actor()) >= 0:
                c.step(pol.base(c, q))
            tot += pol.score(c)
        tots[a] = tot
    return tots


class LegalOrderTies(RolloutPolicy):
    """Pre-fix rule: first maximum in legal-action order (no min_z)."""

    def __call__(self, m, r):
        legal = m.legal_actions(r)
        if len(legal) == 1:
            return legal[0]
        _no_peek(m, self.opp_bank)
        tots = _totals(self, m, r, legal)
        mx = max(tots.values())
        return next(a for a in legal if tots[a] == mx)


class LegalOrderNoTiebreak(LegalOrderTies):
    """Pre-fix planner for discrete objectives: legal-order ties AND no points tie-break."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.score = Objective(self.objective, tiebreak=0.0)


class TieProbe(RolloutPolicy):
    """Plays the current rule (ties keep base) and logs what the pre-fix rule would pick."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.log = []

    def __call__(self, m, r):
        legal = m.legal_actions(r)
        if len(legal) == 1:
            return legal[0]
        ba = self.base(m, r)
        tots = _totals(self, m, r, [ba] + [a for a in legal if a != ba])
        mx = max(tots.values())
        new = ba if tots[ba] == mx else next(a for a in legal if a != ba and tots[a] == mx)
        old = next(a for a in legal if tots[a] == mx)
        self.log.append(((m.N - m.busy[r]) * m.cfg.dt, sum(t == mx for t in tots.values()),
                         P.ACTION_NAMES[old], P.ACTION_NAMES[new]))
        return new


RULES = {"base": RolloutPolicy, "legal": LegalOrderTies, "legal-notb": LegalOrderNoTiebreak}


def _ab_one(args):
    rule, n, s = args
    pol = RULES[rule]("teleop", Greedy("proc"), n_scen=n, seed=s * 31337 + n)   # as validate.py
    return play(Match(CFG, [P.ELITE], seed=s), pol).value("teleop")


def _alliance_one(args):
    cfg, rule, obj, n, seed, opp, bank = args
    profs = [P.PROFILES[x] for x in ALLIANCE]
    if rule == "greedy-proc":
        return play(Match(cfg, profs, seed=seed, opp=opp), Greedy("proc")).result()
    pol = RULES[rule](obj, Greedy("proc"), n_scen=n, opp_bank=bank)
    pol.reseed(seed * 104729 + 17)                                      # as alliance.py
    return play(Match(cfg, profs, seed=seed, opp=opp), pol).result()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe-matches", type=int, default=30)
    ap.add_argument("--probe-offset", type=int, default=100_000)
    ap.add_argument("--matches", type=int, default=200)
    ap.add_argument("--offset", type=int, default=400_000,
                    help="A/B seeds: disjoint from tuning and from validate.py's planner seeds")
    ap.add_argument("--scen", default="16,32")
    ap.add_argument("--alliance-matches", type=int, default=400, help="0 = skip the alliance parts")
    ap.add_argument("--alliance-offset", type=int, default=500_000,
                    help="disjoint from the seeds of the reported alliance tables (200000..)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = ap.parse_args()
    lines = []

    def emit(s=""):
        print(s)
        lines.append(s)
        sys.stdout.flush()

    emit("# Rollout tie rule\n")
    dec = ties = diverge = 0
    when, pairs = Counter(), Counter()
    for s in range(args.probe_offset, args.probe_offset + args.probe_matches):
        pol = TieProbe("teleop", Greedy("proc"), n_scen=32, seed=s * 31337 + 32)
        play(Match(CFG, [P.ELITE], seed=s), pol)
        for rem_s, n_tied, old, new in pol.log:
            dec += 1
            if n_tied > 1:
                ties += 1
                when["≤ 25 s left" if rem_s <= 25 else "> 25 s left"] += 1
            if old != new:
                diverge += 1
                pairs[f"{old}→{new}"] += 1
    emit(f"## Probe (elite, TELEOP, 32 scenarios, seeds {args.probe_offset}.."
         f"{args.probe_offset + args.probe_matches - 1})\n")
    emit(f"- decisions with ≥ 2 legal actions: {dec}")
    emit(f"- exact ties at the maximum: {ties} ({100 * ties / dec:.1f}%), {dict(when)}")
    emit(f"- pre-fix rule picks differently: {diverge} ({100 * diverge / dec:.1f}% of decisions, "
         f"{100 * diverge / ties:.1f}% of tied decisions)")
    emit(f"- (pre-fix → current) picks: {dict(pairs.most_common())}\n")

    seeds = list(range(args.offset, args.offset + args.matches))
    res = dp.solve(P.ELITE, CFG)
    dpv = [play(Match(CFG, [P.ELITE], seed=s), dp.DPPolicy(res)).value("teleop") for s in seeds]
    emit(f"## A/B, single robot (elite, TELEOP, fresh seeds {seeds[0]}..{seeds[-1]}, paired, "
         "same planner seed per match)\n")
    emit("| scenarios | gap vs DP, ties keep base (current) | gap vs DP, legal order (pre-fix) "
         "| pre-fix − current |")
    emit("|---|---|---|---|")
    with ProcessPoolExecutor(args.workers) as ex:
        for n in (int(x) for x in args.scen.split(",")):
            v = {rule: list(ex.map(_ab_one, [(rule, n, s) for s in seeds]))
                 for rule in ("base", "legal")}
            g1, h1 = paired(v["base"], dpv)
            g2, h2 = paired(v["legal"], dpv)
            d, h = paired(v["legal"], v["base"])
            emit(f"| {n} | {g1:+.2f} ± {h1:.2f} | {g2:+.2f} ± {h2:.2f} | {d:+.2f} ± {h:.2f} |")

        if args.alliance_matches > 0:
            acfg = GameConfig(event="regular", algae_blocking="B")
            truth = build_bank(acfg, 7_000_000, 512)
            bank = build_bank(acfg, 8_000_000, 512)
            aseeds = list(range(args.alliance_offset, args.alliance_offset + args.alliance_matches))
            opps = [truth[s] for s in aseeds]

            def run(rule, obj):
                return list(ex.map(_alliance_one, [(acfg, rule, obj, 16, s, o, bank)
                                                   for s, o in zip(aseeds, opps)], chunksize=4))

            emit(f"\n## A/B, alliance {ALLIANCE} (regular season, seeds {aseeds[0]}..{aseeds[-1]}, "
                 "16 scenarios, opponents / planner bank / reseed as experiments/alliance.py)\n")
            emit("| objective | metric | ties keep base (current) | legal order (pre-fix) "
                 "| pre-fix − current |")
            emit("|---|---|---|---|---|")
            for obj in ("points", "margin"):
                out = {rule: run(rule, obj) for rule in ("base", "legal")}
                for k in ("points", "margin", "win", "rp"):
                    cur = [float(x[k]) for x in out["base"]]
                    pre = [float(x[k]) for x in out["legal"]]
                    d, h = paired(pre, cur)
                    emit(f"| {obj} | {k} | {mean_ci(cur)[0]:.3f} | {mean_ci(pre)[0]:.3f} | "
                         f"{d:+.3f} ± {h:.3f} |")

            emit(f"\n## Discrete objective `win`, same alliance seeds: what the tie fix does\n")
            emit("current = ties keep the base action + 1e-4/point tie-break (policies.Objective); "
                 "pre-fix = first max in legal-action order, no tie-break.\n")
            emit("| policy | P(win) | E[RP] | E[points] | ΔP(win) vs greedy-proc |")
            emit("|---|---|---|---|---|")
            out = {"greedy-proc": run("greedy-proc", None),
                   "rollout-win-16, current": run("base", "win"),
                   "rollout-win-16, pre-fix": run("legal-notb", "win")}
            base_w = [float(x["win"]) for x in out["greedy-proc"]]
            for name, rs in out.items():
                w = [float(x["win"]) for x in rs]
                d, h = paired(w, base_w)
                emit(f"| {name} | {mean_ci(w)[0]:.3f} | {mean_ci([float(x['rp']) for x in rs])[0]:.3f} | "
                     f"{mean_ci([float(x['points']) for x in rs])[0]:.1f} | {d:+.3f} ± {h:.3f} |")
    os.makedirs("results", exist_ok=True)
    with open("results/tie_rule_ab.md", "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
