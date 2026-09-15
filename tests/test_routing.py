"""Alliance routing model: geometry, kinematics, scheduler invariants, regression numbers."""
import math
import random

import pytest

from frcsim.reefscape2025 import routing as R
from frcsim.reefscape2025 import rules

U = R.USER
MIRROR = {17: 19, 19: 17, 22: 20, 20: 22, 18: 18, 21: 21}   # reflection about the field midline


def _random_plan(seed, n=3):
    order = R.SLOTS[:]
    random.Random(seed).shuffle(order)
    return [order[k::n] for k in range(n)]


CHOOSERS = {
    "greedy": lambda: R.greedy,
    "zone": lambda: R.zone_chooser(R.TACTIC_ZONES),
    "zone_level": lambda: R.zone_level_chooser(R.TACTIC_ZONES),
    "naive": lambda: R.naive_chooser({0: 12, 1: 13, 2: 12}),
    "plan": lambda: R.plan_chooser(_random_plan(7)),
}


def test_trapezoid_branches_agree_at_the_boundary():
    d = U.vmax ** 2 / U.acc
    assert R.leg(d, U) == pytest.approx(d / U.vmax + U.vmax / U.acc)
    assert R.leg(d, U) == pytest.approx(2 * math.sqrt(d / U.acc))
    assert R.leg(1.0, U) == pytest.approx(2 * math.sqrt(1 / 5))
    assert R.leg(10.0, U) == pytest.approx(10 / 4 + 4 / 5)


def test_algae_faces_and_blocking():
    assert len(R.HIGH_ALGAE_FACES) == rules.HIGH_ALGAE_PER_REEF
    assert len(R.LOW_ALGAE_FACES) == rules.LOW_ALGAE_PER_REEF
    assert [f in R.HIGH_ALGAE_FACES for f in R.FACES] == [True, False] * 3   # alternating
    assert len(R.SLOTS) == 3 * rules.BRANCHES_PER_LEVEL
    free = {lv: sum(1 for f, _, l in R.SLOTS if l == lv and lv not in R.BLOCKS[f]) for lv in R.LEVELS}
    assert free == {2: 6, 3: 0, 4: 12}   # same as the reading-B test in test_sim.py


def test_field_is_mirror_symmetric():
    F = R.FIELD[U]
    for f in R.FACES:
        for side in (-1, 1):
            assert F.length(12, (f, side)) == pytest.approx(F.length(13, (MIRROR[f], -side)), abs=2e-3)


def test_paths_go_around_the_reef():
    F = R.FIELD[U]
    for f in R.FACES:
        for s in R.STATIONS:
            assert F.length(s, (f, 1)) >= math.dist(F.pose[s], F.pose[(f, 1)]) - 1e-9
    straight = min(math.dist(F.pose[s], F.pose[(21, 1)]) for s in R.STATIONS)
    assert min(F.length(s, (21, 1)) for s in R.STATIONS) > straight + 0.3   # GH is behind the reef


def _check_run(t, stats, log, trace):
    placed = [e for e in log if "MISS" not in e[6]]
    assert sorted(e[5] for e in placed) == sorted(R.SLOTS)            # every branch once
    assert t == pytest.approx(max(e[3] for e in placed))              # fill = last placement done
    assert stats["proc"] + stats["net"] + stats["floor"] == len(R.FACES)
    assert stats["proc"] + stats["net"] == stats["held"]              # every held algae is scored
    for f in R.FACES:
        on_face = sorted((e for e in log if e[5][0] == f), key=lambda e: e[2])
        for a, b in zip(on_face, on_face[1:]):
            assert b[2] >= a[3] - 1e-9                               # one robot per face at a time
        blocked = [e for e in on_face if e[5][2] in R.BLOCKS[f]]
        assert "algae" in blocked[0][6]                              # algae removed first ...
        assert sum("algae" in e[6] for e in on_face) == 1            # ... exactly once
    for res in {x[0] for x in trace}:                                 # stations and the processor:
        uses = sorted((x for x in trace if x[0] == res), key=lambda x: (x[3], x[2]))
        for a, b in zip(uses, uses[1:]):
            assert b[3] >= a[4] - 1e-9                               # one robot at a time
            assert b[2] >= a[2] - 1e-9                               # served in order of arrival


