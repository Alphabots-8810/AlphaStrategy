"""Sensitivity analysis - the intended deliverable while profiles are uncalibrated.

  A  exact single-robot DP: dV*/d(capability)  ("which upgrade is worth most points")
  B  alliance, CRN: dE[RP], dP(win) per capability change  (policy = rp-seeker heuristic)
  C  PROCESSOR vs NET break-even vs opponent HUMAN PLAYER accuracy
  D  Coopertition: value of processing as a function of opponent coop intent

    .venv/bin/python experiments/sensitivity.py [--dp] [--matches 3000]
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace

from frcsim.reefscape2025 import dp
from frcsim.reefscape2025 import profiles as P
from frcsim.reefscape2025.policies import Greedy, rp_seeker
from frcsim.reefscape2025.sim import GameConfig, Match, OpponentBank, play
from frcsim.stats import mean_ci, paired

BASE = (P.ELITE, P.MID, P.LOW)
lines = []


def emit(s=""):
    print(s)
    lines.append(s)
    sys.stdout.flush()


def bank(cfg, coop_frac, n=3000, seed0=7_000_000):
    """Opponent outcomes; a `coop_frac` share play greedy-coop, the rest greedy-net.
    Entry i is coop-minded iff floor((i+1)*f) > floor(i*f), so every prefix keeps the mix."""
    coop = OpponentBank(cfg, BASE, Greedy("coop"), n=n, seed0=seed0).outcomes
    net = OpponentBank(cfg, BASE, Greedy("net"), n=n, seed0=seed0 + n).outcomes
    return [coop[i] if int((i + 1) * coop_frac) > int(i * coop_frac) else net[i]
            for i in range(n)]


def run(cfg, profiles, policy, opps, seeds):
    rs = []
    for s in seeds:
        m = play(Match(cfg, profiles, seed=s, opp=opps[s % len(opps)]), policy)
        rs.append(m.result())
    return rs


def col(rs, k):
    return [float(r[k]) for r in rs]


def section_dp():
    cfg = GameConfig(auto=False, floor_algae=False)
    emit("## A. Exact single-robot DP sensitivities (elite, TELEOP only)\n")
    base = dp.solve(P.ELITE, cfg)
    v0 = base.value(cfg.start_loc)
    emit(f"Baseline V* = {v0:.2f} expected TELEOP points (solve {base.seconds:.0f}s).\n")
    emit("| change | V* | ΔV* |")
    emit("|---|---|---|")
    E = P.ELITE
    variants = [
        ("L4 place time 1.5→1.2 s", E.with_task(P.L4, mean=1.2), cfg),
        ("intake time 0.8→0.6 s", E.with_task(P.INTAKE, mean=0.6), cfg),
        ("drive 10% faster", replace(E, speed_factor=0.9), cfg),
        ("L4 success 0.94→0.99", E.with_task(P.L4, p=0.99), cfg),
        ("deep climb 6.0→4.5 s", E.with_task(P.CLIMB, mean=4.5), cfg),
        ("deep climb success 0.90→0.97", E.with_task(P.CLIMB, p=0.97), cfg),
        ("shallow instead of deep (same time/p)", replace(E, climb="shallow"), cfg),
        ("no ALGAE handling at all", replace(E, remove_low=None, remove_high=None,
                                             hold_algae=False, net=None, processor=None), cfg),
        ("ALGAE blocking reading A", E, replace(cfg, algae_blocking="A")),
    ]
    for name, prof, c in variants:
        v = dp.solve(prof, c).value(c.start_loc)
        emit(f"| {name} | {v:.2f} | {v - v0:+.2f} |")
    emit()


def section_alliance(matches):
    cfg = GameConfig()
    opps = bank(cfg, 0.5)
    seeds = range(matches)
    pol = rp_seeker()
    emit(f"## B. Alliance sensitivities (rp-seeker policy, {matches} CRN matches, "
         "opponent 50% coop-minded)\n")
    ref = run(cfg, BASE, pol, opps, seeds)
    emit(f"Baseline: E[RP] {mean_ci(col(ref, 'rp'))[0]:.3f}, P(win) {mean_ci(col(ref, 'win'))[0]:.3f}, "
         f"E[points] {mean_ci(col(ref, 'points'))[0]:.1f}\n")
    emit("| change | ΔE[RP] | ΔP(win) | ΔE[points] | ΔP(coral RP) | ΔP(barge RP) |")
    emit("|---|---|---|---|---|---|")
    E, M, L = BASE
    variants = [
        ("elite: L4 place 1.5→1.2 s", (E.with_task(P.L4, mean=1.2), M, L), cfg),
        ("elite: drive 10% faster", (replace(E, speed_factor=0.9), M, L), cfg),
        ("mid: add L4 (2.8 s, p .8)", (E, replace(M, score={**M.score, P.L4: P.Task(2.8, 0.25, 0.8)}), L), cfg),
        ("mid: shallow→deep climb", (E, replace(M, climb="deep"), L), cfg),
        ("l1bot: add shallow climb (8 s, p .75)", (E, M, replace(L, climb="shallow", climb_task=P.Task(8.0, 0.3, 0.75))), cfg),
        ("l1bot: add L2 (2.2 s, p .85)", (E, M, replace(L, score={**L.score, P.L2: P.Task(2.2, 0.3, 0.85)})), cfg),
        ("our HP net 50%→80%", BASE, replace(cfg, hp_net_p=0.8)),
        ("REEF congestion ×2", BASE, replace(cfg, reef_congestion_s=(0.0, 1.0, 3.5))),
        ("ALGAE blocking reading A", BASE, replace(cfg, algae_blocking="A")),
    ]
    for name, profs, c in variants:
        o = bank(c, 0.5) if c != cfg else opps
        rs = run(c, profs, pol, o, seeds)
        cells = [paired(col(rs, k), col(ref, k)) for k in ("rp", "win", "points", "coral_rp", "barge_rp")]
        emit(f"| {name} | " + " | ".join(f"{d:+.3f} ± {h:.3f}" if i != 2 else f"{d:+.1f} ± {h:.1f}"
                                         for i, (d, h) in enumerate(cells)) + " |")
    emit()


def section_processor(matches):
    emit("## C. PROCESSOR vs NET: greedy-proc minus greedy-net, by opponent HP accuracy\n")
    emit("Processing scores 6 for us but feeds the opponent HUMAN PLAYER a 4-pt NET throw.\n")
    emit("| opp HP net % | Δmargin (ours−theirs) | ΔP(win) | ΔE[RP] |")
    emit("|---|---|---|---|")
    seeds = range(matches)
    for p_hp in (0.0, 0.25, 0.5, 0.75, 1.0):
        cfg = GameConfig(opp_hp_net_p=p_hp)
        opps = bank(cfg, 0.5)
        a = run(cfg, BASE, Greedy("proc"), opps, seeds)
        b = run(cfg, BASE, Greedy("net"), opps, seeds)
        ma = [r["points"] - r["opp_points"] for r in a]
        mb = [r["points"] - r["opp_points"] for r in b]
        dm, hm = paired(ma, mb)
        dw, hw = paired(col(a, "win"), col(b, "win"))
        dr, hr = paired(col(a, "rp"), col(b, "rp"))
        emit(f"| {int(p_hp * 100)} | {dm:+.2f} ± {hm:.2f} | {dw:+.3f} ± {hw:.3f} | {dr:+.3f} ± {hr:.3f} |")
    emit()


def section_coop(matches):
    emit("## D. Coopertition: greedy-coop minus greedy-net, by opponent coop intent\n")
    emit("| opponent coop-minded | P(coop) coop-policy | ΔE[RP] | ΔP(coral RP) | ΔP(win) |")
    emit("|---|---|---|---|---|")
    seeds = range(matches)
    for frac in (0.0, 0.5, 1.0):
        for ev in ("regular", "champs"):
            cfg = GameConfig(event=ev)
            opps = bank(cfg, frac)
            a = run(cfg, BASE, Greedy("coop"), opps, seeds)
            b = run(cfg, BASE, Greedy("net"), opps, seeds)
            dr, hr = paired(col(a, "rp"), col(b, "rp"))
            dc, hc = paired(col(a, "coral_rp"), col(b, "coral_rp"))
            dw, hw = paired(col(a, "win"), col(b, "win"))
            emit(f"| {int(frac * 100)}% ({ev}) | {mean_ci(col(a, 'coop'))[0]:.2f} | {dr:+.3f} ± {hr:.3f} | "
                 f"{dc:+.3f} ± {hc:.3f} | {dw:+.3f} ± {hw:.3f} |")
    emit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dp", action="store_true", help="include section A (re-solves the DP 10x)")
    ap.add_argument("--matches", type=int, default=3000)
    args = ap.parse_args()
    emit("# Sensitivity analysis (UNCALIBRATED profiles — read the deltas, not the levels)\n")
    if args.dp:
        section_dp()
    section_alliance(args.matches)
    section_processor(args.matches)
    section_coop(args.matches)
    os.makedirs("results", exist_ok=True)
    with open("results/sensitivity.md", "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
