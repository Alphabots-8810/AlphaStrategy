"""Robot capability profiles, field travel model, and discretised duration PMFs.

EVERYTHING in this file is a modelling assumption, not a rule. The default
profiles are UNCALIBRATED hand-set numbers meant to span "elite / mid / L1-bot"
2025 robots; replace them with scouting-derived distributions before trusting
absolute outputs. Relative comparisons and sensitivities are the intended use.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from statistics import NormalDist

# --- Locations ---------------------------------------------------------------
REEF, STATION, PROCESSOR, BARGE = 0, 1, 2, 3
LOC_NAMES = ("REEF", "STATION", "PROCESSOR", "BARGE")
N_LOCS = 4

# --- Macro actions -------------------------------------------------------------
INTAKE, L1, L2, L3, L4, REM_LOW, REM_HIGH, NET, PROC, FLOOR, CLIMB, PARK = range(12)
N_ACTIONS = 12
ACTION_NAMES = ("INTAKE", "L1", "L2", "L3", "L4", "REM_LOW", "REM_HIGH",
                "NET", "PROC", "FLOOR", "CLIMB", "PARK")
ACTION_DEST = (STATION, REEF, REEF, REEF, REEF, REEF, REEF,
               BARGE, PROCESSOR, REEF, BARGE, BARGE)
CORAL_ACTIONS = (L1, L2, L3, L4)
REEF_ACTIONS = frozenset((L1, L2, L3, L4, REM_LOW, REM_HIGH, FLOOR))
TERMINAL_ACTIONS = frozenset((CLIMB, PARK))

# Mean drive time (s) between locations for speed_factor = 1.0, including
# approach/alignment. Rough 2025 field geometry (17.5 m x 8.0 m, REEF ~4.5 m off
# the wall, stations in the corners, PROCESSOR on the side wall, NET at mid
# field). Same-location entries = repositioning (e.g. moving to another face).
_BASE_TRAVEL = {
    (REEF, REEF): 0.5, (REEF, STATION): 2.2, (REEF, PROCESSOR): 1.8, (REEF, BARGE): 2.0,
    (STATION, STATION): 0.3, (STATION, PROCESSOR): 3.0, (STATION, BARGE): 3.5,
    (PROCESSOR, PROCESSOR): 0.3, (PROCESSOR, BARGE): 3.0,
    (BARGE, BARGE): 0.3,
}


def base_travel(a: int, b: int) -> float:
    return _BASE_TRAVEL.get((a, b), _BASE_TRAVEL.get((b, a)))


@dataclass(frozen=True)
class Task:
    """Service time at the destination (lognormal mean/cv) and success prob."""
    mean: float
    cv: float = 0.2
    p: float = 1.0


@dataclass(frozen=True)
class AutoRoutine:
    """Pre-programmed AUTO, modelled as a sampled outcome (not optimised)."""
    leave_p: float = 0.95
    coral: tuple = ()          # ((level, p_success), ...) attempted in order
    end_loc: int = REEF        # where TELEOP starts


@dataclass(frozen=True)
class RobotProfile:
    name: str
    intake: Task
    score: dict                     # level -> Task; missing level = cannot score it
    speed_factor: float = 1.0       # multiplies base travel means
    travel_cv: float = 0.15
    remove_low: Task | None = None
    remove_high: Task | None = None
    hold_algae: bool = False        # keeps dislodged ALGAE (else it falls to the floor)
    hold_both: bool = False         # may carry 1 CORAL + 1 ALGAE at once (G409 limit)
    floor_algae: Task | None = None
    net: Task | None = None
    processor: Task | None = None
    climb: str | None = None        # "deep" | "shallow" | None
    climb_task: Task | None = None
    park_task: Task = field(default_factory=lambda: Task(0.5, 0.2, 1.0))
    auto: AutoRoutine = field(default_factory=AutoRoutine)

    def __post_init__(self):
        if self.climb not in (None, "deep", "shallow"):
            raise ValueError(f"climb must be None, 'deep' or 'shallow', got {self.climb!r}")
        if self.climb and self.climb_task is None:
            raise ValueError("climb is set but climb_task is None")

    def task(self, a: int) -> Task | None:
        if a == INTAKE:
            return self.intake
        if a in CORAL_ACTIONS:
            return self.score.get(a)
        return {REM_LOW: self.remove_low, REM_HIGH: self.remove_high,
                NET: self.net, PROC: self.processor, FLOOR: self.floor_algae,
                CLIMB: self.climb_task if self.climb else None,
                PARK: self.park_task}[a]

    def with_task(self, a: int, **changes) -> "RobotProfile":
        """Copy with one task's fields changed (for sensitivity sweeps)."""
        t = replace(self.task(a), **changes)
        if a == INTAKE:
            return replace(self, intake=t)
        if a in CORAL_ACTIONS:
            return replace(self, score={**self.score, a: t})
        key = {REM_LOW: "remove_low", REM_HIGH: "remove_high", NET: "net",
               PROC: "processor", FLOOR: "floor_algae", CLIMB: "climb_task",
               PARK: "park_task"}[a]
        return replace(self, **{key: t})


