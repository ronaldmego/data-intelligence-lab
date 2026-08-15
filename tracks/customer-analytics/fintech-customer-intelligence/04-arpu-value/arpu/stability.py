"""Case 01's value axis, taken apart.

Case 01 measured how much of the base changes segment in six months and found
the movement is almost entirely on the risk axis — 41.3% against 6.0% for value —
and concluded that value is the slow axis. That is true as an aggregate and it is
the wrong picture of what is happening underneath.

The value axis in this world has **seven** true values: the seven tariffs. A
customer's measured ARPU is that tariff plus a term unrelated to anything, and
the axis is then cut into three bands. Whether a customer's band can move at all
depends on one thing: whether their tariff happens to sit near a cut. For six of
the seven it does not, and their band is a constant. For the one that does, the
band is re-drawn by billing noise every time the analysis runs.

An aggregate of "constant" and "coin flip" reads as "fairly stable". It is
neither.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev

_SEGMENTATION = Path(__file__).resolve().parents[2] / "01-segmentation"
if str(_SEGMENTATION) not in sys.path:
    sys.path.insert(0, str(_SEGMENTATION))

from segmentation.grid import band_of, quantile_cuts  # noqa: E402


@dataclass(frozen=True)
class PlanMovement:
    """One tariff's exposure to the value axis moving under it."""

    product_id: str
    monthly_fee: float
    customers: int
    moved: int
    measured_mean: float
    measured_sd: float
    nearest_cut: float
    below_cut: int          # members whose measured ARPU sits under that threshold
    above_cut: int

    @property
    def share_moved(self) -> float:
        return self.moved / self.customers if self.customers else 0.0

    @property
    def distance_to_cut_in_sd(self) -> float:
        """How far the tariff sits from the nearest band threshold, in units of
        its own measurement noise. Descriptive: it explains the magnitude, but
        it does not decide anything — see :attr:`straddles`."""
        if self.measured_sd == 0:
            return float("inf")
        return abs(self.measured_mean - self.nearest_cut) / self.measured_sd

    @property
    def straddles(self) -> bool:
        """Do this tariff's customers actually fall on both sides of a cut?

        Counted rather than inferred from the distance. A tariff can sit one
        standard deviation from a threshold and still never cross it, because
        measured ARPU is the fee *plus a non-negative* term — so its
        distribution has a hard floor at the fee, and a cut sitting exactly
        there is a wall rather than a boundary.
        """
        return self.below_cut > 0 and self.above_cut > 0


@dataclass(frozen=True)
class AxisStability:
    """Value-band movement between the two cutoffs, and where it lives."""

    months_apart: int
    n: int
    moved: int
    by_product: list[PlanMovement]
    cuts_before: list[float]
    cuts_after: list[float]
    months_averaged: int

    @property
    def share_moved(self) -> float:
        return self.moved / self.n if self.n else 0.0

    @property
    def straddling_plans(self) -> list[PlanMovement]:
        return [p for p in self.by_product if p.straddles]

    @property
    def concentration(self) -> float:
        """Share of all movers contributed by the tariffs that straddle a cut."""
        if not self.moved:
            return 0.0
        return sum(p.moved for p in self.straddling_plans) / self.moved

    @property
    def still_plans(self) -> list[PlanMovement]:
        """Tariffs where not one customer changed band."""
        return [p for p in self.by_product if p.moved == 0]

    @property
    def worst_plan(self) -> PlanMovement:
        return max(self.by_product, key=lambda p: p.share_moved)


def measure_axis(before: dict[str, float], after: dict[str, float], product_of: dict[str, str],
                 fees: dict[str, float], months_apart: int, months_averaged: int,
                 bands: int = 3) -> AxisStability:
    """Cut both snapshots into bands and count who changed.

    The axes are re-cut at each cutoff, exactly as case 01 does — which keeps
    every band the same size by construction and is precisely why the aggregate
    looks calm.
    """
    shared = [cid for cid in after if cid in before]
    cuts_before = quantile_cuts([before[c] for c in shared], bands)
    cuts_after = quantile_cuts([after[c] for c in shared], bands)

    moved_ids = [
        cid for cid in shared
        if band_of(before[cid], cuts_before) != band_of(after[cid], cuts_after)
    ]
    moved = set(moved_ids)

    by_product: list[PlanMovement] = []
    for product_id in sorted({product_of[c] for c in shared}, key=lambda p: fees[p]):
        members = [c for c in shared if product_of[c] == product_id]
        values = [after[c] for c in members]
        measured_mean = mean(values)
        nearest = min(cuts_after, key=lambda cut: abs(cut - measured_mean))
        by_product.append(PlanMovement(
            product_id=product_id,
            monthly_fee=fees[product_id],
            customers=len(members),
            moved=sum(1 for c in members if c in moved),
            measured_mean=measured_mean,
            measured_sd=pstdev(values) if len(values) > 1 else 0.0,
            nearest_cut=nearest,
            below_cut=sum(1 for v in values if v < nearest),
            above_cut=sum(1 for v in values if v >= nearest),
        ))

    return AxisStability(
        months_apart=months_apart,
        n=len(shared),
        moved=len(moved_ids),
        by_product=by_product,
        cuts_before=cuts_before,
        cuts_after=cuts_after,
        months_averaged=months_averaged,
    )
