"""The case, end to end — and the three readings of it that disagree.

The pipeline trains at the earlier cutoff and scores the later one. It then
deliberately reproduces the two shortcuts that would have flattered the result,
because the headline of this case is not "we got AUC 0.7x" — it is **how far
wrong the comfortable methods would have been**, measured on the same data:

1. **Out-of-time** (the honest read): fit at the prior cutoff, score the final
   one, as a deployed model is judged.
2. **In-time random split**: shuffle customers at a single cutoff. No future to
   generalise to, so the number comes out higher — and it is the number most
   churn decks quote.
3. **A post-outcome feature**: one field derived from the label. Nothing errors;
   the metric simply becomes excellent and meaningless.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .data import Population, Tables, load_tables, scoreable_population
from .economics import Economics, TargetingComparison, compare_policies
from .features import FEATURE_NAMES, build_features, build_leaky_feature
from .metrics import Evaluation, evaluate
from .model import CollinearityFilter, LogisticRegression, PlattCalibrator, Standardiser, sigmoid

# The signs the data model was *built* with (see data-model/telco/config.py).
# Checking the fitted coefficients against them is a test of the whole pipeline
# that no real dataset can offer: here the right answer is known, so "the model
# recovered the design" is verifiable rather than a matter of taste.
DESIGNED_SIGNS: dict[str, int] = {
    "usage_trend": -1,             # w_usage_decline: falling usage raises churn
    "payment_problem_rate": +1,    # w_payment_problems
    "failed_invoices_last6": +1,
    "unresolved_escalations": +1,  # w_unresolved_support: the strongest driver
    "has_unresolved_escalation": +1,
    "app_logins_last3": -1,        # w_low_engagement
    "self_service_last3": -1,
    "is_early_life": +1,           # w_early_life
    "tenure_months": -1,
    "retention_offer_taken": -1,   # w_retention_response: a real, negative uplift
}


@dataclass(frozen=True)
class Driver:
    """One feature's effect, reported two ways because they answer two questions.

    ``marginal`` is the effect on its own — what a business stakeholder means by
    "do late payers churn more?". ``coefficient`` is the effect *given every
    other feature in the model* — what the model actually uses. They routinely
    disagree, and quoting the second as if it were the first is one of the
    commonest ways an explainable model gets explained wrong.
    """

    name: str
    coefficient: float             # conditional, on standardised features
    marginal_coefficient: float    # the same feature fitted alone
    marginal_standard_error: float
    odds_ratio_per_sd: float
    designed_sign: int | None

    @property
    def significant(self) -> bool:
        """Is the marginal effect larger than its own sampling noise?"""
        return abs(self.marginal_coefficient) > 2.0 * self.marginal_standard_error

    @property
    def recovered(self) -> bool | None:
        """Did the designed effect survive into the data, on its own terms?

        ``None`` means *inconclusive*, not *wrong*: the effect is too small
        relative to its standard error to have a readable sign. Some designed
        drivers are deliberately weak — reporting a coefficient smaller than its
        own noise as a contradiction would be a failure of the analysis, not a
        finding about the data.
        """
        if self.designed_sign is None or not self.significant:
            return None
        return (self.marginal_coefficient > 0) == (self.designed_sign > 0)

    @property
    def flips_when_conditioned(self) -> bool:
        """True when the effect changes sign once the other features are present.

        Not a bug and not leakage — it means another feature already carries
        this one's information. It is flagged because the driver table is read
        by people who will otherwise quote the conditional sign as a fact about
        customers.
        """
        return (self.coefficient > 0) != (self.marginal_coefficient > 0)


@dataclass
class CaseResult:
    train: Population
    test: Population
    drivers: list[Driver] = field(default_factory=list)
    dropped_features: list[tuple[str, str, float]] = field(default_factory=list)
    out_of_time: Evaluation | None = None
    out_of_time_uncalibrated: Evaluation | None = None
    out_of_time_oracle: Evaluation | None = None
    in_time: Evaluation | None = None
    with_leakage: Evaluation | None = None
    comparison: TargetingComparison | None = None
    economics: Economics = field(default_factory=Economics)
    n_fit: int = 0
    n_calibration: int = 0
    converged: bool = False
    # The scored population, kept so the targeting economics can be re-evaluated
    # under different commercial assumptions without refitting the model. Case 05
    # measures the save rate this case had to assume, and re-runs these numbers
    # against the measured value; refitting to change one constant would be
    # wasteful and would risk answering with a different model.
    probabilities: list[float] = field(default_factory=list)
    monthly_revenue: list[float] = field(default_factory=list)
    y_test: list[int] = field(default_factory=list)

    @property
    def optimism_gap(self) -> float:
        """How much a random split would have overstated the AUC."""
        if self.in_time is None or self.out_of_time is None:
            return 0.0
        return self.in_time.auc - self.out_of_time.auc


def _stride_split(n: int, every: int) -> tuple[list[int], list[int]]:
    """A deterministic hold-out: every ``every``-th row.

    No RNG, so the result is byte-reproducible on any machine and in any Python
    version. Customer ids are assigned in generation order, and every trait is
    drawn independently per customer, so position carries no information about
    the outcome — a stride is as good as a shuffle here, and it is auditable.
    """
    held = [i for i in range(n) if i % every == 0]
    kept = [i for i in range(n) if i % every != 0]
    return kept, held


def _subset(rows: list[list[float]], idx: list[int]) -> list[list[float]]:
    return [rows[i] for i in idx]


@dataclass(frozen=True)
class FittedModel:
    """A model plus the two transforms it is only valid alongside.

    Bundled deliberately: the pruner and the standardiser are *fitted objects*,
    not preprocessing steps. Re-deriving either from the scoring data — the
    natural thing to do when they are loose functions — is leakage that nothing
    would flag.
    """

    pruner: CollinearityFilter
    standardiser: Standardiser
    model: LogisticRegression

    def log_odds(self, x: list[list[float]]) -> list[float]:
        return self.model.decision_function(self.standardiser.transform(self.pruner.transform(x)))

    def probabilities(self, x: list[list[float]]) -> list[float]:
        return [sigmoid(z) for z in self.log_odds(x)]


def _marginal_coefficients(x: list[list[float]], y: list[int]) -> list[tuple[float, float]]:
    """Fit each feature on its own, to recover its unconditional effect and noise."""
    fits = [
        LogisticRegression(l2=0.0, max_iter=100).fit([[row[j]] for row in x], y)
        for j in range(len(x[0]))
    ]
    return [(f.coefficients[0], f.standard_errors[0]) for f in fits]


def _fit(x_train: list[list[float]], y_train: list[int], l2: float) -> FittedModel:
    pruner = CollinearityFilter().fit(x_train)
    pruned = pruner.transform(x_train)
    standardiser = Standardiser().fit(pruned)
    model = LogisticRegression(l2=l2).fit(standardiser.transform(pruned), y_train)
    return FittedModel(pruner=pruner, standardiser=standardiser, model=model)


def run_case(
    tables: Tables | None = None,
    economics: Economics | None = None,
    l2: float = 1.0,
    capacity_share: float = 0.10,
) -> CaseResult:
    """Run the whole case and return every number the report needs."""
    tables = tables if tables is not None else load_tables()
    economics = economics or Economics()

    # --- populations -----------------------------------------------------
    # Training: everyone who existed at the earlier cutoff.
    # Scoring: everyone still there at the final cutoff — which excludes those
    # who churned during the earlier window. They are not customers to save.
    train = scoreable_population(tables, "churn_labels_prior")
    test = scoreable_population(tables, "churn_labels", exclude_churned_in="churn_labels_prior")

    x_train = build_features(tables, train.cutoff, train.customer_ids)
    y_train = [train.labels[c] for c in train.customer_ids]
    x_test = build_features(tables, test.cutoff, test.customer_ids)
    y_test = [test.labels[c] for c in test.customer_ids]

    result = CaseResult(train=train, test=test, economics=economics)

    # --- the honest read: fit at the prior cutoff, score the final one ----
    # A slice of training data is withheld from fitting and reserved for the
    # calibrator, so calibration is never fitted on what it is reported against.
    fit_idx, cal_idx = _stride_split(len(y_train), every=5)
    result.n_fit, result.n_calibration = len(fit_idx), len(cal_idx)

    fitted = _fit(_subset(x_train, fit_idx), [y_train[i] for i in fit_idx], l2)
    result.converged = fitted.model.converged
    result.dropped_features = [
        (FEATURE_NAMES[j], FEATURE_NAMES[k] if k >= 0 else "(constant)", r)
        for j, k, r in fitted.pruner.dropped
    ]

    calibrator = PlattCalibrator().fit(
        fitted.log_odds(_subset(x_train, cal_idx)), [y_train[i] for i in cal_idx],
    )

    test_log_odds = fitted.log_odds(x_test)
    result.out_of_time_uncalibrated = evaluate(fitted.probabilities(x_test), y_test, log_odds=test_log_odds)
    result.out_of_time = evaluate(calibrator.transform(test_log_odds), y_test)
    probabilities = calibrator.transform(test_log_odds)

    # What calibration *could* be if we already knew the outcomes we are trying
    # to predict. Not achievable in production — it is a ceiling, reported to
    # separate "the ranking is weak" from "only the level has drifted".
    oracle = PlattCalibrator().fit(test_log_odds, y_test)
    result.out_of_time_oracle = evaluate(oracle.transform(test_log_odds), y_test)

    kept = fitted.pruner.kept_names(FEATURE_NAMES)
    marginal = _marginal_coefficients(
        fitted.standardiser.transform(fitted.pruner.transform(_subset(x_train, fit_idx))),
        [y_train[i] for i in fit_idx],
    )
    result.drivers = sorted(
        (
            Driver(
                name=name,
                coefficient=coefficient,
                marginal_coefficient=marginal[column][0],
                marginal_standard_error=marginal[column][1],
                odds_ratio_per_sd=math.exp(coefficient),
                designed_sign=DESIGNED_SIGNS.get(name),
            )
            for column, (name, coefficient) in enumerate(zip(kept, fitted.model.coefficients, strict=True))
        ),
        key=lambda d: -abs(d.coefficient),
    )

    # --- shortcut 1: a random split at a single cutoff --------------------
    in_fit, in_held = _stride_split(len(y_train), every=3)
    y_held = [y_train[i] for i in in_held]
    in_time = _fit(_subset(x_train, in_fit), [y_train[i] for i in in_fit], l2)
    result.in_time = evaluate(
        in_time.probabilities(_subset(x_train, in_held)),
        y_held,
        log_odds=in_time.log_odds(_subset(x_train, in_held)),
    )

    # --- shortcut 2: one feature derived from the outcome ------------------
    leak = build_leaky_feature(tables, "churn_labels_prior", train.customer_ids)
    x_leaky = [[*row, leak[i]] for i, row in enumerate(x_train)]
    leaky = _fit(_subset(x_leaky, in_fit), [y_train[i] for i in in_fit], l2)
    result.with_leakage = evaluate(
        leaky.probabilities(_subset(x_leaky, in_held)),
        y_held,
        log_odds=leaky.log_odds(_subset(x_leaky, in_held)),
    )

    # --- the decision: who do we actually call? ---------------------------
    arpu_column = FEATURE_NAMES.index("arpu_last3")
    monthly_revenue = [row[arpu_column] for row in x_test]
    result.comparison = compare_policies(
        probabilities, monthly_revenue, y_test, economics, capacity_share=capacity_share,
    )
    result.probabilities = probabilities
    result.monthly_revenue = monthly_revenue
    result.y_test = y_test

    return result
