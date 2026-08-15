"""A ridge-penalised logistic regression, fitted by IRLS, in the standard library.

Logistic regression is the right default for this problem and not a compromise:
churn decisions have to be *defended* to a retention team and a regulator, the
coefficients are the explanation, and a well-specified linear model on sensible
features is close to the ceiling when the data-generating process is itself
log-additive (this one is, by construction — which is what makes it a fair test
of whether the pipeline recovers the design).

Fitted by **IRLS** (Newton-Raphson) rather than gradient descent: it converges in
a handful of iterations to the actual penalised maximum-likelihood estimate,
with no learning rate to hand-tune and no "did it converge?" ambiguity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


def sigmoid(z: float) -> float:
    if z < -60:
        return 0.0
    if z > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Solve ``a x = b`` by Gaussian elimination with partial pivoting.

    The system here is (features + 1) square — around 20x20 — so an explicit
    solve is both exact enough and instant. Partial pivoting is what keeps it
    stable when two features are nearly collinear.
    """
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]

    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            raise ValueError("singular matrix: features are collinear — drop one")
        m[col], m[pivot] = m[pivot], m[col]

        inv = 1.0 / m[col][col]
        for r in range(col + 1, n):
            factor = m[r][col] * inv
            if factor == 0.0:
                continue
            for c in range(col, n + 1):
                m[r][c] -= factor * m[col][c]

    x = [0.0] * n
    for col in range(n - 1, -1, -1):
        total = m[col][n] - sum(m[col][c] * x[c] for c in range(col + 1, n))
        x[col] = total / m[col][col]
    return x


def _invert(a: list[list[float]]) -> list[list[float]]:
    """Invert a small symmetric positive-definite matrix by Gauss-Jordan."""
    n = len(a)
    m = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            raise ValueError("singular matrix: cannot invert")
        m[col], m[pivot] = m[pivot], m[col]
        scale = 1.0 / m[col][col]
        for c in range(2 * n):
            m[col][c] *= scale
        for r in range(n):
            if r == col or m[r][col] == 0.0:
                continue
            factor = m[r][col]
            for c in range(2 * n):
                m[r][c] -= factor * m[col][c]
    return [row[n:] for row in m]


@dataclass
class Standardiser:
    """Centre and scale each column.

    **Fitted on training data only.** Fitting it on train+test is the quietest
    form of leakage there is: nothing crashes, no feature is obviously wrong, and
    the test set has silently informed the transform applied to itself.
    """

    means: list[float] = field(default_factory=list)
    sds: list[float] = field(default_factory=list)

    def fit(self, x: list[list[float]]) -> Standardiser:
        n = len(x)
        if n == 0:
            raise ValueError("cannot fit a standardiser on an empty matrix")
        p = len(x[0])
        self.means = [sum(row[j] for row in x) / n for j in range(p)]
        self.sds = []
        for j in range(p):
            var = sum((row[j] - self.means[j]) ** 2 for row in x) / max(1, n - 1)
            sd = math.sqrt(var)
            # A constant column carries no information; scaling by 1.0 leaves it
            # at zero after centring rather than dividing by zero.
            self.sds.append(sd if sd > 1e-12 else 1.0)
        return self

    def transform(self, x: list[list[float]]) -> list[list[float]]:
        return [[(v - m) / s for v, m, s in zip(row, self.means, self.sds, strict=True)] for row in x]


@dataclass
class CollinearityFilter:
    """Drop features that duplicate one already kept.

    This is not about accuracy — a ridge penalty absorbs collinearity and the
    AUC barely moves. It is about the deliverable: when two features carry the
    same information, the fit splits the effect between them arbitrarily, and
    one routinely lands with **the wrong sign**. On this dataset an unpruned fit
    reports that an unresolved escalation *reduces* churn — the exact opposite
    of how the data was generated, and precisely the kind of statement that
    destroys a retention team's trust in the model.

    A model whose explanation is wrong is worse than one with no explanation,
    because someone will act on it. So near-duplicates are removed before the
    coefficients are read.

    Greedy and order-dependent: features earlier in the input order win, so the
    caller expresses its preference through the feature order.
    """

    threshold: float = 0.90
    keep: list[int] = field(default_factory=list)
    dropped: list[tuple[int, int, float]] = field(default_factory=list)  # (dropped, kept_because_of, r)

    def fit(self, x: list[list[float]], names: tuple[str, ...] | None = None) -> CollinearityFilter:
        del names  # only used by callers for reporting
        n, p = len(x), len(x[0])
        means = [sum(row[j] for row in x) / n for j in range(p)]
        sds = []
        for j in range(p):
            var = sum((row[j] - means[j]) ** 2 for row in x) / max(1, n - 1)
            sds.append(math.sqrt(var) or 1.0)

        def correlation(a: int, b: int) -> float:
            cov = sum((row[a] - means[a]) * (row[b] - means[b]) for row in x) / max(1, n - 1)
            return cov / (sds[a] * sds[b])

        self.keep, self.dropped = [], []
        for j in range(p):
            if sds[j] <= 1e-12:  # constant column: no information at all
                self.dropped.append((j, -1, 0.0))
                continue
            clash = next(((k, correlation(j, k)) for k in self.keep if abs(correlation(j, k)) >= self.threshold), None)
            if clash is None:
                self.keep.append(j)
            else:
                self.dropped.append((j, clash[0], clash[1]))
        return self

    def transform(self, x: list[list[float]]) -> list[list[float]]:
        return [[row[j] for j in self.keep] for row in x]

    def kept_names(self, names: tuple[str, ...]) -> list[str]:
        return [names[j] for j in self.keep]


