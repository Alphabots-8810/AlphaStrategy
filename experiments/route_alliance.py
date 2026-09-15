"""Alliance reef fill, REEFSCAPE 2025 blue side: routes, zones, order, algae disposal.

Uses src/frcsim/reefscape2025/routing.py (field geometry + trapezoidal velocity profile),
not the 4-location travel matrix of sim.py. Writes results/route_alliance.md and the
route map results/route_alliance.svg. A few minutes on one core.

    .venv/bin/python experiments/route_alliance.py [--mc 400] [--anneal-iters 15000]
"""
from __future__ import annotations

import argparse
import itertools
import math
import os
import statistics
import sys
from dataclasses import replace

from frcsim.reefscape2025 import rules
from frcsim.reefscape2025 import routing as R

NAME = R.FACE_NAME
PTS = rules.CORAL_PTS["teleop"]
MARKS = (20, 30, 40, 50, 60)
COL = ["#d9480f", "#1971c2", "#2f9e44"]


def mc(p, chooser, policy="floor", n=400, n_robots=3):
    """Monte Carlo over runs 0..n-1 (the same draws for every policy). -> mean, p90, sorted."""
    xs = sorted(R.simulate(p, n_robots, chooser, policy=policy, noise=R.Noise(run=k))[0]
                for k in range(n))
    return statistics.mean(xs), xs[int(0.9 * n)], xs


def pairings(fs):
    if not fs:
        yield []
        return
    for i in range(1, len(fs)):
        for rest in pairings(fs[1:i] + fs[i + 1:]):
            yield [(fs[0], fs[i])] + rest


def banked(log):
    ev = [(e[3], PTS[e[5][2]]) for e in log if "MISS" not in e[6]]
    return [sum(v for t, v in ev if t <= m) for m in MARKS]


def zlabel(z):
    return " / ".join("+".join(sorted(NAME[f] for f in z[r])) for r in sorted(z))


