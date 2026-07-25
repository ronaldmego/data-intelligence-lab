"""What each offer is worth to each customer, in one currency.

A next-best-offer engine has to compare a retention discount against an upgrade
against a data bundle. They pay off in different ways and on different horizons,
so "best" only means something once they are all expressed as **expected margin
over the horizon, net of what it costs to make the offer**.

Three things this module insists on, each of which is a way real NBO engines go
wrong:

* **Retention and growth offers compete for the same customer.** An upgrade is
  only worth its incremental margin if the customer is still there to pay it, so
  every growth offer is discounted by the churn risk the retention model
  produces. Scoring the two in separate systems — the usual arrangement — makes
  it structurally impossible to notice that the customer being upsold this week
  is the one the retention team is trying to save.
* **The save rate is the one case 05 measured, not the one case 02 assumed.**
  Case 02 priced its list at 25%; the experiment put it at 12.4%. Using the
  measured figure here is the whole point of running the experiment.
* **Contact cost is per channel.** A push notification and an outbound call are
  not the same offer with the same economics, and a customer who has opted in to
  nothing but ``call`` is expensive to reach in a way that changes whether they
  are worth reaching at all.

The churn model, its feature builder and the base ``Economics`` all come from
case 02 rather than being restated, so the two cases cannot drift apart.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from pathlib import Path

_CHURN_CASE = Path(__file__).resolve().parents[2] / "02-churn-prediction"
if str(_CHURN_CASE) not in sys.path:
    sys.path.insert(0, str(_CHURN_CASE))

from churn.economics import Economics  # noqa: E402
from churn.features import FEATURE_NAMES, build_features  # noqa: E402
from churn.model import CollinearityFilter, LogisticRegression, Standardiser  # noqa: E402

from .data import Offer, PlanLadder, Tables, _float, _int, month_calendar  # noqa: E402

# Measured by case 05 against its held-out control. Case 02 assumed 25%; the
# experiment could not reject that, but it also could not reject zero, and the
# point estimate is this. Named here so the provenance travels with the number.
MEASURED_SAVE_RATE = 0.124


@dataclass(frozen=True)
class OfferEconomics:
    """Commercial assumptions, stated out loud so they can be argued with.

    Wraps case 02's :class:`Economics` — margin, horizon, value at risk and the
    retention arithmetic are its, unchanged — and adds the two things a
    multi-offer decision needs: what each channel costs to use, and what each
    offer costs when it is taken.
    """

    base: Economics
    contact_cost_by_channel: tuple[tuple[str, float], ...] = (
        ("push", 0.05),
        ("email", 0.10),
        ("sms", 0.25),
        ("call", 1.50),   # case 02's contact cost — an outbound call
    )
    # A data bundle's incremental monthly revenue. The catalogue records the
    # bundle in GB, not in money, so this is an assumption and is priced as
    # roughly a fifth of a mid-tier plan.
    data_bundle_monthly_price: float = 4.00

    @property
    def channel_cost(self) -> dict[str, float]:
        return dict(self.contact_cost_by_channel)

    def contact_cost(self, channel: str) -> float:
        return self.channel_cost.get(channel, self.base.contact_cost)

    def offer_cost(self, offer: Offer, monthly_revenue: float) -> float:
        """What the offer costs when it is taken, over the horizon.

        A discount is a share of the bill, so it costs more on a bigger
        customer — which a flat per-offer cost hides, and which matters because
        the biggest customers are also the ones worth saving.
        """
        if offer.type == "discount":
            return offer.value * monthly_revenue * self.base.horizon_months
        return 0.0  # an upgrade or a bundle is revenue, not a cost


@dataclass(frozen=True)
class OfferValue:
    """One offer's expected value for one customer, with its parts visible."""

    customer_id: str
    offer_id: str
    channel: str
    objective: str
    expected_value: float
    acceptance: float          # modelled P(accept), 1.0 where acceptance is folded in
    churn_probability: float
    contact_cost: float


