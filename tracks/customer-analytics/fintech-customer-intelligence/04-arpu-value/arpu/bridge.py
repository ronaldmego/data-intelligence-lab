"""The ARPU bridge — and the interval that decides whether it says anything.

Every operator has this chart: ARPU by month, with the movement attributed to
*existing customers*, *new customers* and *churn*. The decomposition below is the
exact one, an identity rather than an approximation:

    ARPU(t) - ARPU(t-1)  =  within  +  entry  -  exit

where **within** is the paired change among customers present in both months,
**entry** is how far the joiners sit from that panel weighted by their share, and
**exit** the same for leavers. Nothing is left over.

The part that is usually missing is the second half of this module: each term
carries the standard error of the mean it is built from. Without it a bridge is
a bar chart that always has bars, and a monthly review can spend forty minutes
on a movement smaller than the noise in its own measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev

from .data import Tables, _f


@dataclass(frozen=True)
class Step:
    """One month-to-month transition, decomposed and bracketed."""

    month_from: str
    month_to: str
    arpu_from: float
    arpu_to: float
    within: float
    within_se: float
    entry: float
    entry_se: float
    exit_: float
    exit_se: float
    panel: int          # customers present in both months
    joined: int
    left: int

    @property
    def total(self) -> float:
        return self.arpu_to - self.arpu_from

    @property
    def total_se(self) -> float:
        """The terms are near-independent here; adding in quadrature is close
        enough for a band whose job is to say *smaller than the noise*."""
        return (self.within_se ** 2 + self.entry_se ** 2 + self.exit_se ** 2) ** 0.5

    @property
    def residual(self) -> float:
        """Identity check: should be zero to floating-point tolerance."""
        return self.total - (self.within + self.entry - self.exit_)

    def readable(self, term: str) -> bool:
        value, se = {
            "within": (self.within, self.within_se),
            "entry": (self.entry, self.entry_se),
            "exit": (self.exit_, self.exit_se),
            "total": (self.total, self.total_se),
        }[term]
        return abs(value) > 2.0 * se


@dataclass(frozen=True)
class Bridge:
    """The whole series, and what survives its own error bars."""

    steps: list[Step]
    arpu: list[tuple[str, float, int]]   # month, arpu, customers billed

    @property
    def first(self) -> tuple[str, float, int]:
        return self.arpu[0]

    @property
    def last(self) -> tuple[str, float, int]:
        return self.arpu[-1]

    @property
    def level_range(self) -> float:
        return max(a for _, a, _ in self.arpu) - min(a for _, a, _ in self.arpu)

    @property
    def base_growth(self) -> float:
        return self.last[2] / self.first[2] - 1.0

    @property
    def revenue_growth(self) -> float:
        first_month, first_arpu, first_n = self.first
        last_month, last_arpu, last_n = self.last
        return (last_arpu * last_n) / (first_arpu * first_n) - 1.0

    @property
    def readable_steps(self) -> list[Step]:
        """Transitions whose *total* movement clears twice its own noise."""
        return [step for step in self.steps if step.readable("total")]

    @property
    def readable_terms(self) -> int:
        return sum(
            1 for step in self.steps for term in ("within", "entry", "exit")
            if step.readable(term)
        )

    @property
    def largest_step(self) -> Step:
        return max(self.steps, key=lambda s: abs(s.total))

    @property
    def exit_is_structural_zero(self) -> bool:
        """No customer ever stops being invoiced in this data model.

        Stated as a measurement rather than as a footnote, because it is the
        reason the exit term is empty and therefore the reason the classic
        *"ARPU rose because the cheap customers left"* movement cannot appear
        here at all.
        """
        return all(step.left == 0 for step in self.steps)


def _se_of_mean(values: list[float]) -> float:
    return pstdev(values) / len(values) ** 0.5 if len(values) > 1 else 0.0


def build_bridge(tables: Tables, cutoff: str) -> Bridge:
    """Decompose the monthly ARPU series up to ``cutoff``."""
    by_month: dict[str, dict[str, float]] = {}
    for row in tables["billing"]:
        month = row["period_month"]
        if month > cutoff:
            continue
        by_month.setdefault(month, {})[row["customer_id"]] = _f(row["amount_billed"])

    months = sorted(by_month)
    series = [(m, mean(by_month[m].values()), len(by_month[m])) for m in months]

    steps: list[Step] = []
    for previous, current in zip(months, months[1:], strict=False):
        before, after = by_month[previous], by_month[current]
        panel = sorted(set(before) & set(after))
        joined = sorted(set(after) - set(before))
        left = sorted(set(before) - set(after))

        panel_before = [before[c] for c in panel]
        panel_after = [after[c] for c in panel]
        deltas = [after[c] - before[c] for c in panel]

        within = mean(deltas) if deltas else 0.0
        within_se = _se_of_mean(deltas)

        entry = entry_se = 0.0
        if joined and panel:
            weight = len(joined) / len(after)
            joiner_values = [after[c] for c in joined]
            entry = weight * (mean(joiner_values) - mean(panel_after))
            entry_se = weight * (
                (pstdev(joiner_values) ** 2 / len(joiner_values))
                + (pstdev(panel_after) ** 2 / len(panel_after))
            ) ** 0.5

        exit_ = exit_se = 0.0
        if left and panel:
            weight = len(left) / len(before)
            leaver_values = [before[c] for c in left]
            exit_ = weight * (mean(leaver_values) - mean(panel_before))
            exit_se = weight * (
                (pstdev(leaver_values) ** 2 / len(leaver_values))
                + (pstdev(panel_before) ** 2 / len(panel_before))
            ) ** 0.5

        steps.append(Step(
            month_from=previous,
            month_to=current,
            arpu_from=mean(before.values()),
            arpu_to=mean(after.values()),
            within=within,
            within_se=within_se,
            entry=entry,
            entry_se=entry_se,
            exit_=exit_,
            exit_se=exit_se,
            panel=len(panel),
            joined=len(joined),
            left=len(left),
        ))

    return Bridge(steps=steps, arpu=series)
