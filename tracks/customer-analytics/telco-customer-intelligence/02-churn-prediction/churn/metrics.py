"""Evaluation — deliberately not one number.

"Accuracy alone isn't success" is easy to say and easy to violate, so this
module refuses to produce a single headline. It reports three separate
questions, because a model can pass any one of them while failing the others:

* **Ranking** (AUC, KS, lift) — can it put the right customers at the top? This
  is all a *prioritised call list* needs.
* **Calibration** (Brier, log-loss, reliability, ECE) — when it says 30%, do 30%
  actually churn? Any decision involving money — expected value, budget,
  guaranteed save rates — needs this, and a model can rank perfectly while being
  systematically wrong about level.
* **Concentration** (decile capture) — how much of the churn sits in the part of
  the base you can afford to contact?

Accuracy itself is not reported at all. At a 13% base rate, "always predict no
churn" scores 87% and is worth nothing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Bin:
    """One slice of the base, ordered by predicted risk."""

    index: int
    size: int
    mean_predicted: float
    observed_rate: float
    n_events: int

    @property
    def gap(self) -> float:
        return self.mean_predicted - self.observed_rate


def auc_standard_error(auc: float, n_pos: int, n_neg: int) -> float:
    """Hanley–McNeil standard error of the AUC.

    Reported because an AUC quoted without it invites conclusions the sample
    cannot support — including, on this dataset, the difference between the
    out-of-time and in-time readings.
    """
    if n_pos == 0 or n_neg == 0:
        return float("inf")
    q1 = auc / (2.0 - auc)
    q2 = 2.0 * auc * auc / (1.0 + auc)
    variance = (
        auc * (1.0 - auc)
        + (n_pos - 1) * (q1 - auc * auc)
        + (n_neg - 1) * (q2 - auc * auc)
    ) / (n_pos * n_neg)
    return math.sqrt(max(0.0, variance))


@dataclass(frozen=True)
class Evaluation:
    n: int
    n_events: int
    base_rate: float
    auc: float
    auc_standard_error: float
    ks: float
    brier: float
    log_loss: float
    expected_calibration_error: float
    calibration_slope: float
    mean_predicted: float
    reliability: list[Bin]
    deciles: list[Bin]

    @property
    def top_decile_lift(self) -> float:
        if not self.deciles or self.base_rate == 0:
            return 0.0
        return self.deciles[0].observed_rate / self.base_rate

    @property
    def top_decile_capture(self) -> float:
        if not self.deciles or self.n_events == 0:
            return 0.0
        return self.deciles[0].n_events / self.n_events


def roc_auc(scores: list[float], y: list[int]) -> float:
    """Rank-based AUC with correct handling of ties.

    Ties matter more than they look: a model that outputs the same probability
    for many customers should be scored as a coin flip among them, not credited
    with an ordering it never expressed.
    """
    pairs = sorted(zip(scores, y, strict=True), key=lambda t: t[0])
    n = len(pairs)
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        average = (i + j) / 2.0 + 1.0  # ranks are 1-based
        for k in range(i, j + 1):
            ranks[k] = average
        i = j + 1

    n_pos = sum(1 for _, label in pairs if label == 1)
    n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    rank_sum = sum(r for r, (_, label) in zip(ranks, pairs, strict=True) if label == 1)
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def ks_statistic(scores: list[float], y: list[int]) -> float:
    """Maximum separation between the cumulative distributions of the classes.

    Evaluated only at *distinct* score thresholds. Stepping row by row instead
    would let a model that assigns every customer the same score post a KS of
    1.0 purely because the input happened to arrive sorted by outcome — a
    separation it never expressed.
    """
    pairs = sorted(zip(scores, y, strict=True), key=lambda t: -t[0])
    n_pos = sum(y)
    n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.0

    cum_pos = cum_neg = 0
    best = 0.0
    i = 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        for _, label in pairs[i:j + 1]:  # the whole tied group moves together
            if label == 1:
                cum_pos += 1
            else:
                cum_neg += 1
        best = max(best, abs(cum_pos / n_pos - cum_neg / n_neg))
        i = j + 1
    return best


def brier_score(probabilities: list[float], y: list[int]) -> float:
    return sum((p - label) ** 2 for p, label in zip(probabilities, y, strict=True)) / len(y)


def log_loss(probabilities: list[float], y: list[int]) -> float:
    eps = 1e-15
    total = 0.0
    for p, label in zip(probabilities, y, strict=True):
        clipped = min(1 - eps, max(eps, p))
        total -= math.log(clipped) if label == 1 else math.log(1 - clipped)
    return total / len(y)


def _equal_count_bins(probabilities: list[float], y: list[int], n_bins: int, descending: bool) -> list[Bin]:
    """Split the base into roughly equal-sized bins, ordered by predicted risk.

    Bin boundaries are extended across ties, so customers with **identical**
    predictions always land in the same bin. Cutting through a tied group would
    make the bins depend on the order the rows arrived in — which, for a model
    with many repeated predictions, turns a perfectly calibrated result into an
    arbitrarily miscalibrated-looking one.
    """
    order = sorted(range(len(probabilities)), key=lambda i: probabilities[i], reverse=descending)
    n = len(order)
    bins: list[Bin] = []
    start = 0
    for b in range(n_bins):
        if start >= n:
            break
        stop = (b + 1) * n // n_bins
        if stop <= start:
            continue  # this bin was absorbed by a previous bin's tie extension
        while stop < n and probabilities[order[stop]] == probabilities[order[stop - 1]]:
            stop += 1
        idx = order[start:stop]
        events = sum(y[i] for i in idx)
        bins.append(Bin(
            index=len(bins),
            size=len(idx),
            mean_predicted=sum(probabilities[i] for i in idx) / len(idx),
            observed_rate=events / len(idx),
            n_events=events,
        ))
        start = stop
    return bins


def calibration_slope(log_odds: list[float], y: list[int]) -> float:
    """Regress the outcome on the model's own log-odds.

    A slope of 1.0 means the model's confidence is exactly right. Below 1.0 it
    is overconfident — its high scores are too high and its low scores too low —
    which is the classic signature of a model applied to a later period than the
    one it was fitted on.
    """
    from .model import LogisticRegression

    fitted = LogisticRegression(l2=0.0, max_iter=100).fit([[z] for z in log_odds], y)
    return fitted.coefficients[0]


def evaluate(probabilities: list[float], y: list[int], log_odds: list[float] | None = None, n_bins: int = 10) -> Evaluation:
    n = len(y)
    n_events = sum(y)
    reliability = _equal_count_bins(probabilities, y, n_bins, descending=False)
    ece = sum(b.size * abs(b.gap) for b in reliability) / n

    if log_odds is None:
        eps = 1e-15
        log_odds = [math.log(min(1 - eps, max(eps, p)) / (1 - min(1 - eps, max(eps, p)))) for p in probabilities]

    auc = roc_auc(probabilities, y)
    return Evaluation(
        n=n,
        n_events=n_events,
        base_rate=n_events / n,
        auc=auc,
        auc_standard_error=auc_standard_error(auc, n_events, n - n_events),
        ks=ks_statistic(probabilities, y),
        brier=brier_score(probabilities, y),
        log_loss=log_loss(probabilities, y),
        expected_calibration_error=ece,
        calibration_slope=calibration_slope(log_odds, y),
        mean_predicted=sum(probabilities) / n,
        reliability=reliability,
        deciles=_equal_count_bins(probabilities, y, n_bins, descending=True),
    )