def _upgrade_gain(offer: Offer, plan_id: str, ladder: PlanLadder) -> float:
    """Incremental monthly revenue from taking an upgrade offer."""
    if offer.upgrade_to_rank is None:
        return 0.0
    target = ladder.target_plan(plan_id, offer.upgrade_to_rank)
    if target is None:
        return 0.0
    return max(0.0, ladder.fee[target] - ladder.fee[plan_id])


def offer_value(
    offer: Offer,
    customer_id: str,
    plan_id: str,
    churn_probability: float,
    acceptance: float,
    monthly_revenue: float,
    ladder: PlanLadder,
    economics: OfferEconomics,
) -> OfferValue:
    """Expected margin from making this offer to this customer, net of cost."""
    contact_cost = economics.contact_cost(offer.channel)

    if offer.is_retention:
        # Case 02's arithmetic, with this offer's cost substituted for the
        # generic one: saved margin x the chance the save works x the chance
        # there was anything to save, minus contact and offer. Acceptance is
        # already inside the save rate, which case 05 measured per *contacted*
        # customer, so multiplying by an acceptance model here would count it
        # twice.
        priced = replace(
            economics.base,
            contact_cost=contact_cost,
            offer_cost=economics.offer_cost(offer, monthly_revenue),
        )
        value = priced.expected_value(churn_probability, monthly_revenue)
        return OfferValue(customer_id, offer.offer_id, offer.channel, offer.objective,
                          value, 1.0, churn_probability, contact_cost)

    if offer.type == "upgrade":
        monthly_gain = _upgrade_gain(offer, plan_id, ladder)
    else:
        monthly_gain = economics.data_bundle_monthly_price

    # Growth revenue only arrives if the customer is still here to pay it. This
    # is the join between the two models, and leaving it out is what lets an
    # engine upsell the customer another team is trying to save.
    survives = 1.0 - churn_probability
    gain = (acceptance * survives * monthly_gain
            * economics.base.margin * economics.base.horizon_months)
    return OfferValue(customer_id, offer.offer_id, offer.channel, offer.objective,
                      gain - contact_cost, acceptance, churn_probability, contact_cost)


# --- the acceptance model ---------------------------------------------------


@dataclass
class AcceptanceModel:
    """P(accept | contacted), fitted per campaign objective on what happened.

    Trained only on customers who were **exposed**: a held-back customer had no
    opportunity to accept, so including them would model the randomisation
    rather than the propensity.

    Features are built as of the month *before* the campaign ran. That one-month
    step back is not fussiness — case 02's feature set includes
    ``retention_offer_taken``, and building at the campaign's own month would
    hand the model the very response it is being asked to predict. It is the
    same leak case 02 exists to demonstrate, arriving through a different door.
    """

    objective: str
    model: LogisticRegression | None = None
    standardiser: Standardiser | None = None
    collinearity: CollinearityFilter | None = None
    n_train: int = 0
    n_accepted: int = 0
    base_rate: float = 0.0

    def fit(self, x: list[list[float]], y: list[int]) -> AcceptanceModel:
        self.n_train, self.n_accepted = len(y), sum(y)
        self.base_rate = self.n_accepted / len(y) if y else 0.0
        # Below this there is nothing to fit that would not be noise; the
        # predictor falls back to the base rate rather than inventing structure.
        if self.n_accepted < 20 or self.n_train - self.n_accepted < 20:
            return self

        self.collinearity = CollinearityFilter().fit(x)
        pruned = self.collinearity.transform(x)
        self.standardiser = Standardiser().fit(pruned)
        self.model = LogisticRegression(l2=2.0).fit(self.standardiser.transform(pruned), y)
        return self

    def predict(self, x: list[list[float]]) -> list[float]:
        if self.model is None or self.standardiser is None or self.collinearity is None:
            return [self.base_rate] * len(x)
        pruned = self.collinearity.transform(x)
        return self.model.predict_proba(self.standardiser.transform(pruned))


