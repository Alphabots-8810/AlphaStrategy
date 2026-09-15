"""Alliance reef-fill routing for REEFSCAPE 2025.

Question: three robots fill all 36 L2–L4 branches. Which robot takes which reef face, in
what order, from which coral station, and how long does it take? sim.py / dp.py cannot
answer this: they use an abstract 4-location travel matrix. This module uses the real
field geometry and a trapezoidal velocity profile, and covers only the reef-fill phase
of TELEOP.

Sources
  geometry  WPILib 2025 welded AprilTag layout, blue side (allwpilib v2025.3.2,
            apriltag/src/main/native/resources/edu/wpi/first/apriltag/2025-reefscape-welded.json).
            Reef centre x = 176.746 in, branches 6.469 in either side of a face centre, and
            the coral-mark positions are from FRC 6328 RobotCode2025Public FieldConstants.
  algae     Which faces carry high vs low staged algae: 6328 FieldConstants orders the faces
            18, 19, 20, 21, 22, 17 and AlgaeObjective(id) sets low = (id % 2 == 1), so high
            algae sit on tags 18/20/22 (AB, IJ, EF) and low algae on 19/21/17 (KL, GH, CD).
            What each one blocks is rules.ALGAE_BLOCKING["B"] (low: L2+L3, high: L3).
Model
  - Every coral is one trip: current spot -> coral station (intake) -> branch (remove that
    face's algae first if it blocks the target level) -> place.
  - A leg is one trapezoidal velocity profile, rest to rest, over the shortest path around
    the reef (reef hexagon inflated by the robot half-length; visibility graph).
  - One robot at a time per coral station, per reef face and at the processor, served in
    order of arrival. The net has no queue.
  - The elevator moves while driving (no extra time); a robot holds up to 1 coral + 1 algae.
  - Not modelled: robots blocking each other on the way, defense, AUTO (the reef starts
    empty), the endgame.
"""
from __future__ import annotations

import hashlib
import heapq
import math
import random
from dataclasses import dataclass
from statistics import NormalDist

from . import rules

IN = 0.0254
FIELD_WIDTH = 8.052   # m, from the same layout file

# (x m, y m, yaw deg) of the blue-side tags used here, copied from the layout file.
TAGS = {
    12: (0.851154, 0.65532, 54.0),                              # coral station, processor side
    13: (0.851154, 7.3964799999999995, 306.0),                  # coral station
    14: (8.272272, 6.137656, 180.0),                            # barge, facing blue
    16: (5.9875419999999995, -0.0038099999999999996, 90.0),     # processor
    17: (4.073905999999999, 3.3063179999999996, 240.0),         # reef faces 17-22
    18: (3.6576, 4.0259, 180.0),
    19: (4.073905999999999, 4.745482, 120.0),
    20: (4.904739999999999, 4.745482, 60.0),
    21: (5.321046, 4.0259, 0.0),
    22: (4.904739999999999, 3.3063179999999996, 300.0),
}
TAG = {k: (x, y, math.radians(d)) for k, (x, y, d) in TAGS.items()}

CENTER = (176.746 * IN, FIELD_WIDTH / 2)
FACES = (18, 19, 20, 21, 22, 17)                  # 6328 order: heading 180 - 60k from the centre
FACE_NAME = {18: "AB", 17: "CD", 22: "EF", 21: "GH", 20: "IJ", 19: "KL"}
HIGH_ALGAE_FACES = frozenset({18, 20, 22})
LOW_ALGAE_FACES = frozenset({19, 21, 17})
BLOCKS = {f: rules.ALGAE_BLOCKING["B"]["high" if f in HIGH_ALGAE_FACES else "low"] for f in FACES}
APOTHEM = sum(math.hypot(TAG[f][0] - CENTER[0], TAG[f][1] - CENTER[1]) for f in FACES) / 6
STATIONS = (12, 13)
LEVELS = (2, 3, 4)
SLOTS = [(f, side, lv) for f in FACES for side in (-1, 1) for lv in LEVELS]   # 36 branches
CORAL_MARKS = [(48 * IN, FIELD_WIDTH / 2 + dy * IN) for dy in (-72, 0, 72)]  # floor algae
START = [(17, 1), (18, 1), (19, 1)]              # robots start at CD / AB / KL (after AUTO)