@dataclass
class LogisticRegression:
    """Binary logistic regression with an L2 penalty on the slopes.

    The intercept is deliberately left unpenalised: shrinking it would distort
    the predicted base rate, and the base rate is the one thing this model must
    get right for its probabilities to mean anything.
    """

    l2: float = 1.0
    max_iter: int = 50
    tol: float = 1e-9
    intercept: float = 0.0
    coefficients: list[float] = field(default_factory=list)
    standard_errors: list[float] = field(default_factory=list)
    n_iter: int = 0
    converged: bool = False

    @staticmethod
    def _irls_system(
        design: list[list[float]], y: list[int], beta: list[float], penalty: list[float],
    ) -> tuple[list[list[float]], list[float]]:
        """Build the weighted normal equations at the current estimate."""
        p1 = len(beta)
        gram = [[0.0] * p1 for _ in range(p1)]
        rhs = [0.0] * p1

        for i, row in enumerate(design):
            eta = sum(row[j] * beta[j] for j in range(p1))
            prob = sigmoid(eta)
            # Floor the IRLS weight: as a fitted probability approaches 0 or 1
            # the weight vanishes and the working response diverges. This is
            # what keeps a near-separating feature from blowing the solve up
            # instead of just producing a large coefficient.
            w = max(prob * (1.0 - prob), 1e-6)
            wz = w * (eta + (y[i] - prob) / w)

            for j in range(p1):
                rj = row[j]
                if rj == 0.0:
                    continue
                rhs[j] += rj * wz
                wrj = w * rj
                grow = gram[j]
                for k in range(j, p1):  # symmetric: fill the upper triangle only
                    grow[k] += wrj * row[k]

        for j in range(p1):
            gram[j][j] += penalty[j]
            for k in range(j + 1, p1):
                gram[k][j] = gram[j][k]
        return gram, rhs

    def fit(self, x: list[list[float]], y: list[int]) -> LogisticRegression:
        if not x:
            raise ValueError("cannot fit on an empty matrix")
        p = len(x[0])
        design = [[1.0, *row] for row in x]  # intercept column first
        beta = [0.0] * (p + 1)
        # No penalty on the intercept (index 0).
        penalty = [0.0] + [2.0 * self.l2] * p

        gram = [[0.0] * (p + 1) for _ in range(p + 1)]
        for iteration in range(1, self.max_iter + 1):
            gram, rhs = self._irls_system(design, y, beta, penalty)
            new_beta = _solve(gram, rhs)
            shift = max(abs(a - b) for a, b in zip(new_beta, beta, strict=True))
            beta = new_beta
            self.n_iter = iteration
            if shift < self.tol:
                self.converged = True
                break

        self.intercept = beta[0]
        self.coefficients = beta[1:]

        # Standard errors from the inverse Fisher information at the estimate.
        # They exist so the report can tell "this effect points the other way"
        # apart from "this effect is indistinguishable from zero" — reporting the
        # sign of a coefficient smaller than its own noise is not a finding.
        gram, _ = self._irls_system(design, y, beta, penalty)
        try:
            covariance = _invert(gram)
            self.standard_errors = [math.sqrt(max(0.0, covariance[j][j])) for j in range(1, p + 1)]
        except ValueError:
            self.standard_errors = [float("inf")] * p
        return self

    def decision_function(self, x: list[list[float]]) -> list[float]:
        """Log-odds. The natural scale for calibration and for stacking."""
        return [
            self.intercept + sum(v * c for v, c in zip(row, self.coefficients, strict=True))
            for row in x
        ]

    def predict_proba(self, x: list[list[float]]) -> list[float]:
        return [sigmoid(z) for z in self.decision_function(x)]


@dataclass
class PlattCalibrator:
    """Map raw log-odds onto calibrated probabilities (Platt scaling).

    Fitted on a slice of the training data held out from model fitting — never
    on the evaluation set. Calibrating on the data you then report calibration
    for is circular, and it is an easy mistake to make because the resulting
    chart looks perfect.
    """

    a: float = 1.0
    b: float = 0.0

    def fit(self, log_odds: list[float], y: list[int]) -> PlattCalibrator:
        inner = LogisticRegression(l2=0.0, max_iter=100).fit([[z] for z in log_odds], y)
        self.a = inner.coefficients[0]
        self.b = inner.intercept
        return self

    def transform(self, log_odds: list[float]) -> list[float]:
        return [sigmoid(self.a * z + self.b) for z in log_odds]
