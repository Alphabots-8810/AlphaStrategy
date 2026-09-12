import random

import pytest

from frcsim.reefscape2025 import profiles as P
from frcsim.reefscape2025 import rules
from frcsim.reefscape2025.policies import Greedy, rp_seeker
from frcsim.reefscape2025.sim import GameConfig, Match, play

ALLIANCE = [P.ELITE, P.MID, P.LOW]
TELEOP = rules.CORAL_PTS["teleop"]


def _random_policy(seed):
    rng = random.Random(seed)
    return lambda m, r: rng.choice(m.legal_actions(r))


@pytest.mark.parametrize("blocking", ["A", "B"])
@pytest.mark.parametrize("seed", range(40))
def test_invariants_random_play(seed, blocking):
    cfg = GameConfig(algae_blocking=blocking)
    m = Match(cfg, ALLIANCE + [P.ALGAE_BOT][: seed % 2], seed=seed, opp=(80, 2))
    auto_n = m.n[:]
    pol = _random_policy(seed)
    last_busy = m.busy[:]
    while (r := m.actor()) >= 0:
        assert m.busy[r] == min(b for b, d in zip(m.busy, m.done) if not d)
        m.step(pol(m, r))
        for lv in (2, 3, 4):
            assert 0 <= m.n[lv] <= m.cap(lv) <= rules.BRANCHES_PER_LEVEL
        assert all(h in (0, 1) for h in m.hc + m.ha)
        assert 0 <= m.low <= 3 and 0 <= m.high <= 3 and m.floor >= 0 and m.supply >= 0
        assert all(b >= lb for b, lb in zip(m.busy, last_busy))
        last_busy = m.busy[:]
    coral_pts = sum(TELEOP[lv] * (m.n[lv] - auto_n[lv]) for lv in (1, 2, 3, 4))
    assert m.pts_teleop == coral_pts + rules.NET_PTS * m.net_scored \
        + rules.PROCESSOR_PTS * m.processed
    assert m.barge <= sum(rules.CAGE_PTS.get(p.climb, rules.PARK_PTS) if p.climb
                          else rules.PARK_PTS for p in m.profiles)


def test_crn_determinism():
    cfg = GameConfig()
    a = play(Match(cfg, ALLIANCE, seed=123, opp=(90, 3)), Greedy()).result()
    b = play(Match(cfg, ALLIANCE, seed=123, opp=(90, 3)), Greedy()).result()
    assert a == b


def test_planning_clone_does_not_touch_world():
    cfg = GameConfig()
    m = Match(cfg, ALLIANCE, seed=5, opp=(90, 3))
    before = m.key()
    c = m.clone(rng=random.Random(0))
    play(c, rp_seeker())
    assert m.key() == before and c.terminal()


def test_teleop_only_start_state():
    cfg = GameConfig(auto=False)
    m = Match(cfg, [P.ELITE], seed=0)
    assert m.pts_auto == 0 and m.n == [0, 0, 0, 0, 0] and not m.leave_all


def test_blocking_readings_initial_capacity():
    a = Match(GameConfig(auto=False, algae_blocking="A"), [P.ELITE])
    b = Match(GameConfig(auto=False, algae_blocking="B"), [P.ELITE])
    assert (a.cap(2), a.cap(3), a.cap(4)) == (6, 6, 12)
    assert (b.cap(2), b.cap(3), b.cap(4)) == (6, 0, 12)
    b.low = 0
    assert (b.cap(2), b.cap(3)) == (12, 6)


def _scored(cfg, n, processed=0, opp_proc=0, barge=0, leave=True, auto_coral=1):
    m = Match(cfg, [P.ELITE], seed=0, opp=(0, opp_proc))
    m.n = [0] + list(n)
    m.processed, m.barge, m.leave_all, m.auto_coral = processed, barge, leave, auto_coral
    return m.result()


def test_coral_rp_and_coop():
    reg = GameConfig(event="regular", hp_net_p=0.0, opp_hp_net_p=0.0)
    assert _scored(reg, (5, 5, 5, 5))["coral_rp"]
    assert not _scored(reg, (5, 5, 4, 5))["coral_rp"]
    # coop (both processed >= 2) lowers the requirement to 3 levels
    r = _scored(reg, (5, 5, 0, 5), processed=2, opp_proc=2)
    assert r["coop"] and r["coral_rp"]
    assert not _scored(reg, (5, 5, 0, 5), processed=2, opp_proc=1)["coop"]
    champs = GameConfig(event="champs", hp_net_p=0.0, opp_hp_net_p=0.0)
    assert not _scored(champs, (6, 7, 7, 7))["coral_rp"]
    assert _scored(champs, (7, 7, 7, 7))["coral_rp"]
    # playoffs: no coop
    assert not _scored(GameConfig(quals=False), (5, 5, 0, 5), processed=2, opp_proc=2)["coop"]


def test_barge_and_auto_rp():
    reg = GameConfig(event="regular")
    assert _scored(reg, (0, 0, 0, 0), barge=14)["barge_rp"]
    assert not _scored(reg, (0, 0, 0, 0), barge=13)["barge_rp"]
    assert not _scored(GameConfig(event="champs"), (0, 0, 0, 0), barge=14)["barge_rp"]
    assert _scored(reg, (0, 0, 0, 0), leave=True, auto_coral=1)["auto_rp"]
    assert not _scored(reg, (0, 0, 0, 0), leave=False, auto_coral=3)["auto_rp"]