@dataclass(frozen=True)
class RobotParams:
    """Seconds and metres. vmax .. t_place were given by the user; the rest are placeholders."""
    name: str
    vmax: float = 4.0
    acc: float = 5.0
    t_intake: float = 1.0
    t_place: tuple = (0.0, 0.0, 0.7, 0.7, 1.0)   # index = level
    t_rm: float = 0.8          # remove one staged algae
    t_proc: float = 0.5        # score one algae in the processor or the net
    t_align: float = 0.0       # extra per stop, at the station and at the reef
    half: float = 0.45         # robot centre to bumper edge
    slide: float = 0.0         # intake spot may move +-slide along the 1.93 m station opening (manual 5.6.2)


USER = RobotParams("user (v 4, a 5, intake 1.0, L2/L3 0.7, L4 1.0)")
SLOWER = RobotParams("slower (intake 1.5, L2/L3 1.0, L4 1.3, algae 1.2, +0.4 s per stop)",
                     t_intake=1.5, t_place=(0, 0, 1.0, 1.0, 1.3), t_rm=1.2, t_proc=0.8, t_align=0.4)
TACTIC_ZONES = {0: {17, 22}, 1: {18, 21}, 2: {19, 20}}   # CD+EF / AB+GH / IJ+KL


def leg(d, p):
    """Rest-to-rest time over distance d: triangular profile if vmax is never reached."""
    return 2 * math.sqrt(d / p.acc) if d <= p.vmax ** 2 / p.acc else d / p.vmax + p.vmax / p.acc


def spots(p):
    """Where a robot may stand to intake: station centres, or 3 spots per station if slide > 0."""
    return list(STATIONS) if p.slide <= 0 else [(s, k) for s in STATIONS for k in (-1, 0, 1)]


def sid(s):
    """Station id of an intake spot."""
    return s if isinstance(s, int) else s[0]


def _starts(n_robots, starts):
    if starts is not None:
        return list(starts)
    if n_robots > len(START):
        raise ValueError(f"pass `starts` for more than {len(START)} robots")
    return START[:n_robots]


class Field:
    """Poses and obstacle-aware path lengths for one RobotParams (the robot size matters)."""

    def __init__(self, p):
        self.p = p
        h = p.half
        self.a_in = APOTHEM + h - 1e-3
        rv = self.a_in / math.cos(math.pi / 6) + 1e-3
        self.normals = [TAG[f][2] for f in FACES]
        self.verts = []
        for f in FACES:
            for s in (-1, 1):
                ang = TAG[f][2] + s * math.pi / 6
                self.verts.append((CENTER[0] + rv * math.cos(ang), CENTER[1] + rv * math.sin(ang)))
        self.pose = {}
        for f in FACES:
            th = math.radians(180 - 60 * FACES.index(f))
            for side in (-1, 1):
                lat, r = 6.469 * IN * side, APOTHEM + h
                self.pose[(f, side)] = (CENTER[0] + r * math.cos(th) - lat * math.sin(th),
                                        CENTER[1] + r * math.sin(th) + lat * math.cos(th))
        for s in STATIONS + (16,):
            x, y, yaw = TAG[s]
            self.pose[s] = (x + h * math.cos(yaw), y + h * math.sin(yaw))
        self.pose["PROC"] = self.pose[16]
        # Net shot spot in front of barge tag 14. The reef and stations are mirror-symmetric
        # about the field midline, so tag 14 vs 15 gives the same numbers.
        self.pose["NET"] = (TAG[14][0] - h - 0.3, TAG[14][1])
        for s in STATIONS:
            x, y = self.pose[s]
            tan = TAG[s][2] + math.pi / 2
            for k in (-1, 0, 1):
                self.pose[(s, k)] = (x + k * p.slide * math.cos(tan), y + k * p.slide * math.sin(tan))
        self._len = {}

    def _inside(self, q):
        return all((q[0] - CENTER[0]) * math.cos(n) + (q[1] - CENTER[1]) * math.sin(n) < self.a_in - 1e-3
                   for n in self.normals)

    def _ok(self, a, b, n=120):
        return not any(self._inside((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n))
                       for k in range(1, n))

    def _dijkstra(self, u, v):
        a, b = self.pose[u], self.pose[v]
        nodes = [a, b] + self.verts
        dist, prev, pq, done = {0: 0.0}, {}, [(0.0, 0)], set()
        while pq:
            d, i = heapq.heappop(pq)
            if i in done:
                continue
            if i == 1:
                pts, k = [nodes[1]], 1
                while k != 0:
                    k = prev[k]
                    pts.append(nodes[k])
                return d, pts[::-1]
            done.add(i)
            for j in range(len(nodes)):
                if j not in done and j != i and self._ok(nodes[i], nodes[j]):
                    nd = d + math.dist(nodes[i], nodes[j])
                    if nd < dist.get(j, 1e18):
                        dist[j], prev[j] = nd, i
                        heapq.heappush(pq, (nd, j))
        return float("inf"), []

    def length(self, u, v):
        key = (u, v) if str(u) <= str(v) else (v, u)
        if key not in self._len:
            self._len[key] = self._dijkstra(u, v)[0]
        return self._len[key]

    def path(self, u, v):
        """Waypoints of the shortest path (for drawing)."""
        return self._dijkstra(u, v)[1]

    def t(self, u, v):
        return leg(self.length(u, v), self.p) if u != v else 0.0


