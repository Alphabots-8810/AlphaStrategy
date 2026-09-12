"""Exact finite-horizon DP: ONE robot maximising expected TELEOP points.

Model = sim.Match with a single robot, auto=False, floor_algae=False (same
duration PMFs, same legality, same end-of-match semantics). Expected points are
additive, so L1 count, PROCESSOR count and Coopertition drop out of the state:

    config = (loc, holding CORAL, holding ALGAE, #L2, #L3, #L4, low ALGAE left,
              high ALGAE left)  ->  4*2*2*13^3*4*4 = 562,432 configs

Backward induction over the dt time grid, vectorised over configs, with a ring
buffer of the next Dmax value slices. Threshold objectives (RP, win prob) would
bring every count back into the state - those go through MCTS instead.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from . import rules
from .profiles import (ACTION_DEST, CLIMB, INTAKE, L1, L2, L3, L4, N_LOCS, NET, PARK,
                       PROC, REM_HIGH, REM_LOW, RobotProfile, build_duration_table)
from .sim import GameConfig

NL = rules.BRANCHES_PER_LEVEL + 1
SHAPE = (N_LOCS, 2, 2, NL, NL, NL,
         rules.LOW_ALGAE_PER_REEF + 1, rules.HIGH_ALGAE_PER_REEF + 1)
N_CONFIGS = int(np.prod(SHAPE))
DP_ACTIONS = (INTAKE, L1, L2, L3, L4, REM_LOW, REM_HIGH, NET, PROC, CLIMB, PARK)


def encode(loc, hc, ha, n2, n3, n4, low, high):
    return np.ravel_multi_index((loc, hc, ha, n2, n3, n4, low, high), SHAPE)


def encode_match(m, r: int = 0) -> int:
    return int(encode(m.loc[r], m.hc[r], m.ha[r], m.n[2], m.n[3], m.n[4], m.low, m.high))


@dataclass
class DPResult:
    profile: RobotProfile
    cfg: GameConfig
    table: dict
    V0: np.ndarray        # optimal expected TELEOP points from t=0, per config
    policy: np.ndarray    # int8 [n_steps, N_CONFIGS]: optimal action id
    seconds: float

    def value(self, loc, hc=0, ha=0, n2=0, n3=0, n4=0,
              low=rules.LOW_ALGAE_PER_REEF, high=rules.HIGH_ALGAE_PER_REEF) -> float:
        return float(self.V0[encode(loc, hc, ha, n2, n3, n4, low, high)])


def _transitions(profile: RobotProfile, cfg: GameConfig):
    """Per action: (a, legal mask, next-config on success, on failure, reward, p, terminal)."""
    idx = np.arange(N_CONFIGS)
    loc, hc, ha, n2, n3, n4, low, high = np.unravel_index(idx, SHAPE)
    blk = rules.ALGAE_BLOCKING[cfg.algae_blocking]
    B, F = rules.BRANCHES_PER_LEVEL, rules.BRANCHES_PER_FACE_PER_LEVEL
    cap = {lv: B - F * (low * (lv in blk["low"]) + high * (lv in blk["high"]))
           for lv in (L2, L3, L4)}
    cnt = {L2: n2, L3: n3, L4: n4}
    one, zero = np.ones_like(hc), np.zeros_like(hc)
    out = []
    for a in DP_ACTIONS:
        task = profile.task(a)
        if task is None:
            continue
        base = {"loc": np.full_like(loc, ACTION_DEST[a]), "hc": hc, "ha": ha,
                "n2": n2, "n3": n3, "n4": n4, "low": low, "high": high}
        ns, nf = dict(base), dict(base)
        reward, terminal = 0.0, False
        free_hands = (hc == 0) | profile.hold_both
        if a == INTAKE:
            legal = (hc == 0) & ((ha == 0) | profile.hold_both)
            ns["hc"] = one
        elif a == L1:
            legal = hc == 1
            ns["hc"] = nf["hc"] = zero
            reward = rules.CORAL_PTS["teleop"][a]
        elif a in (L2, L3, L4):
            legal = (hc == 1) & (cnt[a] < cap[a])
            ns["hc"] = nf["hc"] = zero
            ns[f"n{a}"] = np.minimum(cnt[a] + 1, NL - 1)
            reward = rules.CORAL_PTS["teleop"][a]
        elif a in (REM_LOW, REM_HIGH):
            key = "low" if a == REM_LOW else "high"
            left = low if a == REM_LOW else high
            legal = (left > 0) & free_hands
            if profile.hold_algae:
                legal &= ha == 0
                ns["ha"] = one
            ns[key] = np.maximum(left - 1, 0)
        elif a in (NET, PROC):
            legal = ha == 1
            ns["ha"] = nf["ha"] = zero
            reward = rules.NET_PTS if a == NET else rules.PROCESSOR_PTS
        else:                                   # CLIMB / PARK: episode ends for this robot
            legal = np.ones_like(hc, dtype=bool)
            terminal = True
        out.append((a, np.asarray(legal, dtype=bool),
                    encode(**ns).astype(np.int32), encode(**nf).astype(np.int32),
                    float(reward), task.p, terminal))
    return out


def solve(profile: RobotProfile, cfg: GameConfig, verbose: bool = False) -> DPResult:
    if cfg.floor_algae or cfg.auto:
        raise ValueError("DP models TELEOP from a fixed start with no floor-ALGAE pool: "
                         "use GameConfig(auto=False, floor_algae=False)")
    t_start = time.perf_counter()
    table = build_duration_table(profile, cfg.dt, cfg.k)
    N = cfg.n_steps
    acts = _transitions(profile, cfg)
    dmax = max(max(pm.steps) for pm in table.values())
    W = dmax + 1
    ring = np.zeros((W, N_CONFIGS))
    zeros = np.zeros(N_CONFIGS)
    policy = np.empty((N, N_CONFIGS), dtype=np.int8)
    blk = N_CONFIGS // N_LOCS                  # loc is the most significant index
    park, cage = rules.PARK_PTS, rules.CAGE_PTS.get(profile.climb or "", 0)
    for i in range(N - 1, -1, -1):
        Vi = np.empty(N_CONFIGS)
        for ell in range(N_LOCS):
            sl = slice(ell * blk, (ell + 1) * blk)
            best_q = np.full(blk, -1.0)
            best_a = np.full(blk, PARK, dtype=np.int8)
            for a, legal, nxt_s, nxt_f, reward, p, terminal in acts:
                pm = table[(ell, a)]
                if terminal:
                    val = 0.0
                    for st, pr in zip(pm.steps, pm.probs):
                        j = i + st
                        if a == CLIMB and j <= N:
                            val += pr * (p * cage + (1.0 - p) * park)
                        elif j - pm.service <= N:     # reached the BARGE ZONE by 0:00
                            val += pr * park
                    q = np.full(blk, val)
                else:
                    q = np.zeros(blk)
                    ns, nf = nxt_s[sl], nxt_f[sl]
                    for st, pr in zip(pm.steps, pm.probs):
                        j = i + st
                        if j > N:
                            continue                   # does not finish before 0:00
                        Vj = ring[j % W] if j < N else zeros
                        if p >= 1.0:
                            q += pr * (reward + Vj[ns])
                        else:
                            q += pr * (p * (reward + Vj[ns]) + (1.0 - p) * Vj[nf])
                q[~legal[sl]] = -np.inf
                better = q > best_q
                best_q[better] = q[better]
                best_a[better] = a
            Vi[sl] = best_q
            policy[i, sl] = best_a
        ring[i % W] = Vi
        if verbose and i % 100 == 0:
            print(f"  dp t={i * cfg.dt:6.2f}s  {time.perf_counter() - t_start:5.1f}s elapsed")
    return DPResult(profile, cfg, table, ring[0].copy(), policy,
                    time.perf_counter() - t_start)


class DPPolicy:
    """Plays the DP-optimal policy inside a 1-robot sim.Match."""

    name = "dp-optimal"

    def __init__(self, res: DPResult):
        self.res = res

    def __call__(self, m, r) -> int:
        if m.R != 1 or (m.cfg is not self.res.cfg and m.cfg != self.res.cfg):
            raise ValueError("DPPolicy only plays the 1-robot model it was solved for")
        return int(self.res.policy[m.busy[r], encode_match(m, r)])
