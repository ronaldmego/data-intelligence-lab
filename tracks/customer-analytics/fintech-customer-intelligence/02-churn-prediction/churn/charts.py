"""Charts as hand-written SVG — no plotting library.

Three reasons, in order of how much they matter:

1. **The result has to be visible without running anything.** A reviewer opening
   the repo on GitHub sees the charts in the README; that is the point of a
   portfolio artifact.
2. **Determinism.** The same run produces the same bytes, so a chart that
   changes in a diff means a *number* changed — not that a plotting library
   shifted a font by a pixel.
3. **No dependencies**, so CI renders them on a bare runner.

Colours are mid-tones on a transparent background, legible on GitHub's light and
dark themes alike without relying on media queries inside an ``<img>``.
"""

from __future__ import annotations

from dataclasses import dataclass

INK = "#8b949e"        # axes, labels — readable on white and on dark
GRID = "#8b949e"
PRIMARY = "#4c78a8"    # the model
ACCENT = "#e45756"     # the comparison / the truth line
MUTED = "#9a6fb0"      # the third series

W, H = 720, 400
PAD_L, PAD_R, PAD_T, PAD_B = 62, 18, 34, 46


@dataclass(frozen=True)
class Axes:
    """Maps data coordinates onto the drawing area."""

    x_min: float
    x_max: float
    y_min: float
    y_max: float

    def x(self, value: float) -> float:
        span = self.x_max - self.x_min or 1.0
        return PAD_L + (value - self.x_min) / span * (W - PAD_L - PAD_R)

    def y(self, value: float) -> float:
        span = self.y_max - self.y_min or 1.0
        return H - PAD_B - (value - self.y_min) / span * (H - PAD_T - PAD_B)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _text(x: float, y: float, content: str, anchor: str = "middle", size: int = 11, fill: str = INK) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" '
        f'font-family="ui-sans-serif,system-ui,sans-serif" fill="{fill}">{_escape(content)}</text>'
    )


def _frame(axes: Axes, title: str, x_label: str, y_label: str,
           x_ticks: list[tuple[float, str]], y_ticks: list[tuple[float, str]]) -> list[str]:
    parts = [_text(PAD_L, 20, title, anchor="start", size=13)]
    for value, label in y_ticks:
        y = axes.y(value)
        parts.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}" '
                     f'stroke="{GRID}" stroke-opacity="0.18" stroke-width="1"/>')
        parts.append(_text(PAD_L - 8, y + 4, label, anchor="end", size=10))
    for value, label in x_ticks:
        x = axes.x(value)
        parts.append(_text(x, H - PAD_B + 16, label, size=10))
    parts.append(f'<line x1="{PAD_L}" y1="{H - PAD_B}" x2="{W - PAD_R}" y2="{H - PAD_B}" '
                 f'stroke="{INK}" stroke-opacity="0.45"/>')
    parts.append(f'<line x1="{PAD_L}" y1="{PAD_T}" x2="{PAD_L}" y2="{H - PAD_B}" '
                 f'stroke="{INK}" stroke-opacity="0.45"/>')
    parts.append(_text((PAD_L + W - PAD_R) / 2, H - 8, x_label, size=11))
    parts.append(f'<g transform="translate(14,{(PAD_T + H - PAD_B) / 2}) rotate(-90)">{_text(0, 0, y_label)}</g>')
    return parts


def _polyline(axes: Axes, points: list[tuple[float, float]], colour: str, width: float = 2.0,
              dashed: bool = False) -> str:
    coords = " ".join(f"{axes.x(px):.1f},{axes.y(py):.1f}" for px, py in points)
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    return f'<polyline points="{coords}" fill="none" stroke="{colour}" stroke-width="{width}"{dash}/>'


def _legend(entries: list[tuple[str, str]], x: float, y: float) -> list[str]:
    parts = []
    for i, (colour, label) in enumerate(entries):
        row = y + i * 17
        parts.append(f'<line x1="{x}" y1="{row}" x2="{x + 22}" y2="{row}" stroke="{colour}" stroke-width="2.5"/>')
        parts.append(_text(x + 28, row + 4, label, anchor="start", size=11))
    return parts


def _svg(body: list[str], title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'role="img" aria-label="{_escape(title)}">\n  '
        + "\n  ".join(body)
        + "\n</svg>\n"
    )


