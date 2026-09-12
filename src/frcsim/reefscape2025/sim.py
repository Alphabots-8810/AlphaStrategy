"""Event-driven REEFSCAPE 2025 match simulator (one alliance's TELEOP decisions).

Decision epochs are asynchronous: whenever a robot finishes its current macro
action it becomes the *actor* and picks its next one (semi-MDP). Time lives on
a dt grid and every duration comes from profiles.build_duration_table, so a
1-robot Match with floor_algae=False and auto=False is EXACTLY the model that
dp.py solves - that equivalence is what the validation relies on.

Coupling between alliance partners (what "sum of points/sec" misses):
  - 2 CORAL STATIONS, one robot served at a time each (queueing),
  - 1 PROCESSOR, one robot at a time,
  - REEF congestion: extra service time when partners are also at the REEF,
  - shared BRANCH capacity and shared staged-ALGAE state,
  - shared floor-ALGAE pool (knocked-off ALGAE).
The opponent alliance is an exogenous pre-sampled outcome (no defence in v0);
it interacts only through PROCESSOR -> HUMAN PLAYER net throws and Coopertition.

Randomness: a "world" Match draws every uniform from a counter-based hash of
(seed, robot, action, n-th use), so two policies replayed on the same seed see
the same luck for the same kind of task (common random numbers). A "planning"
clone (MCTS) uses its own random.Random instead, so the planner never peeks at
the world's future.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from . import rules
from .profiles import (ACTION_DEST, BARGE, CLIMB, CORAL_ACTIONS, FLOOR, INTAKE, L1,
                       L2, L3, L4, N_ACTIONS, NET, PARK, PROC, REEF, REEF_ACTIONS,
                       REM_HIGH, REM_LOW, build_duration_table)


@dataclass(frozen=True)
class GameConfig:
    event: str = "regular"            # "regular" (also DCMP) | "champs"
    quals: bool = True                # Coopertition + RP only exist in quals
    dt: float = 0.25                  # time grid (s)
    k: int = 5                        # atoms per duration PMF
    algae_blocking: str = "B"         # see rules.ALGAE_BLOCKING
    teleop_s: float = rules.TELEOP_S
    hp_net_p: float = 0.5             # our HP success per ALGAE the opponent processes
    opp_hp_net_p: float = 0.5         # their HP success per ALGAE we process
    reef_congestion_s: tuple = (0.0, 0.5, 1.75)  # extra s with 0 / 1 / 2+ partners at REEF (on the dt grid)
    floor_algae: bool = True          # knocked-off ALGAE can be re-collected
    mark_algae: int = rules.CORAL_MARK_ALGAE_PER_ALLIANCE  # floor ALGAE at TELEOP start
    auto: bool = True                 # sample AUTO outcomes; False = TELEOP only
    start_loc: int = REEF             # TELEOP start location when auto=False

    @property
    def n_steps(self) -> int:
        return int(round(self.teleop_s / self.dt))

    @property
    def thresholds(self) -> dict:
        return rules.THRESHOLDS[self.event]


_MASK = (1 << 64) - 1


def _mix(x: int) -> int:  # splitmix64 finaliser
    x = (x + 0x9E3779B97F4A7C15) & _MASK
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & _MASK
    return x ^ (x >> 31)


def uhash(seed: int, a: int, b: int, c: int) -> float:
    h = _mix(_mix(_mix(_mix(seed) ^ a) ^ b) ^ c)
    return (h >> 11) * (1.0 / (1 << 53))


# uniform-stream tags that are not action ids
_TAG_LEAVE, _TAG_AUTO_CORAL, _TAG_OUR_HP, _TAG_OPP_HP = 1000, 1001, 1002, 1003


class Match:
    __slots__ = ("cfg", "profiles", "tables", "N", "R", "seed", "rng", "opp",
                 "loc", "hc", "ha", "busy", "done", "dest", "nact",
                 "n", "low", "high", "floor", "station_free", "proc_free", "supply",
                 "processed", "net_scored", "pts_auto", "pts_teleop", "barge",
                 "leave_all", "auto_coral", "_cong", "_blk_low", "_blk_high")

    def __init__(self, cfg: GameConfig, profiles, tables=None, seed: int = 0,
                 opp=None, rng: random.Random | None = None):
        self.cfg = cfg
        self.profiles = tuple(profiles)
        self.tables = tables if tables is not None else tuple(
            build_duration_table(p, cfg.dt, cfg.k) for p in self.profiles)
        self.N = cfg.n_steps
        self.R = R = len(self.profiles)
        self.seed = seed
        self.rng = rng
        self.opp = opp                      # (opp_raw_points, opp_processed) or None
        self.loc = [p.auto.end_loc if cfg.auto else cfg.start_loc for p in self.profiles]
        self.hc = [0] * R
        self.ha = [0] * R
        self.busy = [0] * R
        self.done = [False] * R
        self.dest = [-1] * R
        self.nact = [[0] * N_ACTIONS for _ in range(R)]
        self.n = [0, 0, 0, 0, 0]            # CORAL scored per level (index 1..4)
        self.low = rules.LOW_ALGAE_PER_REEF
        self.high = rules.HIGH_ALGAE_PER_REEF
        self.floor = cfg.mark_algae if cfg.floor_algae else 0
        self.station_free = [0] * rules.CORAL_STATIONS_PER_ALLIANCE
        self.proc_free = 0
        self.supply = rules.CORAL_SUPPLY_PER_ALLIANCE
        self.processed = 0
        self.net_scored = 0
        self.pts_auto = 0
        self.pts_teleop = 0
        self.barge = 0
        self.leave_all = cfg.auto
        self.auto_coral = 0
        blk = rules.ALGAE_BLOCKING[cfg.algae_blocking]
        self._blk_low = tuple(1 if L in blk["low"] else 0 for L in range(5))
        self._blk_high = tuple(1 if L in blk["high"] else 0 for L in range(5))
        self._cong = tuple(int(round(s / cfg.dt)) for s in cfg.reef_congestion_s)
        if cfg.auto:
            self._run_auto()

    # ---------------------------------------------------------------- helpers
    def clone(self, rng: random.Random | None = None, opp=None) -> "Match":
        m = object.__new__(Match)
        for s in ("cfg", "profiles", "tables", "N", "R", "seed", "low", "high",
                  "floor", "proc_free", "supply", "processed", "net_scored",
                  "pts_auto", "pts_teleop", "barge", "leave_all", "auto_coral",
                  "_cong", "_blk_low", "_blk_high"):
            setattr(m, s, getattr(self, s))
        m.rng = rng if rng is not None else self.rng
        m.opp = opp if opp is not None else self.opp
        m.loc, m.hc, m.ha = self.loc[:], self.hc[:], self.ha[:]
        m.busy, m.done, m.dest = self.busy[:], self.done[:], self.dest[:]
        m.nact = [row[:] for row in self.nact]
        m.n = self.n[:]
        m.station_free = self.station_free[:]
        return m

    def _u(self, a: int, b: int, c: int) -> float:
        return self.rng.random() if self.rng is not None else uhash(self.seed, a, b, c)

    def cap(self, level: int) -> int:
        """Branches on `level` not currently blocked by staged ALGAE (L2-L4)."""
        return rules.BRANCHES_PER_LEVEL - rules.BRANCHES_PER_FACE_PER_LEVEL * (
            self.low * self._blk_low[level] + self.high * self._blk_high[level])

    def can_score(self, level: int) -> bool:
        return level == L1 or self.n[level] < self.cap(level)

    def _run_auto(self) -> None:
        pts = rules.CORAL_PTS["auto"]
        for r, p in enumerate(self.profiles):
            if self._u(r, _TAG_LEAVE, 0) < p.auto.leave_p:
                self.pts_auto += rules.LEAVE_PTS
            else:
                self.leave_all = False
            for j, (level, ps) in enumerate(p.auto.coral):
                if self._u(r, _TAG_AUTO_CORAL, j) < ps and self.can_score(level):
                    self.n[level] += 1
                    self.pts_auto += pts[level]
                    self.auto_coral += 1

    # ------------------------------------------------------- decision process
    def actor(self) -> int:
        """Robot whose next decision comes first (-1 = match over)."""
        best, bt = -1, self.N
        for r in range(self.R):
            if not self.done[r] and self.busy[r] < bt:
                best, bt = r, self.busy[r]
        return best

    def terminal(self) -> bool:
        return self.actor() < 0

    def legal_actions(self, r: int) -> list:
        p = self.profiles[r]
        hc, ha = self.hc[r], self.ha[r]
        acts = []
        if not hc and (not ha or p.hold_both) and self.supply > 0:
            acts.append(INTAKE)
        if hc:
            for level in CORAL_ACTIONS:
                if level in p.score and self.can_score(level):
                    acts.append(level)
        free_hands = (not hc) or p.hold_both
        if free_hands and not (p.hold_algae and ha):
            if p.remove_low is not None and self.low > 0:
                acts.append(REM_LOW)
            if p.remove_high is not None and self.high > 0:
                acts.append(REM_HIGH)
        if ha:
            if p.net is not None:
                acts.append(NET)
            if p.processor is not None:
                acts.append(PROC)
        if (self.cfg.floor_algae and p.floor_algae is not None and p.hold_algae
                and self.floor > 0 and not ha and free_hands):
            acts.append(FLOOR)
        if p.climb:
            acts.append(CLIMB)
        acts.append(PARK)
        return acts

    def step(self, a: int) -> None:
        """Current actor performs macro action `a` (outcome sampled)."""
        r = self.actor()
        pmf = self.tables[r][(self.loc[r], a)]
        j = self.nact[r][a]
        self.nact[r][a] = j + 1
        u1 = self._u(r, a, 2 * j)
        u2 = self._u(r, a, 2 * j + 1)
        k = 0
        cum = pmf.cum
        while u1 >= cum[k]:
            k += 1
        self.apply(r, a, k, u2 < self.profiles[r].task(a).p)

    def apply(self, r: int, a: int, k: int, success: bool) -> None:
        """Deterministic transition: robot r does `a`, duration atom k, outcome."""
        p = self.profiles[r]
        pmf = self.tables[r][(self.loc[r], a)]
        t0 = self.busy[r]
        done_t = t0 + pmf.steps[k]
        # A robot cannot arrive before it departs (short-travel atoms can be < mean service).
        arrival = max(t0, done_t - pmf.service)
        if a == INTAKE:
            s = 0 if self.station_free[0] <= self.station_free[1] else 1
            if self.station_free[s] > arrival:
                done_t += self.station_free[s] - arrival
            self.station_free[s] = done_t
        elif a == PROC:
            if self.proc_free > arrival:
                done_t += self.proc_free - arrival
            self.proc_free = done_t
        elif a in REEF_ACTIONS and self.R > 1:
            others = 0                           # partners still busy at the REEF when we arrive
            for o in range(self.R):
                if (o != r and not self.done[o] and self.dest[o] == REEF
                        and self.busy[o] > arrival):
                    others += 1
            done_t += self._cong[min(others, len(self._cong) - 1)]
        N = self.N
        if a == CLIMB:
            self.done[r] = True
            if done_t <= N and success:
                self.barge += rules.CAGE_PTS[p.climb]
            elif done_t - pmf.service <= N:     # reached the BARGE ZONE: failed climb = PARK
                self.barge += rules.PARK_PTS
        elif a == PARK:                          # PARK = BUMPERS in the BARGE ZONE at 0:00,
            self.done[r] = True                  # so arriving is enough (same as a failed CLIMB)
            if done_t - pmf.service <= N:
                self.barge += rules.PARK_PTS
        elif done_t <= N:                        # action must finish before 0:00
            if a == INTAKE:
                if success:
                    self.hc[r] = 1
                    self.supply -= 1
            elif a <= L4:
                self.hc[r] = 0
                if success:
                    self.n[a] += 1
                    self.pts_teleop += rules.CORAL_PTS["teleop"][a]
            elif a == REM_LOW or a == REM_HIGH:
                if success:
                    if a == REM_LOW:
                        self.low -= 1
                    else:
                        self.high -= 1
                    if p.hold_algae:
                        self.ha[r] = 1
                    elif self.cfg.floor_algae:
                        self.floor += 1
            elif a == NET:
                self.ha[r] = 0
                if success:
                    self.pts_teleop += rules.NET_PTS
                    self.net_scored += 1
            elif a == PROC:
                self.ha[r] = 0
                if success:
                    self.pts_teleop += rules.PROCESSOR_PTS
                    self.processed += 1
            elif a == FLOOR:
                if success:
                    self.floor -= 1
                    self.ha[r] = 1
        self.busy[r] = done_t
        self.loc[r] = ACTION_DEST[a]
        self.dest[r] = ACTION_DEST[a]

    def key(self) -> tuple:
        """Hashable decision-relevant state (excludes RNG and opponent sample)."""
        return (tuple(self.loc), tuple(self.hc), tuple(self.ha), tuple(self.busy),
                tuple(self.done), tuple(self.dest), tuple(self.n), self.low, self.high,
                self.floor, tuple(self.station_free), self.proc_free, self.processed,
                self.pts_auto, self.pts_teleop, self.barge, self.leave_all,
                self.auto_coral, self.supply)

    # ---------------------------------------------------------------- scoring
    @property
    def raw_points(self) -> int:
        return self.pts_auto + self.pts_teleop + self.barge

    def result(self) -> dict:
        cfg = self.cfg
        opp_raw, opp_proc = self.opp if self.opp is not None else (0, 0)
        our_hp = sum(1 for i in range(opp_proc) if self._u(_TAG_OUR_HP, 0, i) < cfg.hp_net_p)
        opp_hp = sum(1 for i in range(self.processed)
                     if self._u(_TAG_OPP_HP, 0, i) < cfg.opp_hp_net_p)
        ours = self.raw_points + rules.NET_PTS * our_hp
        theirs = opp_raw + rules.NET_PTS * opp_hp
        coop = cfg.quals and self.processed >= rules.COOP_MIN_PROCESSED_EACH \
            and opp_proc >= rules.COOP_MIN_PROCESSED_EACH
        thr = cfg.thresholds
        levels_ok = sum(1 for lv in (1, 2, 3, 4) if self.n[lv] >= thr["coral_per_level"])
        # Ranking Points exist only in Qualification MATCHES (manual §10.5 / §5.6.1).
        coral_rp = cfg.quals and levels_ok >= (
            rules.CORAL_RP_LEVELS_COOP if coop else rules.CORAL_RP_LEVELS)
        barge_rp = cfg.quals and self.barge >= thr["barge_pts"]
        auto_rp = cfg.quals and self.leave_all and self.auto_coral >= 1
        has_opp = self.opp is not None
        win = has_opp and ours > theirs
        tie = has_opp and ours == theirs
        rp = (rules.RP_WIN * win + rules.RP_TIE * tie + rules.RP_AUTO * auto_rp
              + rules.RP_CORAL * coral_rp + rules.RP_BARGE * barge_rp) if cfg.quals else 0
        return {"points": ours, "opp_points": theirs, "margin": ours - theirs,
                "teleop": self.pts_teleop + self.barge,
                "win": 1.0 if win else (0.5 if tie else 0.0), "rp": rp,
                "coop": coop, "coral_rp": coral_rp, "barge_rp": barge_rp, "auto_rp": auto_rp,
                "processed": self.processed, "net": self.net_scored,
                "levels": tuple(self.n[1:]), "barge_pts": self.barge,
                "algae_left": self.low + self.high}

    def value(self, objective: str) -> float:
        if objective == "teleop":           # no HP draws: this is what the DP maximises
            return float(self.pts_teleop + self.barge)
        return float(self.result()[objective])


def play(m: Match, policies) -> Match:
    """Run a match to the end. `policies` = one callable or a list per robot."""
    per_robot = isinstance(policies, (list, tuple))
    while True:
        r = m.actor()
        if r < 0:
            return m
        pol = policies[r] if per_robot else policies
        m.step(pol(m, r))


class OpponentBank:
    """Pre-sampled opponent-alliance outcomes: (raw points, ALGAE processed).

    v0 has no defence, so the opponent only couples to us through PROCESSOR ->
    HUMAN PLAYER throws and Coopertition; both depend only on these two numbers.
    """

    def __init__(self, cfg: GameConfig, profiles, policy, n: int = 512, seed0: int = 7_000_000):
        tables = tuple(build_duration_table(p, cfg.dt, cfg.k) for p in profiles)
        self.outcomes = []
        for i in range(n):
            m = play(Match(cfg, profiles, tables, seed=seed0 + i), policy)
            self.outcomes.append((m.raw_points, m.processed))

    def __len__(self) -> int:
        return len(self.outcomes)

    def __getitem__(self, i: int) -> tuple:
        return self.outcomes[i % len(self.outcomes)]

    def sample(self, rng: random.Random) -> tuple:
        return self.outcomes[rng.randrange(len(self.outcomes))]