class _FieldCache(dict):
    def __missing__(self, p):
        self[p] = Field(p)
        return self[p]


FIELD = _FieldCache()


# ------------------------------------------------------------------ noise (common random numbers)
def _u(*key):
    h = hashlib.blake2b(repr(key).encode(), digest_size=8).digest()
    return (int.from_bytes(h, "big") + 0.5) / 2 ** 64


def _lognorm(mean, cv, u):
    if cv <= 0:
        return mean
    s2 = math.log(1 + cv * cv)
    return math.exp(math.log(mean) - s2 / 2 + math.sqrt(s2) * NormalDist().inv_cdf(u))


@dataclass(frozen=True)
class Noise:
    """run = -1: deterministic. Otherwise every duration of robot r's n-th trip is drawn from
    (run, r, n, kind), so every policy sees the same luck on its n-th trip (CRN)."""
    run: int = -1
    cv_service: float = 0.25
    cv_drive: float = 0.08
    p_miss: float = 0.03


# What happens to a staged algae once removed. "floor": knocked off. The others hold it and
# score it before the robot's next intake (or right after its last placement): PROC =
# processor, NET = net.
ALGAE_POLICIES = {
    "floor": "knock to the floor",
    "proc_cdef": "CD and EF algae -> processor, the other 4 -> net",
    "proc2net": "first 2 removed -> processor, the rest -> net",
    "proc2": "first 2 removed -> processor, the rest -> floor",
    "proc": "all 6 -> processor",
    "net": "all 6 -> net",
}


def _algae_dest(policy, face, held):
    first = held < rules.COOP_MIN_PROCESSED_EACH
    return {"proc": "PROC", "net": "NET", "proc2": "PROC" if first else None,
            "proc2net": "PROC" if first else "NET",
            "proc_cdef": "PROC" if face in (17, 22) else "NET"}.get(policy)


