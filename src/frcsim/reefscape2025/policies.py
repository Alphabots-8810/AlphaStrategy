"""Policies: heuristic baselines (also the MCTS rollout policy) and the MCTS wrapper."""
from __future__ import annotations

import random

from .. import mcts as _mcts
from . import rules
from .profiles import (ACTION_DEST, CLIMB, CORAL_ACTIONS, FLOOR, INTAKE, L2, L3,
                       NET, PARK, PROC, REEF, REM_HIGH, REM_LOW, STATION,
                       TERMINAL_ACTIONS)

_TELEOP = rules.CORAL_PTS["teleop"]


class Greedy:
    """Points-per-second greedy with an endgame time reserve.

    Scores each legal macro action by (credited points) / (mean time of the
    cycle it starts) and takes the best one that still leaves time to reach the
    endgame. algae_mode: "net" | "proc" | "coop" (PROCESSOR until 2 processed,
    then NET). rp_aware adds a flat bonus for progress toward CORAL RP / coop.
    The exact DP upper-bounds this in the single-robot model.
    """

    def __init__(self, algae_mode: str = "net", climb_buffer: float = 1.3,
                 margin_s: float = 1.0, rp_aware: bool = False, rp_bonus: float = 6.0,
                 name: str | None = None):
        assert algae_mode in ("net", "proc", "coop")
        self.algae_mode = algae_mode
        self.climb_buffer = climb_buffer
        self.margin_s = margin_s
        self.rp_aware = rp_aware
        self.rp_bonus = rp_bonus
        self.name = name or f"greedy-{algae_mode}" + ("-rp" if rp_aware else "")

    # ------------------------------------------------------------ valuations
    def coral_value(self, m, r, level) -> float:
        v = _TELEOP[level] * m.profiles[r].score[level].p
        if (self.rp_aware and m.cfg.quals
                and m.n[level] < m.cfg.thresholds["coral_per_level"]):
            v += self.rp_bonus
        return v

    def best_level(self, m, r, frm):
        """Best scorable level by value/time from `frm`: (level, value, steps) | None."""
        p, tab = m.profiles[r], m.tables[r]
        best, br = None, -1.0
        for level in CORAL_ACTIONS:
            if level in p.score and m.can_score(level):
                v = self.coral_value(m, r, level)
                st = tab[(frm, level)].mean_steps
                if v / st > br:
                    best, br = (level, v, st), v / st
        return best

    def best_free_value(self, m, r) -> float:
        p = m.profiles[r]
        vals = [self.coral_value(m, r, lv) for lv in CORAL_ACTIONS
                if lv in p.score and m.can_score(lv)]
        return max(vals) if vals else 0.0

    def unlock_value(self, m, r, a) -> float:
        """Value to this robot of freeing the 2 BRANCHES per level a staged ALGAE blocks."""
        p = m.profiles[r]
        blk = m._blk_low if a == REM_LOW else m._blk_high
        alt = self.best_free_value(m, r)
        gain = 0.0
        for level in (L2, L3):
            if level not in p.score or not blk[level]:
                continue
            if m.cap(level) - m.n[level] < 2:
                gain += 2 * max(0.0, self.coral_value(m, r, level) - alt)
            if (self.rp_aware and m.cfg.quals
                    and m.cap(level) < m.cfg.thresholds["coral_per_level"]):
                gain += self.rp_bonus
        return gain

    def disposal(self, m, r):
        p = m.profiles[r]
        can_net, can_proc = p.net is not None, p.processor is not None
        if not (can_net or can_proc):
            return None
        if self.algae_mode == "net":
            return NET if can_net else PROC
        if self.algae_mode == "proc":
            return PROC if can_proc else NET
        need_coop = m.cfg.quals and m.processed < rules.COOP_MIN_PROCESSED_EACH
        return PROC if (can_proc and need_coop) or not can_net else NET

    def disp_value(self, m, r, a) -> float:
        p = m.profiles[r]
        if a == NET:
            return rules.NET_PTS * p.net.p
        v = rules.PROCESSOR_PTS * p.processor.p
        if (self.rp_aware and m.cfg.quals
                and m.processed < rules.COOP_MIN_PROCESSED_EACH):
            v += self.rp_bonus
        return v

    # ---------------------------------------------------------------- policy
    def __call__(self, m, r) -> int:
        p, tab, loc = m.profiles[r], m.tables[r], m.loc[r]
        rem = m.N - m.busy[r]
        legal = m.legal_actions(r)
        end_a = CLIMB if CLIMB in legal else PARK
        margin = self.margin_s / m.cfg.dt
        buf = self.climb_buffer

        def reserve(frm):
            return tab[(frm, end_a)].mean_steps * buf + margin

        if rem <= reserve(loc):
            return end_a
        disp = self.disposal(m, r) if p.hold_algae else None
        best_a, best_rate = end_a, 0.0
        for a in legal:
            if a in TERMINAL_ACTIONS:
                continue
            dur = tab[(loc, a)].mean_steps
            if a == INTAKE:
                lv = self.best_level(m, r, STATION)
                if lv is None:
                    continue
                cyc, end_at, val = dur + lv[2], REEF, p.intake.p * lv[1]
            elif a in CORAL_ACTIONS:
                cyc, end_at, val = dur, REEF, self.coral_value(m, r, a)
            elif a == REM_LOW or a == REM_HIGH:
                val, cyc, end_at = self.unlock_value(m, r, a), dur, REEF
                if p.hold_algae and disp is not None:
                    val += self.disp_value(m, r, disp)
                    cyc += tab[(REEF, disp)].mean_steps
                    end_at = ACTION_DEST[disp]
                val *= p.task(a).p
            elif a == FLOOR:
                if disp is None:
                    continue
                cyc = dur + tab[(REEF, disp)].mean_steps
                end_at = ACTION_DEST[disp]
                val = p.floor_algae.p * self.disp_value(m, r, disp)
            elif a == NET or a == PROC:
                if disp is not None and a != disp and disp in legal:
                    continue                      # follow the algae mode
                cyc, end_at, val = dur, ACTION_DEST[a], self.disp_value(m, r, a)
            else:
                continue
            if val <= 0 or cyc + reserve(end_at) > rem:
                continue
            rate = val / cyc
            if rate > best_rate:
                best_a, best_rate = a, rate
        return best_a


