"""Pareto frontier for minimum price and maximum score (plan section 7)."""

from __future__ import annotations

import itertools
from decimal import Decimal
from typing import Hashable, Iterable, Tuple

Point = Tuple[Decimal, Decimal, Hashable]


def pareto_front(points: Iterable[Point]) -> list:
    """Keys of every point no other point dominates, cheapest first.

    Equal prices form one group whose best score is kept only if it beats the best score of every cheaper group;
    all points sharing that surviving coordinate are kept (one vertex per coordinate).
    """
    front, best = [], None
    for _, group in itertools.groupby(sorted(points, key=lambda p: p[0]), key=lambda p: p[0]):
        group = list(group)
        top = max(p[1] for p in group)
        if best is None or top > best:
            front.extend(p[2] for p in group if p[1] == top)
            best = top
    return front