def simulate(p, n_robots, chooser, policy="floor", noise=Noise(), starts=None, log=None, trace=None):
    """Discrete-event alliance fill. Returns (time the last of the 36 branches is filled, stats).

    chooser(state) -> (slot, intake spot) or None. log, if a list, gets one tuple per
    placement: (robot, arrival, start, end, spot, slot, note). trace, if a list, gets one
    tuple per use of a station or the processor: (resource, robot, arrival, start, end).
    A robot with nothing to do waits until someone misses a placement (the slot reopens)."""
    F = FIELD[p]
    pos = _starts(n_robots, starts)
    hold = [None] * n_robots              # None, "PROC" or "NET": the algae it carries
    filled, reserved = set(), set()
    algae = {f: True for f in FACES}
    st_free = {s: 0.0 for s in STATIONS}
    face_free = {f: 0.0 for f in FACES}
    heading = {}                          # face -> robots on their way there
    idle = set()
    proc_free = 0.0
    last_end = 0.0
    stats = {"floor": 0, "proc": 0, "net": 0, "held": 0, "wait": 0.0, "misses": 0}
    count = [0] * n_robots
    ev = [(0.0, r, "decide", None) for r in range(n_robots)]
    heapq.heapify(ev)
    t_fill = None

    def dur(base, r, kind, drive=False):
        if noise.run < 0:
            return base
        cv = noise.cv_drive if drive else noise.cv_service
        return _lognorm(base, cv, _u(noise.run, r, count[r], kind)) if base > 0 else 0.0

    while ev:
        t, r, kind, data = heapq.heappop(ev)
        if kind == "decide":
            choice = None
            if len(filled) < len(SLOTS):
                choice = chooser(dict(p=p, F=F, t=t, r=r, pos=pos[r], filled=filled, reserved=reserved,
                                      algae=algae, st_free=st_free, face_free=face_free, heading=heading,
                                      hold=hold[r], policy=policy))
            if choice is None and not hold[r]:
                idle.add(r)
                continue
            count[r] += 1
            if choice is not None:
                slot = choice[0]
                reserved.add(slot)
                heading.setdefault(slot[0], set()).add(r)
            if hold[r]:                   # score the algae it carries first
                arr = t + dur(F.t(pos[r], hold[r]), r, "d0", True)
                heapq.heappush(ev, (arr, r, "at_algae", choice))
            else:
                slot, s = choice
                heapq.heappush(ev, (t + dur(F.t(pos[r], s), r, "d1", True), r, "at_station", choice))
        elif kind == "at_algae":
            dest = hold[r]
            start = max(t, proc_free) if dest == "PROC" else t
            stats["wait"] += start - t
            end = start + dur(p.t_proc, r, "proc" if dest == "PROC" else "net")
            if dest == "PROC":
                proc_free = end
                stats["proc"] += 1
                if trace is not None:
                    trace.append(("processor", r, t, start, end))
            else:
                stats["net"] += 1
            hold[r], pos[r] = None, dest
            if data is None:              # nothing left to place: look for work again
                heapq.heappush(ev, (end, r, "decide", None))
            else:
                slot, s = data
                heapq.heappush(ev, (end + dur(F.t(dest, s), r, "d1", True), r, "at_station", data))
        elif kind == "at_station":
            slot, s = data
            start = max(t, st_free[sid(s)])
            stats["wait"] += start - t
            end = start + dur(p.t_intake + p.t_align, r, "intake")
            st_free[sid(s)] = end
            if trace is not None:
                trace.append((f"station {sid(s)}", r, t, start, end))
            heapq.heappush(ev, (end + dur(F.t(s, slot[:2]), r, "d2", True), r, "at_face", (slot, s)))
        else:
            slot, s = data
            f, side, lv = slot
            start = max(t, face_free[f])
            stats["wait"] += start - t
            tt = start
            note = ""
            if lv in BLOCKS[f] and algae[f]:
                tt += dur(p.t_rm, r, "rm")
                algae[f] = False
                dest = _algae_dest(policy, f, stats["held"])
                if dest and not hold[r]:
                    hold[r] = dest
                    stats["held"] += 1
                    note = f" +algae->{dest}"
                else:
                    stats["floor"] += 1
                    note = " +algae(floor)"
            tt += dur(p.t_place[lv] + p.t_align, r, "place")
            face_free[f] = tt
            heading.get(f, set()).discard(r)
            reserved.discard(slot)
            pos[r] = (f, side)
            missed = noise.run >= 0 and _u(noise.run, r, count[r], "miss") < noise.p_miss
            if missed:
                stats["misses"] += 1
                for q in idle:            # the slot is open again: wake everyone waiting
                    heapq.heappush(ev, (tt, q, "decide", None))
                idle.clear()
            else:
                filled.add(slot)
                last_end = max(last_end, tt)
                if len(filled) == len(SLOTS):
                    t_fill = last_end
            if log is not None:
                log.append((r, t, start, tt, s, slot, note + (" MISS" if missed else "")))
            heapq.heappush(ev, (tt, r, "decide", None))
    return t_fill, stats


# ------------------------------------------------------------------ choosers
def est(st, slot, s):
    """When this robot would finish placing `slot` if it went via intake spot s now."""
    p, F, t, here = st["p"], st["F"], st["t"], st["pos"]
    if st["hold"]:
        t += F.t(here, st["hold"]) + p.t_proc
        here = st["hold"]
    arr = t + F.t(here, s)
    start = max(arr, st["st_free"][sid(s)]) + p.t_intake + p.t_align
    arr_f = start + F.t(s, slot[:2])
    f = slot[0]
    arr_f = max(arr_f, st["face_free"][f])
    extra = p.t_rm if (slot[2] in BLOCKS[f] and st["algae"][f]) else 0.0
    return arr_f + extra + p.t_place[slot[2]] + p.t_align


def open_slots(st, allowed=None):
    """Unfilled, unreserved slots on faces no other robot is heading to."""
    return [sl for sl in SLOTS if sl not in st["filled"] and sl not in st["reserved"]
            and (allowed is None or sl[0] in allowed)
            and st["heading"].get(sl[0], set()) <= {st["r"]}]


