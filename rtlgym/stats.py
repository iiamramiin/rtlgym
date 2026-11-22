# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Exact binomial intervals for descriptive acceptance rates."""

from __future__ import annotations

import math


def _binomial_cdf(k: int, n: int, p: float) -> float:
    """Sum a binomial lower tail in log space, without a statistics dependency."""
    if k < 0:
        return 0.0
    if k >= n or p == 0:
        return 1.0
    if p == 1:
        return 0.0
    log_term = log_sum = n * math.log1p(-p)
    log_odds = math.log(p) - math.log1p(-p)
    for x in range(1, k + 1):
        log_term += math.log(n - x + 1) - math.log(x) + log_odds
        log_sum = max(log_sum, log_term) + math.log1p(math.exp(-abs(log_sum - log_term)))
    return min(1.0, math.exp(log_sum))


def clopper_pearson(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float] | None:
    """Two-sided equal-tail Clopper-Pearson bounds, by binomial-tail inversion.

    The confidence procedure is exact (conservative), rather than a normal
    approximation. Bounds are evaluated numerically to floating-point precision.
    Empty samples have no interval. Errors must remain in the caller's denominator.
    """
    if type(successes) is not int or type(total) is not int or not 0 <= successes <= total:
        raise ValueError("successes and total must be integers with 0 <= successes <= total")
    if not isinstance(confidence, (int, float)) or not 0 < confidence < 1:
        raise ValueError("confidence must lie strictly between zero and one")
    if not total:
        return None
    tail = (1.0 - confidence) / 2.0
    rate = successes / total
    if successes == 0:
        return 0.0, -math.expm1(math.log(tail) / total)
    if successes == total:
        return math.exp(math.log(tail) / total), 1.0

    low, high = 0.0, rate
    for _ in range(64):
        middle = (low + high) / 2.0
        # P(X >= successes) is a lower tail for the number of failures. This
        # avoids subtracting a near-one CDF when the desired tail is small.
        if _binomial_cdf(total - successes, total, 1.0 - middle) < tail:
            low = middle
        else:
            high = middle
    lower = (low + high) / 2.0
    low, high = rate, 1.0
    for _ in range(64):
        middle = (low + high) / 2.0
        if _binomial_cdf(successes, total, middle) > tail:
            low = middle
        else:
            high = middle
    return lower, (low + high) / 2.0


def format_ci(interval: tuple[float, float] | list[float] | None) -> str:
    """Format stored numerical bounds for a Markdown cell."""
    return f"[{interval[0]:.1%}, {interval[1]:.1%}]" if interval is not None else "n/a"