def write_svg(path, p, zones, policy):
    F = R.FIELD[p]
    log = []
    T, _ = R.simulate(p, 3, R.zone_level_chooser(zones), policy=policy, log=log)
    legs, detours, algae_to = {}, {}, {r: [] for r in range(3)}
    for r in range(3):
        rows = sorted((x for x in log if x[0] == r), key=lambda x: x[3])
        for i, (_, _, _, _, s, (f, _, _), note) in enumerate(rows):
            legs[(r, s, f)] = legs.get((r, s, f), 0) + 1
            if "->" in note:
                dest = note.split("->")[1].strip()
                algae_to[r].append(f"{NAME[f]}→{'processor' if dest == 'PROC' else 'net'}")
                nxt = rows[i + 1][4] if i + 1 < len(rows) else None
                detours[(r, f, dest, nxt)] = 1
    done = {r: max(x[3] for x in log if x[0] == r) for r in range(3)}

    S, W, H = 72, 8.9, R.FIELD_WIDTH
    X = lambda x: 20 + x * S
    Y = lambda y: 20 + (H - y) * S
    pts = lambda ps: " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in ps)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{X(W) + 20:.0f}" height="{Y(0) + 280:.0f}" '
         'font-family="-apple-system,Helvetica,Arial,sans-serif" font-size="13">',
         '<rect width="100%" height="100%" fill="#ffffff"/>',
         f'<rect x="{X(0)}" y="{Y(H)}" width="{W * S:.1f}" height="{H * S:.1f}" fill="#f4f6f8" stroke="#868e96"/>',
         f'<text x="{X(0) + 6}" y="{Y(H / 2) + 4:.1f}" font-size="11" fill="#868e96" '
         f'transform="rotate(-90 {X(0) + 12} {Y(H / 2):.1f})">blue alliance wall</text>']
    o.append(f'<polygon points="{pts(sorted(F.verts, key=lambda q: math.atan2(q[1] - R.CENTER[1], q[0] - R.CENTER[0])))}" '
             'fill="none" stroke="#adb5bd" stroke-dasharray="4 4"/>')
    rv = R.APOTHEM / math.cos(math.pi / 6)
    hexp = [(R.CENTER[0] + rv * math.cos(R.TAG[f][2] + s * math.pi / 6),
             R.CENTER[1] + rv * math.sin(R.TAG[f][2] + s * math.pi / 6))
            for f in sorted(R.FACES, key=lambda f: R.TAG[f][2] % (2 * math.pi)) for s in (-1, 1)]
    o.append(f'<polygon points="{pts(hexp)}" fill="#dee2e6" stroke="#495057"/>')
    for x, y in R.CORAL_MARKS:
        o.append(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="7" fill="#20c997" opacity="0.6"/>')
    for s in R.STATIONS:
        x, y, yaw = R.TAG[s]
        tx, ty = math.cos(yaw + math.pi / 2), math.sin(yaw + math.pi / 2)
        o.append(f'<line x1="{X(x - 0.97 * tx):.1f}" y1="{Y(y - 0.97 * ty):.1f}" x2="{X(x + 0.97 * tx):.1f}" '
                 f'y2="{Y(y + 0.97 * ty):.1f}" stroke="#212529" stroke-width="6"/>')
        o.append(f'<text x="{X(x) + 30:.1f}" y="{Y(y) + (22 if y < 4 else -12):.1f}" font-weight="600">station {s}</text>')
    px, _ = F.pose["PROC"]
    o.append(f'<rect x="{X(px) - 24:.1f}" y="{Y(0) - 12:.1f}" width="48" height="12" fill="#495057"/>'
             f'<text x="{X(px):.1f}" y="{Y(0) - 18:.1f}" text-anchor="middle" font-weight="600">processor</text>')
    nx, ny = F.pose["NET"]
    o.append(f'<circle cx="{X(nx):.1f}" cy="{Y(ny):.1f}" r="6" fill="#495057"/>'
             f'<text x="{X(nx) - 10:.1f}" y="{Y(ny) - 10:.1f}" text-anchor="end" font-weight="600">net shot</text>')
    for (r, f, dest, nxt) in detours:
        ps = F.path((f, 1), dest)
        if nxt is not None:
            ps += F.path(dest, nxt)[1:]
        o.append(f'<polyline points="{pts(ps)}" fill="none" stroke="{COL[r]}" stroke-width="2" '
                 'stroke-dasharray="6 5" stroke-opacity="0.9"/>')
    for (r, s, f), n in sorted(legs.items(), key=lambda kv: (kv[0][0], str(kv[0][1]), kv[0][2])):
        off = (r - 1) * 0.05
        ps = [(x + off, y + off) for x, y in F.path(s, (f, 1))]
        o.append(f'<polyline points="{pts(ps)}" fill="none" stroke="{COL[r]}" stroke-width="{1.5 + 1.2 * n:.1f}" '
                 'stroke-opacity="0.75" stroke-linecap="round"/>')
    for f in R.FACES:
        yaw = R.TAG[f][2]
        lx, ly = R.CENTER[0] + 0.5 * math.cos(yaw), R.CENTER[1] + 0.5 * math.sin(yaw)
        o.append(f'<text x="{X(lx):.1f}" y="{Y(ly) + 1:.1f}" text-anchor="middle" font-weight="700">{NAME[f]}</text>')
        o.append(f'<text x="{X(lx):.1f}" y="{Y(ly) + 13:.1f}" text-anchor="middle" font-size="10" fill="#495057">'
                 f'{"high" if f in R.HIGH_ALGAE_FACES else "low"}</text>')
    y0 = Y(0) + 34
    o.append(f'<text x="{X(0)}" y="{y0}" font-size="15" font-weight="700">3-robot zones: two faces each, '
             'L4 → L3 → L2, each trip via the station that places soonest</text>')
    o.append(f'<text x="{X(0)}" y="{y0 + 21}">All 36 L2–L4 branches filled at {T:.1f} s (no noise)</text>')
    o.append(f'<text x="{X(0)}" y="{y0 + 39}">Solid: station → reef (thicker = more trips). '
             'Dashed: carrying algae to the processor / net, then to a station</text>')
    for r in range(3):
        fs = "+".join(sorted(NAME[f] for f in zones[r]))
        trips = ", ".join(f"st{s}→{NAME[f]} ×{n}" for (rr, s, f), n in sorted(legs.items(), key=lambda kv: (-kv[1], NAME[kv[0][2]], str(kv[0][1])))
                         if rr == r)
        alg = ", ".join(algae_to[r]) or "algae to the floor"
        yy = y0 + 66 + 40 * r
        o.append(f'<rect x="{X(0)}" y="{yy - 11}" width="14" height="14" fill="{COL[r]}"/>'
                 f'<text x="{X(0) + 22}" y="{yy + 1}" font-weight="600">Robot {r + 1} ({fs}): {trips}</text>'
                 f'<text x="{X(0) + 22}" y="{yy + 18}" font-size="12" fill="#343a40">algae: {alg}; '
                 f'last placement {done[r]:.1f} s</text>')
    foot = ["Given by 8810: v 4 m/s, a 5 m/s², intake 1.0 s, place L2/L3 0.7 s, L4 1.0 s. Robots start at CD / AB / KL.",
            "Placeholders: algae removal 0.8 s, processor / net 0.5 s. Green dots: floor algae on the coral marks.",
            "Blue half, WPILib 2025 AprilTag coordinates. Dashed hexagon: the reef inflated by the robot half-length."]
    for i, line in enumerate(foot):
        o.append(f'<text x="{X(0)}" y="{y0 + 196 + 16 * i}" font-size="11" fill="#495057">{line}</text>')
    o.append("</svg>")
    with open(path, "w") as fh:
        fh.write("\n".join(o) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mc", type=int, default=400, help="Monte Carlo runs per table cell")
    ap.add_argument("--mc-zones", type=int, default=300, help="Monte Carlo runs per zone pairing")
    ap.add_argument("--mc-final", type=int, default=1000, help="Monte Carlo runs for the recommended tactic")
    ap.add_argument("--anneal-iters", type=int, default=15000)
    ap.add_argument("--anneal-seeds", type=int, default=4)
    ap.add_argument("--out", default="results/route_alliance.md")
    ap.add_argument("--svg", default="results/route_alliance.svg")
    args = ap.parse_args()
    lines = []

    def emit(s=""):
        print(s)
        lines.append(s)
        sys.stdout.flush()

    U, SL = R.USER, R.SLOWER
    PARAMS = (U, SL)
    tz = R.TACTIC_ZONES
    emit("# Alliance reef fill (REEFSCAPE 2025, blue side)\n")
    emit("Model: `src/frcsim/reefscape2025/routing.py` (WPILib 2025 AprilTag geometry, shortest paths "
         "around the reef, one trapezoidal velocity profile per leg, one robot at a time per coral station, "
         "per reef face and at the processor). Three identical robots start at faces CD / AB / KL with an empty reef "
         "(no AUTO); the task is to fill all 36 L2–L4 branches.\n")
    emit(f"- **{U.name}**: given by the user. Algae removal {U.t_rm} s, processor / net {U.t_proc} s and "
         f"robot half-length {U.half} m are placeholders.")
    emit(f"- **{SL.name}**: a pessimistic variant.")
    emit("- Monte Carlo (MC): service times lognormal CV 0.25, driving CV 0.08, 3% of placements miss and are "
         "redone. Run k uses the same draws for every plan (common random numbers).")
    emit("- Staged algae (rules.ALGAE_BLOCKING['B']): high on AB/EF/IJ blocks L3 of its face; low on "
         "CD/GH/KL blocks L2 and L3. A robot removes it when it first targets a blocked level.\n")

    F = R.FIELD[U]
    emit("## 1. Geometry: shortest path from a branch to the nearest coral station\n")
    emit("| face | tag | staged algae | blocks | nearest station | path (m), near / far branch "
         "| one-way time (s) |")
    emit("|---|---|---|---|---|---|---|")
    rows = []
    for f in R.FACES:
        per = sorted(min((F.length(s, (f, side)), s) for s in R.STATIONS) for side in (-1, 1))
        rows.append((per[0][0], f, per))
    for _, f, per in sorted(rows):
        sts = "/".join(str(s) for s in sorted({s for _, s in per}))
        emit(f"| {NAME[f]} | {f} | {'high' if f in R.HIGH_ALGAE_FACES else 'low'} | "
             f"{'+'.join('L%d' % lv for lv in R.BLOCKS[f])} | {sts} | {per[0][0]:.2f} / {per[1][0]:.2f} | "
             f"{R.leg(per[0][0], U):.2f} / {R.leg(per[1][0], U):.2f} |")

    emit("\n## 2. How many robots does it take (deterministic)\n")
    emit("| params | robots | lower bound (s) | reactive greedy (s) |")
    emit("|---|---|---|---|")
    for p in PARAMS:
        for n in (1, 2, 3):
            emit(f"| {p.name.split()[0]} | {n} | {R.lower_bound(p, n):.1f} | {R.simulate(p, n, R.greedy)[0]:.1f} |")

    emit("\n## 3. Does the plan matter? (3 robots, algae knocked to the floor)\n")
    emit("| params | plan | deterministic (s) | MC mean (s) | MC p90 (s) |")
    emit("|---|---|---|---|---|")
    for p in PARAMS:
        best, fb = None, math.inf
        for sd in range(1, args.anneal_seeds + 1):
            plan, f = R.anneal(p, 3, iters=args.anneal_iters, seed=sd)
            if f < fb:
                best, fb = plan, f
        plans = [
            (f"annealed fixed plan (best of {args.anneal_seeds} × {args.anneal_iters} iters)", R.plan_chooser(best)),
            ("reactive greedy (soonest finish)", R.greedy),
            (f"zones {zlabel(tz)}, soonest finish", R.zone_chooser(tz)),
            (f"zones {zlabel(tz)}, L4 → L3 → L2", R.zone_level_chooser(tz)),
            ("naive: own station (12/13/12), AB→KL, L4 first", R.naive_chooser({0: 12, 1: 13, 2: 12})),
            ("naive: everyone uses station 12", R.naive_chooser({0: 12, 1: 12, 2: 12})),
        ]
        emit(f"| {p.name.split()[0]} | lower bound | {R.lower_bound(p, 3):.1f} | | |")
        for label, ch in plans:
            m, p90, _ = mc(p, ch, n=args.mc)
            emit(f"| {p.name.split()[0]} | {label} | {R.simulate(p, 3, ch)[0]:.1f} | {m:.1f} | {p90:.1f} |")

    emit(f"\n## 4. Every way to give each robot two faces (15 pairings; each with its best "
         f"robot-to-pair assignment; MC {args.mc_zones} runs; soonest finish within the zone)\n")
    for p in PARAMS:
        emit(f"**{p.name}**\n")
        emit("| zones (robots start at CD / AB / KL) | deterministic (s) | MC mean (s) | MC p90 (s) |")
        emit("|---|---|---|---|")
        res = []
        for pr in pairings(list(R.FACES)):
            best = None
            for perm in itertools.permutations(pr):
                z = {r: set(perm[r]) for r in range(3)}
                t = R.simulate(p, 3, R.zone_chooser(z))[0]
                if best is None or t < best[0]:
                    best = (t, z)
            t, z = best
            m, p90, _ = mc(p, R.zone_chooser(z), n=args.mc_zones)
            res.append((m, p90, t, z))
        for m, p90, t, z in sorted(res, key=lambda x: x[0]):
            emit(f"| {zlabel(z)} | {t:.1f} | {m:.1f} | {p90:.1f} |")
        emit()

    emit(f"## 5. Order within the zones ({zlabel(tz)}): time to fill and coral points banked\n")
    emit(f"| params | algae | order | deterministic (s) | MC mean (s) | MC p90 (s) | coral points by {MARKS} s, deterministic run |")
    emit("|---|---|---|---|---|---|---|")
    for p in PARAMS:
        for pol in ("floor", "proc_cdef"):
            for label, mk in (("soonest finish", R.zone_chooser), ("L4 → L3 → L2", R.zone_level_chooser)):
                log = []
                t = R.simulate(p, 3, mk(tz), policy=pol, log=log)[0]
                m, p90, _ = mc(p, mk(tz), pol, n=args.mc)
                emit(f"| {p.name.split()[0]} | {pol} | {label} | {t:.1f} | {m:.1f} | {p90:.1f} | {banked(log)} |")

    emit(f"\n## 6. What to do with the staged algae (zones {zlabel(tz)}, L4 → L3 → L2)\n")
    emit("Processor 6 points, net 4. An algae through our processor goes to the opponent's human player, "
         "who can throw it into their net for 4. In qualification matches, 2 processed algae per alliance "
         "(both alliances) is Coopertition, which cuts the Coral RP to 3 levels.\n")
    emit("| params | policy | deterministic (s) | MC mean (s) | MC p90 (s) | processor / net / floor "
         "(deterministic run) | our algae points | opponent HP can get back |")
    emit("|---|---|---|---|---|---|---|---|")
    for p in PARAMS:
        for pol, desc in R.ALGAE_POLICIES.items():
            t, s = R.simulate(p, 3, R.zone_level_chooser(tz), policy=pol)
            m, p90, _ = mc(p, R.zone_level_chooser(tz), pol, n=args.mc)
            emit(f"| {p.name.split()[0]} | {desc} | {t:.1f} | {m:.1f} | {p90:.1f} | {s['proc']} / {s['net']} / "
                 f"{s['floor']} | {s['proc'] * rules.PROCESSOR_PTS + s['net'] * rules.NET_PTS} | "
                 f"≤ {s['proc'] * rules.NET_PTS} |")

    emit("\n## 7. Intake spot along the coral station (the opening is 1.93 m wide, manual 5.6.2)\n")
    emit("| params | intake spot | lower bound (s) | reactive greedy (s) | annealed, 3000 iters (s) |")
    emit("|---|---|---|---|---|")
    for p in PARAMS:
        for sl in (0.0, 0.5):
            q = replace(p, name=p.name + f" slide {sl}", slide=sl)
            where = "station centre" if sl == 0 else f"centre or ±{sl} m"
            emit(f"| {p.name.split()[0]} | {where} | {R.lower_bound(q, 3):.1f} | "
                 f"{R.simulate(q, 3, R.greedy)[0]:.1f} | {R.anneal(q, 3, iters=3000, seed=3)[1]:.1f} |")

    emit("\n## 8. Sensitivity (user params, reactive greedy, algae to the floor, deterministic)\n")
    emit("| change | 3 robots (s) | lower bound, 3 robots (s) | 2 robots (s) |")
    emit("|---|---|---|---|")
    for trm in (0.5, 0.8, 1.5):
        q = replace(U, name=f"t_rm {trm}", t_rm=trm)
        emit(f"| algae removal {trm} s | {R.simulate(q, 3, R.greedy)[0]:.1f} | {R.lower_bound(q, 3):.1f} | "
             f"{R.simulate(q, 2, R.greedy)[0]:.1f} |")
    for v, a in ((3.0, 3.0), (4.0, 5.0), (4.5, 8.0)):
        q = replace(U, name=f"v{v} a{a}", vmax=v, acc=a)
        emit(f"| v {v} m/s, a {a} m/s² | {R.simulate(q, 3, R.greedy)[0]:.1f} | {R.lower_bound(q, 3):.1f} | "
             f"{R.simulate(q, 2, R.greedy)[0]:.1f} |")
    emit("\nExtra seconds per stop (alignment / settling, once at the station and once at the reef). "
         "Cycle = a robot's time from the start to its last placement ÷ the coral it placed, averaged over "
         "the robots; queueing is included, so it is what you can time from match video.\n")
    emit("| extra per stop | 3 robots: fill (s) | 3 robots: cycle (s) | 2 robots: fill (s) | 2 robots: cycle (s) |")
    emit("|---|---|---|---|---|")
    for x in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        q = replace(U, name=f"align {x}", t_align=x)
        row = []
        for n in (3, 2):
            log = []
            t = R.simulate(q, n, R.greedy, log=log)[0]
            cyc = statistics.mean(max(e[3] for e in log if e[0] == r) / sum(e[0] == r for e in log)
                                  for r in range(n))
            row += [f"{t:.1f}", f"{cyc:.2f}"]
        emit(f"| +{x:.1f} s | " + " | ".join(row) + " |")

    emit(f"\n## 9. Recommended tactic: zones {zlabel(tz)}, L4 → L3 → L2, "
         f"{R.ALGAE_POLICIES['proc_cdef']}\n")
    emit(f"| params | deterministic (s) | MC mean | p10 | p50 | p90 | p99 | max (MC {args.mc_final} runs) |")
    emit("|---|---|---|---|---|---|---|---|")
    for p in PARAMS:
        n = args.mc_final
        m, _, xs = mc(p, R.zone_level_chooser(tz), "proc_cdef", n=n)
        t = R.simulate(p, 3, R.zone_level_chooser(tz), policy="proc_cdef")[0]
        emit(f"| {p.name.split()[0]} | {t:.1f} | {m:.1f} | {xs[n // 10]:.1f} | {xs[n // 2]:.1f} | "
             f"{xs[int(0.9 * n)]:.1f} | {xs[int(0.99 * n)]:.1f} | {xs[-1]:.1f} |")
    emit("\nTrips (user params, deterministic; time = placement done; * = removed that face's algae first):\n")
    log = []
    R.simulate(U, 3, R.zone_level_chooser(tz), policy="proc_cdef", log=log)
    for r in range(3):
        rows = sorted((x for x in log if x[0] == r), key=lambda x: x[3])
        emit(f"- Robot {r + 1} ({'+'.join(sorted(NAME[f] for f in tz[r]))}): " + ", ".join(
            f"{e:.0f} s st{s}→{NAME[f]}-L{lv}" + (f"* (algae → {'processor' if 'PROC' in note else 'net'})"
                                                   if '->' in note else "")
            for _, _, _, e, s, (f, _, lv), note in rows))
    write_svg(args.svg, U, tz, "proc_cdef")
    emit(f"\n![route map]({os.path.basename(args.svg)})\n")

    emit("## 10. After the fill (user params): one-way leg times (s)\n")
    emit("| from | to net shot | to processor | to nearest station |")
    emit("|---|---|---|---|")
    for f in R.FACES:
        near = lambda dest: min(F.t((f, sd), dest) for sd in (-1, 1))
        emit(f"| face {NAME[f]} (nearer branch) | {near('NET'):.2f} | {near('PROC'):.2f} | "
             f"{min(near(s) for s in R.STATIONS):.2f} |")
    for i, q in enumerate(R.CORAL_MARKS):
        F.pose[f"MARK{i}"] = q
        emit(f"| coral-mark algae {i + 1} (y = {q[1]:.2f} m) | {F.t(f'MARK{i}', 'NET'):.2f} | "
             f"{F.t(f'MARK{i}', 'PROC'):.2f} | {min(F.t(f'MARK{i}', s) for s in R.STATIONS):.2f} |")
    rt = statistics.mean(2 * min(F.t(s, (f, 1)) for s in R.STATIONS) for f in R.FACES)
    emit(f"\nAn L1 trip (station → reef → station, average over faces): {rt:.2f} s driving + "
         f"{U.t_intake} s intake + placement.")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
