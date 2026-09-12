"""Closed-loop UCT with chance nodes for asynchronous (semi-MDP) multi-agent planning.

Game-agnostic by file boundary: it only needs a state object exposing
    clone(rng=..., opp=...) -> planning copy that draws from `rng`
    actor() -> int            (-1 when the episode is over)
    legal_actions(r) -> list
    step(a)                   (current actor performs a; outcome sampled)
    key() -> hashable         (exact decision-relevant state)
    value(objective) -> float (only read at terminal states)

Asynchronous decision epochs: only the agent that just became idle chooses, so
branching is |actions|, not |actions|^robots. Because nodes are keyed by the
exact post-transition state, stochastic outcomes become separate children
(closed-loop, not open-loop), and on a finite discrete model the root value
estimate is consistent - which is what lets it be checked against exact DP.
Q values are min-max normalised with the returns seen so far, so one
exploration constant works for points, win-probability, and RP objectives.
"""
from __future__ import annotations

import math
import random


class _Node:
    __slots__ = ("n", "edges", "untried", "prior")

    def __init__(self):
        self.n = 0
        self.edges = {}
        self.untried = None
        self.prior = None      # the rollout policy's action here (expanded first)


class _Edge:
    __slots__ = ("n", "w", "kids")

    def __init__(self):
        self.n = 0
        self.w = 0.0
        self.kids = {}


class MCTS:
    def __init__(self, objective: str, rollout, n_iter: int = 200, c: float = 1.0,
                 seed: int = 0, opp_sampler=None, prior_weight: float = 0.0,
                 action_filter=None):
        # action_filter(state, actor, actions) -> actions: planner-side pruning of
        # the candidate set (e.g. no "end my match now" at t=10 s). None = all legal.
        self.action_filter = action_filter
        self.objective = objective
        self.rollout = rollout          # callable(state, actor) -> action
        self.n_iter = n_iter
        self.c = c
        self.rng = random.Random(seed)
        self.opp_sampler = opp_sampler  # callable(rng) -> exogenous opponent sample, or None
        # Progressive bias (Chaslot et al. 2008): the rollout policy's action gets
        # +prior_weight/(1+visits) in normalised units, so a small budget defaults
        # to the heuristic and deviates only on evidence. 0 = plain UCT.
        self.prior_weight = prior_weight

    def reseed(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def search(self, root_state):
        """Returns (best action, {action: (visits, mean value)})."""
        rng = self.rng
        root = _Node()
        lo, hi = math.inf, -math.inf
        for _ in range(self.n_iter):
            opp = self.opp_sampler(rng) if self.opp_sampler is not None else None
            s = root_state.clone(rng=rng, opp=opp)
            node, path = root, []
            while True:                                   # selection / expansion
                r = s.actor()
                if r < 0:
                    break
                if node.untried is None:
                    acts = list(s.legal_actions(r))
                    if self.action_filter is not None:
                        acts = self.action_filter(s, r, acts)
                    rng.shuffle(acts)
                    pa = self.rollout(s, r)
                    if pa in acts:              # expand the heuristic's choice first
                        acts.remove(pa)
                        acts.append(pa)
                        node.prior = pa
                    node.untried = acts
                if node.untried:
                    a = node.untried.pop()
                    e = node.edges[a] = _Edge()
                    fresh = True
                else:
                    a = self._uct(node, lo, hi)
                    e = node.edges[a]
                    fresh = False
                s.step(a)
                path.append((node, e))
                k = s.key()
                child = e.kids.get(k)
                if child is None:
                    child = e.kids[k] = _Node()
                    fresh = True
                node = child
                if fresh:
                    break
            while True:                                   # rollout
                r = s.actor()
                if r < 0:
                    break
                s.step(self.rollout(s, r))
            v = self.objective(s) if callable(self.objective) else s.value(self.objective)
            if v < lo:
                lo = v
            if v > hi:
                hi = v
            for nd, e in path:                            # backup
                nd.n += 1
                e.n += 1
                e.w += v
        stats = {a: (e.n, e.w / e.n) for a, e in root.edges.items() if e.n}
        best = max(stats, key=lambda a: (stats[a][0], stats[a][1]))
        return best, stats

    def _uct(self, node: _Node, lo: float, hi: float):
        span = hi - lo if hi > lo else 1.0
        logn = math.log(node.n)
        best, bs = None, -math.inf
        for a, e in node.edges.items():
            sc = (e.w / e.n - lo) / span + self.c * math.sqrt(logn / e.n)
            if a == node.prior:
                sc += self.prior_weight / (1 + e.n)
            if sc > bs:
                best, bs = a, sc
        return best