def _campaign_training_rows(
    tables: Tables,
    objective: str,
    consented_only: bool,
    consent: dict[str, dict[str, bool]],
) -> list[tuple[str, str, int]]:
    """``(customer_id, feature_cutoff, accepted)`` for one objective."""
    calendar = month_calendar(tables)
    signup = {r["customer_id"]: r["signup_date"] for r in tables["customers"]}

    campaigns = {
        r["campaign_id"]: (
            calendar[max(0, min(_int(r["month_index"]), len(calendar) - 1) - 1)],
            r["channel"],
        )
        for r in tables["campaigns"] if r["objective"] == objective
    }

    rows = []
    for exposure in tables["campaign_exposures"]:
        if exposure["campaign_id"] not in campaigns or _int(exposure["exposed"]) != 1:
            continue
        cutoff, channel = campaigns[exposure["campaign_id"]]
        cid = exposure["customer_id"]
        if signup.get(cid, "9999") > cutoff:
            continue  # not a customer yet at the feature cutoff
        if consented_only and not consent.get(cid, {}).get(channel, False):
            continue
        rows.append((cid, cutoff, _int(exposure["responded"])))
    return rows


def fit_acceptance_models(
    tables: Tables,
    objectives: list[str],
    consent: dict[str, dict[str, bool]],
    consented_only: bool = False,
) -> dict[str, AcceptanceModel]:
    """Fit one acceptance model per objective from campaign history.

    ``consented_only`` restricts training to the customers the campaign was
    actually permitted to contact. That is not a variant for completeness: going
    forward the policy only lets us contact those customers, so a model fitted
    on everyone is fitted on a population we can no longer address. The case
    reports both and compares them.
    """
    models = {}
    for objective in objectives:
        rows = _campaign_training_rows(tables, objective, consented_only, consent)
        model = AcceptanceModel(objective=objective)
        if rows:
            by_cutoff: dict[str, list[tuple[str, int]]] = {}
            for cid, cutoff, accepted in rows:
                by_cutoff.setdefault(cutoff, []).append((cid, accepted))

            x: list[list[float]] = []
            y: list[int] = []
            for cutoff, entries in sorted(by_cutoff.items()):
                ids = [cid for cid, _ in entries]
                x += build_features(tables, cutoff, ids)
                y += [accepted for _, accepted in entries]
            model.fit(x, y)
        models[objective] = model
    return models


def feature_matrix(tables: Tables, cutoff: str, customer_ids: list[str]) -> list[list[float]]:
    """Case 02's feature builder, at the decision cutoff."""
    return build_features(tables, cutoff, customer_ids)


def score_offers(
    tables: Tables,
    offers: list[Offer],
    customer_ids: list[str],
    churn_probability: dict[str, float],
    acceptance: dict[str, dict[str, float]],
    revenue: dict[str, float],
    ladder: PlanLadder,
    economics: OfferEconomics,
) -> dict[tuple[str, str], OfferValue]:
    """Expected value for every (customer, offer) pair."""
    plan_of = {r["customer_id"]: r["current_plan_id"] for r in tables["customers"]}

    values = {}
    for cid in customer_ids:
        for offer in offers:
            values[(cid, offer.offer_id)] = offer_value(
                offer=offer,
                customer_id=cid,
                plan_id=plan_of[cid],
                churn_probability=churn_probability[cid],
                acceptance=acceptance[offer.objective][cid],
                monthly_revenue=revenue[cid],
                ladder=ladder,
                economics=economics,
            )
    return values


__all__ = [
    "MEASURED_SAVE_RATE",
    "AcceptanceModel",
    "Economics",
    "FEATURE_NAMES",
    "OfferEconomics",
    "OfferValue",
    "feature_matrix",
    "fit_acceptance_models",
    "offer_value",
    "score_offers",
    "_float",
]