def test_no_rp_in_playoffs():
    r = _scored(GameConfig(quals=False), (5, 5, 5, 5), barge=16)
    assert r["rp"] == 0 and not (r["coral_rp"] or r["barge_rp"] or r["auto_rp"])


def test_mark_algae_start_in_floor_pool():
    assert Match(GameConfig(), [P.ELITE]).floor == rules.CORAL_MARK_ALGAE_PER_ALLIANCE
    assert Match(GameConfig(floor_algae=False), [P.ELITE]).floor == 0


def test_planners_pickle_and_refuse_to_peek():
    import pickle
    from frcsim.reefscape2025.policies import MCTSPolicy, RolloutPolicy
    for pol in (RolloutPolicy("rp", n_scen=2), MCTSPolicy("rp", n_iter=5)):
        pickle.loads(pickle.dumps(pol))
        m = Match(GameConfig(), ALLIANCE, seed=0, opp=(100, 2))
        with pytest.raises(ValueError):
            pol(m, m.actor())


class _HopelessBank:
    """Opponent that always scores 1000: every scenario is a loss."""

    def sample(self, rng):
        rng.random()
        return (1000, 0)


def test_discrete_objective_ties_do_not_fall_back_to_list_order():
    from frcsim.reefscape2025.policies import Objective, RolloutPolicy
    cfg = GameConfig()
    for seed in range(6):
        m = Match(cfg, ALLIANCE, seed=seed, opp=(1000, 0))
        for _ in range(seed * 3):                 # advance to varied decision points
            m.step(Greedy("proc")(m, m.actor()))
        r = m.actor()
        win = RolloutPolicy("win", Greedy("proc"), n_scen=4, seed=1, opp_bank=_HopelessBank())(m, r)
        pts = RolloutPolicy("points", Greedy("proc"), n_scen=4, seed=1, opp_bank=_HopelessBank())(m, r)
        assert win == pts                         # all-loss ties are ordered by expected points
        base = Greedy("proc")(m, r)
        pure = RolloutPolicy("win", Greedy("proc"), n_scen=4, seed=1, opp_bank=_HopelessBank())
        pure.score = Objective("win", tiebreak=0.0)
        assert pure(m, r) == base                 # exact ties keep the base heuristic's action
        gated = RolloutPolicy("win", Greedy("proc"), n_scen=4, seed=1, opp_bank=_HopelessBank(),
                              min_z=1.0)(m, r)
        assert gated in (base, pts)               # gate: base, or a significant improvement


def test_congestion_only_counts_partners_still_at_reef():
    cfg = GameConfig(auto=False)
    pm = P.build_duration_table(P.ELITE, cfg.dt, cfg.k)[(P.STATION, P.L4)]
    arrival = pm.steps[0] - pm.service
    for partner_busy, extra in ((arrival, 0), (arrival + 1, cfg.reef_congestion_s[1])):
        m = Match(cfg, [P.ELITE, P.ELITE], seed=0)
        m.loc[0], m.hc[0] = P.STATION, 1
        m.dest[1], m.busy[1] = P.REEF, partner_busy
        m.apply(0, P.L4, 0, True)
        assert m.busy[0] == pm.steps[0] + int(round(extra / cfg.dt))


def test_lone_robot_never_waits_in_queue():
    cfg = GameConfig(auto=False)
    for prof in (P.MID, P.ALGAE_BOT, P.LOW):     # STATION->INTAKE atom 0 < mean service
        m = Match(cfg, [prof], seed=0)
        m.loc[0] = P.STATION
        pm = m.tables[0][(P.STATION, P.INTAKE)]
        m.apply(0, P.INTAKE, 0, True)
        assert m.busy[0] == pm.steps[0]


def test_park_scores_on_arrival():
    cfg = GameConfig(auto=False)
    m = Match(cfg, [P.LOW], seed=0)
    pm = m.tables[0][(P.REEF, P.PARK)]
    m.busy[0] = m.N - pm.steps[-1] + pm.service   # arrives exactly at 0:00, finishes after
    m.apply(0, P.PARK, len(pm.steps) - 1, True)
    assert m.barge == rules.PARK_PTS


def test_profile_validation():
    from dataclasses import replace
    with pytest.raises(ValueError):
        replace(P.ELITE, climb_task=None)
    with pytest.raises(ValueError):
        replace(P.ELITE, climb="medium")


def test_climb_semantics():
    cfg = GameConfig(auto=False, dt=0.5, k=3)
    m = Match(cfg, [P.ELITE], seed=0)
    m.loc[0] = P.BARGE
    pm = m.tables[0][(P.BARGE, P.CLIMB)]
    m.busy[0] = m.N - pm.steps[0]            # finishes exactly at 0:00
    m.apply(0, P.CLIMB, 0, True)
    assert m.barge == rules.DEEP_CAGE_PTS
    m2 = Match(cfg, [P.ELITE], seed=0)
    m2.loc[0] = P.BARGE
    m2.busy[0] = m2.N - pm.steps[0] + 1      # one step late, but reached the zone
    m2.apply(0, P.CLIMB, 0, True)
    assert m2.barge == rules.PARK_PTS