def greedy(st, allowed=None):
    """Reactive: the slot and intake spot that finish soonest. Prefers `allowed` faces, then
    any face no other robot is heading to, then any open slot."""
    cands = (open_slots(st, allowed) or (open_slots(st) if allowed is not None else [])
             or [sl for sl in SLOTS if sl not in st["filled"] and sl not in st["reserved"]])
    if not cands:
        return None
    return min(((est(st, sl, s), sl, s) for sl in cands for s in spots(st["p"])))[1:]


def zone_chooser(zones):
    """Each robot owns some faces and fills them soonest-first; helps the others when done."""
    def ch(st):
        return greedy(st, zones[st["r"]])
    return ch


def zone_level_chooser(zones):
    """Own faces only; highest level first (L4 -> L3 -> L2), then soonest finish; then help."""
    def ch(st):
        cands = open_slots(st, zones[st["r"]])
        if not cands:
            return greedy(st)
        top = max(sl[2] for sl in cands)
        return min(((est(st, sl, s), sl, s) for sl in cands if sl[2] == top for s in spots(st["p"])))[1:]
    return ch


def plan_chooser(plan):
    """Fixed per-robot slot order; intake spot picked at run time; missed slots retried first."""
    def ch(st):
        for sl in plan[st["r"]]:
            if sl not in st["filled"] and sl not in st["reserved"]:
                return min(((est(st, sl, s), sl, s) for s in spots(st["p"])))[1:]
        return greedy(st)
    return ch


def naive_chooser(station_of_robot):
    """No planning: each robot owns one station; everyone takes the next open slot in
    AB, CD, ..., KL order, L4 first."""
    order = [(f, s, lv) for lv in (4, 3, 2) for f in (18, 17, 22, 21, 20, 19) for s in (-1, 1)]

    def ch(st):
        for sl in order:
            if sl not in st["filled"] and sl not in st["reserved"]:
                return sl, station_of_robot[st["r"]]
        return None
    return ch


def lower_bound(p, n_robots, starts=None):
    """Total unavoidable work / n_robots: every coral needs an intake, a placement and the
    cheapest station->branch leg; every coral but each robot's last needs the way back;
    every algae needs removing. Ignores waiting and algae scoring trips."""
    F = FIELD[p]
    starts = _starts(n_robots, starts)
    a = {sl: min(F.t(s, sl[:2]) for s in spots(p)) for sl in SLOTS}
    work = sum(p.t_intake + p.t_align + p.t_place[sl[2]] + p.t_align + a[sl] for sl in SLOTS)
    work += sum(a.values()) - sum(sorted(a.values())[-n_robots:])
    work += sum(min(F.t(st, s) for s in spots(p)) for st in starts)
    work += len(FACES) * p.t_rm
    return work / n_robots


def anneal(p, n_robots, iters=6000, seed=1, init=None):
    """Simulated annealing over fixed per-robot slot orders (plan_chooser), deterministic sim."""
    rng = random.Random(seed)
    if init is None:
        init = [[] for _ in range(n_robots)]
        order = SLOTS[:]
        rng.shuffle(order)
        for i, sl in enumerate(order):
            init[i % n_robots].append(sl)
    cur = [lst[:] for lst in init]
    f_cur = simulate(p, n_robots, plan_chooser(cur))[0]
    best, f_best = [lst[:] for lst in cur], f_cur
    T0 = 2.0
    for it in range(iters):
        T = T0 * (1 - it / iters) + 1e-3
        cand = [lst[:] for lst in cur]
        m = rng.random()
        ra, rb = rng.randrange(n_robots), rng.randrange(n_robots)
        if m < 0.4 and cand[ra]:
            i = rng.randrange(len(cand[ra]))
            sl = cand[ra].pop(i)
            cand[rb].insert(rng.randrange(len(cand[rb]) + 1), sl)
        elif m < 0.8 and cand[ra] and cand[rb]:
            i, j = rng.randrange(len(cand[ra])), rng.randrange(len(cand[rb]))
            cand[ra][i], cand[rb][j] = cand[rb][j], cand[ra][i]
        elif len(cand[ra]) > 2:
            i, j = sorted(rng.sample(range(len(cand[ra])), 2))
            cand[ra][i:j + 1] = reversed(cand[ra][i:j + 1])
        f = simulate(p, n_robots, plan_chooser(cand))[0]
        if f is None:
            continue
        if f <= f_cur or rng.random() < math.exp((f_cur - f) / T):
            cur, f_cur = cand, f
            if f < f_best:
                best, f_best = [lst[:] for lst in cand], f
    return best, f_best