@pytest.mark.parametrize("policy", list(R.ALGAE_POLICIES))
@pytest.mark.parametrize("chooser", list(CHOOSERS))
def test_fill_invariants(policy, chooser):
    for p in (R.USER, R.SLOWER, R.RobotParams("slide", slide=0.5)):
        for run in (-1, 0, 1, 2, 3, 4, 5):
            log, trace = [], []
            t, stats = R.simulate(p, 3, CHOOSERS[chooser](), policy=policy, noise=R.Noise(run=run),
                                  log=log, trace=trace)
            _check_run(t, stats, log, trace)


@pytest.mark.parametrize("n", [1, 2, 3])
def test_fewer_robots(n):
    for policy in ("floor", "proc", "proc_cdef"):
        for run in (-1, 0, 1, 2):
            log, trace = [], []
            t, stats = R.simulate(U, n, R.greedy, policy=policy, noise=R.Noise(run=run), log=log, trace=trace)
            _check_run(t, stats, log, trace)


def test_noise_is_reproducible_and_misses_are_retried():
    a = R.simulate(U, 3, R.greedy, noise=R.Noise(run=5))[0]
    assert a == R.simulate(U, 3, R.greedy, noise=R.Noise(run=5))[0]
    assert a != R.simulate(U, 3, R.greedy)[0]
    misses = 0
    for k in range(40):
        log, trace = [], []
        t, stats = R.simulate(U, 3, R.greedy, noise=R.Noise(run=k), log=log, trace=trace)
        _check_run(t, stats, log, trace)
        misses += stats["misses"]
    assert misses > 0


@pytest.mark.parametrize("n", [1, 2, 3])
def test_lower_bound_is_below_every_schedule(n):
    for p in (R.USER, R.SLOWER, R.RobotParams("slow removal", t_rm=10.0)):
        lb = R.lower_bound(p, n)
        assert lb <= R.simulate(p, n, R.greedy)[0] + 1e-9
        assert lb <= R.simulate(p, n, R.plan_chooser(_random_plan(3, n)))[0] + 1e-9
        if n == 3:
            for make in CHOOSERS.values():
                assert lb <= R.simulate(p, n, make())[0] + 1e-9
            assert lb <= R.anneal(p, n, iters=300, seed=1)[1] + 1e-9


def test_more_robots_need_starts():
    with pytest.raises(ValueError):
        R.lower_bound(U, 4)
    with pytest.raises(ValueError):
        R.simulate(U, 4, R.greedy)
    four = R.START + [(21, 1)]
    assert R.simulate(U, 4, R.greedy, starts=four)[0] >= R.lower_bound(U, 4, starts=four) - 1e-9


def test_regression_numbers():
    """Numbers quoted in the README (results/route_alliance.md)."""
    F = R.FIELD[U]
    near_far = {f: sorted(min(F.length(s, (f, side)) for s in R.STATIONS) for side in (-1, 1)) for f in R.FACES}
    order = (19, 17, 18, 20, 22, 21)   # KL, CD, AB, IJ, EF, GH
    assert [round(near_far[f][0], 2) for f in order] == [3.26, 3.26, 3.53, 4.28, 4.28, 5.76]
    assert [round(near_far[f][1], 2) for f in order] == [3.40, 3.40, 3.53, 4.61, 4.61, 5.76]
    assert [round(R.lower_bound(U, n), 1) for n in (1, 2, 3)] == [201.1, 100.3, 66.6]
    assert round(R.simulate(U, 3, R.greedy)[0], 1) == 71.4
    assert round(R.simulate(U, 3, R.zone_level_chooser(R.TACTIC_ZONES))[0], 1) == 71.1
    assert round(R.simulate(U, 3, R.zone_level_chooser(R.TACTIC_ZONES), policy="proc_cdef")[0], 1) == 76.0
    # processor queue is claimed on arrival (section 6 of results/route_alliance.md)
    assert round(R.simulate(U, 3, R.zone_level_chooser(R.TACTIC_ZONES), policy="proc2")[0], 1) == 71.8
    assert round(R.simulate(R.SLOWER, 3, R.zone_level_chooser(R.TACTIC_ZONES), policy="proc")[0], 1) == 97.6
