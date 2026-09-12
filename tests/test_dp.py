"""DP vs brute-force expectimax built on the simulator's own transition function.

The brute force enumerates every (duration atom, success) outcome through
Match.apply(), so agreement means the vectorised DP solves exactly the model the
simulator plays - not a re-derivation of it.
"""
import math

import pytest

from frcsim.reefscape2025 import dp
from frcsim.reefscape2025 import profiles as P
from frcsim.reefscape2025.sim import GameConfig, Match


def expectimax(m0: Match) -> float:
    memo = {}

    def V(m):
        r = m.actor()
        if r < 0:
            return 0.0
        key = m.key()
        if key in memo:
            return memo[key]
        best = -math.inf
        for a in m.legal_actions(r):
            pm = m.tables[r][(m.loc[r], a)]
            p = m.profiles[r].task(a).p
            q = 0.0
            for k, pr in enumerate(pm.probs):
                for succ, ps in ((True, p), (False, 1.0 - p)):
                    if ps <= 0.0:
                        continue
                    c = m.clone()
                    before = c.pts_teleop + c.barge
                    c.apply(r, a, k, succ)
                    q += pr * ps * (c.pts_teleop + c.barge - before + V(c))
            best = max(best, q)
        memo[key] = best
        return best

    return V(m0)


def _start(cfg, prof, **state):
    m = Match(cfg, [prof], seed=1)
    for k, v in state.items():
        if k in ("hc", "ha", "loc"):
            getattr(m, k)[0] = v
        elif k in ("n2", "n3", "n4"):
            m.n[int(k[1])] = v
        else:
            setattr(m, k, v)
    return m


CASES = [
    (P.ELITE, {}),
    (P.ELITE, {"hc": 1}),
    (P.ELITE, {"hc": 1, "ha": 1, "loc": P.STATION}),
    (P.ELITE, {"n4": 11, "hc": 1}),
    (P.ELITE, {"n4": 12, "hc": 1, "low": 1, "high": 0}),
    (P.ELITE, {"loc": P.BARGE, "ha": 1}),
    (P.MID, {}),
    (P.MID, {"hc": 1, "n2": 5, "low": 2}),
    (P.ALGAE_BOT, {}),
    (P.ALGAE_BOT, {"ha": 1, "loc": P.PROCESSOR}),
    (P.LOW, {"loc": P.STATION}),
]


@pytest.mark.parametrize("blocking", ["A", "B"])
@pytest.mark.parametrize("prof,state", CASES)
def test_dp_matches_expectimax(blocking, prof, state):
    cfg = GameConfig(dt=0.5, k=3, teleop_s=7.0, auto=False, floor_algae=False,
                     algae_blocking=blocking)
    res = dp.solve(prof, cfg)
    m = _start(cfg, prof, **state)
    exact = expectimax(m)
    assert res.V0[dp.encode_match(m)] == pytest.approx(exact, abs=1e-9)


@pytest.mark.parametrize("prof", [P.ELITE, P.MID])
def test_dp_ring_buffer_wraps(prof):
    """Horizon longer than the ring-buffer window, so every slot is reused."""
    cfg = GameConfig(dt=1.0, k=2, teleop_s=16.0, auto=False, floor_algae=False)
    res = dp.solve(prof, cfg)
    dmax = max(max(pm.steps) for pm in res.table.values())
    assert cfg.n_steps > dmax + 1
    for state in ({}, {"loc": P.STATION}):
        m = _start(cfg, prof, **state)
        assert res.V0[dp.encode_match(m)] == pytest.approx(expectimax(m), abs=1e-9)


def test_dp_endgame_climb_window():
    """Horizon barely longer than a climb: value must be driven by CLIMB/PARK."""
    cfg = GameConfig(dt=0.5, k=3, teleop_s=9.0, auto=False, floor_algae=False)
    res = dp.solve(P.ELITE, cfg)
    m = _start(cfg, P.ELITE, loc=P.BARGE)
    assert res.V0[dp.encode_match(m)] == pytest.approx(expectimax(m), abs=1e-9)


def test_dp_rejects_unmodelled_config():
    with pytest.raises(ValueError):
        dp.solve(P.ELITE, GameConfig(floor_algae=True, auto=False))
    with pytest.raises(ValueError):
        dp.solve(P.ELITE, GameConfig(floor_algae=False, auto=True))