def rp_seeker() -> Greedy:
    return Greedy(algae_mode="coop", rp_aware=True, climb_buffer=1.5, name="rp-seeker")


class RolloutPolicy:
    """One-step lookahead over a base heuristic with common random numbers.

    Bertsekas-style rollout: at each decision, every legal action is evaluated
    by taking it and then following `base` to the end of the match, under the
    SAME n_scen sampled scenarios (scenario seed + opponent draw) for every
    candidate, and the best mean wins. Pairing the candidates on identical luck
    removes most of the return variance from the comparison, which is why this
    beats UCT at small budgets here. It is a policy-improvement step: in
    expectation (large n_scen) it never does worse than `base`; ties go to the
    base heuristic's own action, so it cannot do worse on ties either. Scenario
    seeds come from the planner's own RNG, never from the world's seed.
    """

    def __init__(self, objective: str, base=None, n_scen: int = 16, seed: int = 0,
                 opp_bank=None, min_z: float = 0.0, name: str | None = None):
        self.objective = objective
        self.score = Objective(objective)
        self.base = base or Greedy("proc")
        self.n_scen = n_scen
        self.opp_bank = opp_bank
        # min_z > 0: leave the base action only if the paired mean improvement
        # exceeds min_z standard errors (guards against the optimiser's curse of
        # taking a max over noisy estimates, which bites discrete objectives).
        self.min_z = min_z
        self.rng = random.Random(seed)
        self.name = name or (f"rollout-{objective}-{self.base.name}-{n_scen}"
                             + (f"-z{min_z:g}" if min_z else ""))

    def reseed(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def __call__(self, m, r) -> int:
        legal = m.legal_actions(r)
        if len(legal) == 1:
            return legal[0]
        _no_peek(m, self.opp_bank)
        scen = [(self.rng.getrandbits(62),
                 self.opp_bank.sample(self.rng) if self.opp_bank is not None else None)
                for _ in range(self.n_scen)]
        base = self.base
        ba = base(m, r)
        cands = [ba] + [a for a in legal if a != ba]    # strict '>' => ties keep the base action
        vals = {}
        for a in cands:
            vs = []
            for sd, opp in scen:
                c = m.clone()
                c.rng, c.seed, c.opp = None, sd, opp   # scenario mode: hash streams on sd
                c.step(a)
                while (q := c.actor()) >= 0:
                    c.step(base(c, q))
                vs.append(self.score(c))
            vals[a] = vs
        n = len(scen)
        base_v = vals[ba]
        best, best_v = ba, sum(base_v)
        for a in cands[1:]:
            tot = sum(vals[a])
            if tot <= best_v:
                continue
            if self.min_z > 0:
                d = [x - y for x, y in zip(vals[a], base_v)]
                md = sum(d) / n
                var = sum((x - md) ** 2 for x in d) / max(1, n - 1)
                if md <= self.min_z * (var / n) ** 0.5:
                    continue                            # not significantly better than base
            best, best_v = a, tot
        return best


class Objective:
    """Planner objective = primary metric + a tiny expected-points tie-break.

    "win" and "rp" are discrete: for most decisions the match is already won or
    lost in every sampled scenario, so all candidates tie and a planner would fall
    back on list order (L1 before L4, INTAKE before CLIMB); experiments/tie_rule_ab.py
    measures the damage (results/tie_rule_ab.md, discrete section). 1e-4 per point stays
    below the primary metric's resolution at any practical scenario count
    (1/n_scen), so it only orders ties. Continuous objectives get no tie-break.
    """

    def __init__(self, name: str, tiebreak: float = 1e-4):
        self.name = name
        self.tiebreak = tiebreak if name in ("win", "rp") else 0.0

    def __call__(self, m) -> float:
        if not self.tiebreak:
            return m.value(self.name)
        res = m.result()
        return float(res[self.name]) + self.tiebreak * res["points"]


def _no_peek(m, opp_bank) -> None:
    """Planners must sample opponents from their own bank, never read the world's."""
    if opp_bank is None and m.opp is not None:
        raise ValueError("planner needs an opp_bank when the match has an opponent "
                         "(otherwise it would plan against the TRUE opponent outcome)")


class NoEarlyTerminal:
    """Planner pruning: drop CLIMB/PARK while more than `min_s` seconds remain."""

    def __init__(self, min_s: float = 25.0):
        self.min_s = min_s

    def __call__(self, m, r, acts):
        if (m.N - m.busy[r]) * m.cfg.dt <= self.min_s:
            return acts
        kept = [a for a in acts if a not in TERMINAL_ACTIONS]
        return kept or acts


class MCTSPolicy:
    """Online MCTS planner: re-plans at every decision epoch of every robot."""

    def __init__(self, objective: str, n_iter: int = 200, rollout=None, c: float = 1.0,
                 seed: int = 0, opp_bank=None, prior_weight: float = 0.0,
                 action_filter=None, name: str | None = None):
        self.mcts = _mcts.MCTS(Objective(objective), rollout or Greedy(), n_iter=n_iter, c=c,
                               seed=seed, opp_sampler=opp_bank.sample if opp_bank else None,
                               prior_weight=prior_weight, action_filter=action_filter)
        self.name = name or (f"mcts-{objective}-{n_iter}"
                             + (f"-pb{prior_weight:g}" if prior_weight else "")
                             + ("-prune" if action_filter is not None else ""))

    def reseed(self, seed: int) -> None:
        self.mcts.reseed(seed)

    def __call__(self, m, r) -> int:
        legal = m.legal_actions(r)
        if self.mcts.action_filter is not None:
            legal = self.mcts.action_filter(m, r, legal)
        if len(legal) == 1:                     # nothing to plan (after pruning)
            return legal[0]
        _no_peek(m, self.mcts.opp_sampler)
        return self.mcts.search(m)[0]
