"""Small statistics helpers (95% normal-approximation CIs)."""
from __future__ import annotations

import math


def mean_ci(xs) -> tuple:
    """(mean, 95% half-width)."""
    xs = [float(x) for x in xs]
    n = len(xs)
    if n == 0:
        return float("nan"), float("nan")
    mu = sum(xs) / n
    if n == 1:
        return mu, float("inf")
    var = sum((x - mu) ** 2 for x in xs) / (n - 1)
    return mu, 1.96 * math.sqrt(var / n)


def fmt(xs, digits: int = 2) -> str:
    mu, hw = mean_ci(xs)
    return f"{mu:.{digits}f} ± {hw:.{digits}f}"


def paired(xs, ys) -> tuple:
    """Mean and 95% half-width of the paired difference xs - ys (CRN comparisons)."""
    return mean_ci([x - y for x, y in zip(xs, ys)])