# --- Discretised duration PMFs ---------------------------------------------------
_STD_NORMAL = NormalDist()


def lognormal_atoms(mean: float, cv: float, k: int) -> list[float]:
    """k equal-probability atoms (quantile midpoints) of a lognormal."""
    if cv <= 0:
        return [mean] * k
    s2 = math.log(1.0 + cv * cv)
    mu = math.log(mean) - s2 / 2.0
    s = math.sqrt(s2)
    return [math.exp(mu + s * _STD_NORMAL.inv_cdf((i + 0.5) / k)) for i in range(k)]


@dataclass(frozen=True)
class DurationPMF:
    steps: tuple        # possible total durations in time steps (>= 1), ascending
    probs: tuple        # probabilities
    cum: tuple          # cumulative probabilities (for inverse-CDF sampling)
    service: int        # mean service steps at the destination (arrival = done - service)
    mean_steps: float   # E[steps]


def build_duration_table(profile: RobotProfile, dt: float, k: int) -> dict:
    """(from_loc, action) -> DurationPMF, for every action the robot can do.

    Total duration = travel(from -> dest) + service, modelled as ONE lognormal
    with the summed mean and combined std, then quantised to k atoms on the dt
    grid. The simulator and the DP both read this table, so they share exactly
    the same stochastic model.
    """
    table = {}
    for a in range(N_ACTIONS):
        task = profile.task(a)
        if task is None:
            continue
        for loc in range(N_LOCS):
            tr = base_travel(loc, ACTION_DEST[a]) * profile.speed_factor
            mean = tr + task.mean
            std = math.hypot(tr * profile.travel_cv, task.mean * task.cv)
            atoms = lognormal_atoms(mean, std / mean, k)
            merged: dict[int, float] = {}
            for x in atoms:
                st = max(1, int(round(x / dt)))
                merged[st] = merged.get(st, 0.0) + 1.0 / k
            steps = tuple(sorted(merged))
            probs = tuple(merged[s] for s in steps)
            cum, acc = [], 0.0
            for p in probs:
                acc += p
                cum.append(acc)
            cum[-1] = 1.0
            table[(loc, a)] = DurationPMF(steps, probs, tuple(cum),
                                          max(0, int(round(task.mean / dt))),
                                          sum(s * q for s, q in zip(steps, probs)))
    return table


# --- Default (UNCALIBRATED) profiles ---------------------------------------------
ELITE = RobotProfile(
    name="elite",
    intake=Task(0.8, 0.3, 0.97),
    score={L1: Task(0.9, 0.2, 0.97), L2: Task(1.0, 0.2, 0.96),
           L3: Task(1.2, 0.2, 0.95), L4: Task(1.5, 0.2, 0.94)},
    speed_factor=1.0,
    remove_low=Task(1.0, 0.25, 0.93), remove_high=Task(1.2, 0.25, 0.92),
    hold_algae=True, hold_both=True,
    floor_algae=Task(2.0, 0.3, 0.85),
    net=Task(1.5, 0.25, 0.85), processor=Task(1.0, 0.2, 0.97),
    climb="deep", climb_task=Task(6.0, 0.25, 0.90),
    auto=AutoRoutine(0.98, ((L4, 0.85), (L4, 0.85), (L4, 0.85)), REEF),
)

MID = RobotProfile(
    name="mid",
    intake=Task(1.5, 0.3, 0.92),
    score={L1: Task(1.2, 0.25, 0.95), L2: Task(1.8, 0.25, 0.88), L3: Task(2.2, 0.25, 0.85)},
    speed_factor=1.3,
    remove_low=Task(2.0, 0.3, 0.85), hold_algae=False, hold_both=False,
    climb="shallow", climb_task=Task(7.0, 0.3, 0.80),
    auto=AutoRoutine(0.95, ((L1, 0.9),), REEF),
)

LOW = RobotProfile(
    name="l1bot",
    intake=Task(2.0, 0.35, 0.90),
    score={L1: Task(1.5, 0.3, 0.90)},
    speed_factor=1.5,
    auto=AutoRoutine(0.90, ((L1, 0.6),), REEF),
)

ALGAE_BOT = RobotProfile(
    name="algae",
    intake=Task(1.2, 0.3, 0.93),
    score={L1: Task(1.0, 0.2, 0.95), L2: Task(1.4, 0.25, 0.92)},
    speed_factor=1.1,
    remove_low=Task(0.9, 0.25, 0.95), remove_high=Task(1.0, 0.25, 0.94),
    hold_algae=True, hold_both=False,
    floor_algae=Task(1.8, 0.3, 0.88),
    net=Task(1.2, 0.2, 0.90), processor=Task(0.8, 0.2, 0.98),
    climb="deep", climb_task=Task(6.5, 0.25, 0.85),
    auto=AutoRoutine(0.95, ((L1, 0.9),), REEF),
)

PROFILES = {p.name: p for p in (ELITE, MID, LOW, ALGAE_BOT)}
