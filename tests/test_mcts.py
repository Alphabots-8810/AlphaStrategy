"""MCTS on tiny single-robot instances, checked against exact expectimax Q*.

Root edge means are averages of returns that include early exploration, so they
approach Q* from below and slowly; the executed policy only needs the argmax to
be (near-)optimal. We check both: decision quality, and convergence of the
chosen edge's mean toward its exact Q* as iterations grow.
"""
import pytest

from frcsim.mcts import MCTS
from frcsim.reefscape2025 import dp
from frcsim.reefscape2025 import profiles as P
from frcsim.reefscape2025.policies import Greedy
from frcsim.reefscape2025.sim import GameConfig, Match

from test_dp import expectimax


def exact_q(m):
    q = {}
    for a in m.legal_actions(0):
        pm = m.tables[0][(m.loc[0], a)]
        p = m.profiles[0].task(a).p
        tot = 0.0
        for k, pr in enumerate(pm.probs):
            for succ, ps in ((True, p), (False, 1.0 - p)):
                if ps > 0:
                    c = m.clone()
                    c.apply(0, a, k, succ)
                    tot += pr * ps * (c.pts_teleop + c.barge + expectimax(c))
        q[a] = tot
    return q


@pytest.mark.parametrize("prof,loc,hc", [(P.ELITE, P.REEF, 1), (P.ELITE, P.STATION, 0),
                                         (P.ALGAE_BOT, P.REEF, 0)])
def test_mcts_decision_and_convergence(prof, loc, hc):
    cfg = GameConfig(dt=0.5, k=3, teleop_s=8.0, auto=False, floor_algae=False)
    res = dp.solve(prof, cfg)
    m = Match(cfg, [prof], seed=0)
    m.loc[0], m.hc[0] = loc, hc
    v_star = float(res.V0[dp.encode_match(m)])
    q = exact_q(m)
    assert max(q.values()) == pytest.approx(v_star, abs=1e-9)
    # Measured (5 seeds x c in .3/.5/.7/1, heuristic-first expansion): >= 10k
    # iterations are near-optimal in every case; the STATION case settles on
    # REM_LOW, 0.26 (3.9% of V*) below INTAKE - mean-backup bias in a deep
    # stochastic subtree - so the criterion is "within 5% of V*". At 1-3k the 8 s
    # horizon traps UCT on CLIMB: the greedy rollout's endgame reserve is at its
    # worst on horizons this short.
    gaps = []
    for n in (10000, 30000):
        best, stats = MCTS("teleop", Greedy(), n_iter=n, c=0.5, seed=3).search(m)
        assert q[best] >= 0.95 * v_star                    # near-optimal decision
        gaps.append(q[best] - stats[best][1])
    assert gaps[1] < gaps[0] + 0.05                        # mean converging toward Q*
    assert -0.3 < gaps[1] < 0.6