def calibration_chart(reliability, base_rate: float) -> str:
    """Predicted vs observed risk, decile by decile.

    The diagonal is the only thing that matters: points below it mean the model
    promises more churn than it delivers.
    """
    top = max([b.mean_predicted for b in reliability] + [b.observed_rate for b in reliability] + [0.05]) * 1.15
    axes = Axes(0.0, top, 0.0, top)
    ticks = [(top * f, f"{top * f:.0%}") for f in (0.0, 0.25, 0.5, 0.75, 1.0)]

    body = _frame(axes, "Calibration — predicted vs observed, out of time",
                  "mean predicted probability", "observed churn rate", ticks, ticks)
    body.append(_polyline(axes, [(0.0, 0.0), (top, top)], INK, 1.2, dashed=True))
    body.append(_polyline(axes, [(b.mean_predicted, b.observed_rate) for b in reliability], PRIMARY, 2.2))
    for b in reliability:
        body.append(f'<circle cx="{axes.x(b.mean_predicted):.1f}" cy="{axes.y(b.observed_rate):.1f}" '
                    f'r="4" fill="{PRIMARY}"/>')
    body.append(f'<line x1="{axes.x(base_rate):.1f}" y1="{PAD_T}" x2="{axes.x(base_rate):.1f}" '
                f'y2="{H - PAD_B}" stroke="{ACCENT}" stroke-width="1" stroke-dasharray="3 3"/>')
    body += _legend([(INK, "perfect calibration"), (PRIMARY, "model"), (ACCENT, "base rate")], PAD_L + 16, PAD_T + 14)
    return _svg(body, "Calibration curve")


def gains_chart(deciles, n: int, n_events: int) -> str:
    """How much of the churn sits in the top X% of the ranked base."""
    points = [(0.0, 0.0)]
    captured = 0
    contacted = 0
    for b in deciles:
        contacted += b.size
        captured += b.n_events
        points.append((contacted / n, captured / max(1, n_events)))

    axes = Axes(0.0, 1.0, 0.0, 1.0)
    ticks = [(f, f"{f:.0%}") for f in (0.0, 0.25, 0.5, 0.75, 1.0)]
    body = _frame(axes, "Cumulative gains — churners captured by depth of contact",
                  "share of customers contacted (ranked by risk)", "share of churners captured", ticks, ticks)
    body.append(_polyline(axes, [(0.0, 0.0), (1.0, 1.0)], INK, 1.2, dashed=True))
    body.append(_polyline(axes, points, PRIMARY, 2.4))
    if len(points) > 1:
        x, y = points[1]
        body.append(f'<circle cx="{axes.x(x):.1f}" cy="{axes.y(y):.1f}" r="4.5" fill="{ACCENT}"/>')
        body.append(_text(axes.x(x) + 12, axes.y(y) + 20, f"top decile: {y:.0%} of churners",
                          anchor="start", size=11))
    body += _legend([(INK, "no model (random)"), (PRIMARY, "model")], W - PAD_R - 190, H - PAD_B - 46)
    return _svg(body, "Cumulative gains curve")


def profit_chart(by_risk, by_value, capacity: int) -> str:
    """Realised profit as contact capacity grows, under both targeting policies.

    The chart that decides the case: the curves peak in different places, and
    the value-ranked one peaks higher while contacting fewer people.
    """
    curves = [by_risk.profit_curve, by_value.profit_curve]
    xs = [x for curve in curves for x, _ in curve]
    ys = [y for curve in curves for _, y in curve]
    x_max = max(xs) or 1
    y_min, y_max = min(ys + [0.0]), max(ys) * 1.12 or 1.0

    axes = Axes(0.0, x_max, y_min, y_max)
    x_ticks = [(x_max * f, f"{int(x_max * f):,}") for f in (0.0, 0.25, 0.5, 0.75, 1.0)]
    step = (y_max - y_min) / 4 or 1.0
    y_ticks = [(y_min + step * i, f"{y_min + step * i:,.0f}") for i in range(5)]

    body = _frame(axes, "Profit by contact capacity — risk-ranked vs value-ranked",
                  "customers contacted (best first)", "realised profit", x_ticks, y_ticks)
    if y_min < 0 < y_max:
        body.append(f'<line x1="{PAD_L}" y1="{axes.y(0.0):.1f}" x2="{W - PAD_R}" y2="{axes.y(0.0):.1f}" '
                    f'stroke="{INK}" stroke-opacity="0.5" stroke-width="1"/>')
    body.append(_polyline(axes, by_risk.profit_curve, MUTED, 2.2))
    body.append(_polyline(axes, by_value.profit_curve, PRIMARY, 2.4))

    for curve, colour in ((by_risk, MUTED), (by_value, PRIMARY)):
        n_opt, profit = curve.optimal
        body.append(f'<circle cx="{axes.x(n_opt):.1f}" cy="{axes.y(profit):.1f}" r="4.5" fill="{colour}"/>')

    body.append(f'<line x1="{axes.x(capacity):.1f}" y1="{PAD_T}" x2="{axes.x(capacity):.1f}" '
                f'y2="{H - PAD_B}" stroke="{ACCENT}" stroke-width="1" stroke-dasharray="3 3"/>')
    body.append(_text(axes.x(capacity) + 6, PAD_T + 12, "budget", anchor="start", size=10, fill=ACCENT))
    body += _legend([(MUTED, "ranked by predicted risk"), (PRIMARY, "ranked by expected value")],
                    W - PAD_R - 208, H - PAD_B - 46)
    return _svg(body, "Profit by contact capacity")
