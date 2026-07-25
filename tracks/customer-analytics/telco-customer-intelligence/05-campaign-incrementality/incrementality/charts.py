"""Charts as hand-written SVG — visible on GitHub, deterministic, no dependencies.

Same reasoning as case 02, and the same palette so the two cases read as one
body of work. The drawing primitives are re-stated here rather than imported
from case 02: they are presentation details private to a case, the two cases
draw different families of chart (interval plots and waterfalls here, curves
there), and reaching into a sibling case's private helpers would couple them
where nothing else does. If a third case wants them, that is the moment to
promote them to a shared module — not before.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

INK = "#8b949e"        # axes, labels — readable on white and on dark
GRID = "#8b949e"
PRIMARY = "#4c78a8"    # the honest estimate
ACCENT = "#e45756"     # the truth
MUTED = "#9a6fb0"      # the confounded readings
POSITIVE = "#54a24b"   # the campaign's own work

W, H = 720, 400
PAD_L, PAD_R, PAD_T, PAD_B = 62, 18, 34, 46


@dataclass(frozen=True)
class Axes:
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    left: float = PAD_L  # some charts need a wider gutter for row labels

    def x(self, value: float) -> float:
        span = self.x_max - self.x_min or 1.0
        return self.left + (value - self.x_min) / span * (W - self.left - PAD_R)

    def y(self, value: float) -> float:
        span = self.y_max - self.y_min or 1.0
        return H - PAD_B - (value - self.y_min) / span * (H - PAD_T - PAD_B)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _text(x: float, y: float, content: str, anchor: str = "middle", size: int = 11,
          fill: str = INK, weight: str = "normal") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" '
        f'font-weight="{weight}" font-family="ui-sans-serif,system-ui,sans-serif" '
        f'fill="{fill}">{_escape(content)}</text>'
    )


def _svg(body: list[str], title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'role="img" aria-label="{_escape(title)}">\n  '
        + "\n  ".join(body)
        + "\n</svg>\n"
    )


def _legend(entries: list[tuple[str, str]], x: float, y: float) -> list[str]:
    parts = []
    for i, (colour, label) in enumerate(entries):
        row = y + i * 17
        parts.append(f'<line x1="{x}" y1="{row}" x2="{x + 22}" y2="{row}" stroke="{colour}" stroke-width="2.5"/>')
        parts.append(_text(x + 28, row + 4, label, anchor="start", size=11))
    return parts


def _pp_tick(value: float) -> str:
    """Percentage points, matching the report's unit for the same quantity."""
    return f"{value * 100:+.0f}" if value else "0"


def _x_axis(axes: Axes, title: str, x_label: str, ticks: list[float], fmt=_pp_tick) -> list[str]:
    parts = [_text(18, 20, title, anchor="start", size=13)]
    for value in ticks:
        x = axes.x(value)
        parts.append(f'<line x1="{x:.1f}" y1="{PAD_T}" x2="{x:.1f}" y2="{H - PAD_B}" '
                     f'stroke="{GRID}" stroke-opacity="0.18" stroke-width="1"/>')
        parts.append(_text(x, H - PAD_B + 16, fmt(value), size=10))
    parts.append(f'<line x1="{axes.x(0.0):.1f}" y1="{PAD_T}" x2="{axes.x(0.0):.1f}" y2="{H - PAD_B}" '
                 f'stroke="{INK}" stroke-opacity="0.55" stroke-width="1.2"/>')
    parts.append(_text((axes.left + W - PAD_R) / 2, H - 8, x_label, size=11))
    return parts


def _nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    """Ticks on round numbers inside [lo, hi].

    A tick at -8.37% is a tick nobody reads. Snapping the step to 1, 2 or 5
    times a power of ten costs four lines and makes every axis legible.
    """
    span = (hi - lo) / max(1, count - 1)
    if span <= 0:
        return [lo]
    magnitude = 10 ** math.floor(math.log10(span))
    step = next((m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= span), 10 * magnitude)
    start = math.ceil(lo / step) * step
    ticks, value = [], start
    while value <= hi + step * 1e-9:
        ticks.append(0.0 if abs(value) < step * 1e-9 else value)
        value += step
    return ticks


def readings_chart(readings: list[tuple[str, float, float, float]], truth: float | None) -> str:
    """The four readings of one campaign, each with its 95% interval.

    The chart the case exists for: three confounded comparisons that disagree
    with each other and with the truth, then the one comparison the control
    group makes possible — which lands on the answer and cannot prove it.
    """
    lows = [lo for _, _, lo, _ in readings]
    highs = [hi for _, _, _, hi in readings]
    span = max(highs + [truth or 0.0, 0.0]) - min(lows + [truth or 0.0, 0.0])
    pad = span * 0.12
    axes = Axes(min(lows + [truth or 0.0, 0.0]) - pad, max(highs + [truth or 0.0, 0.0]) + pad, 0, 1,
                left=PAD_L)

    body = _x_axis(axes, "Four readings of the same retention campaign",
                   "change in 90-day churn, percentage points (negative = the campaign helped)",
                   _nice_ticks(axes.x_min + pad / 2, axes.x_max - pad / 2))

    rows = len(readings)
    top, bottom = PAD_T + 30, H - PAD_B - 26
    for i, (label, value, low, high) in enumerate(readings):
        y = top + (bottom - top) * i / max(1, rows - 1)
        colour = PRIMARY if i == rows - 1 else MUTED
        body.append(f'<line x1="{axes.x(low):.1f}" y1="{y:.1f}" x2="{axes.x(high):.1f}" y2="{y:.1f}" '
                    f'stroke="{colour}" stroke-width="2.4" stroke-linecap="round"/>')
        for end in (low, high):
            body.append(f'<line x1="{axes.x(end):.1f}" y1="{y - 5:.1f}" x2="{axes.x(end):.1f}" '
                        f'y2="{y + 5:.1f}" stroke="{colour}" stroke-width="1.6"/>')
        body.append(f'<circle cx="{axes.x(value):.1f}" cy="{y:.1f}" r="5" fill="{colour}"/>')
        body.append(_text(18, y - 9, label, anchor="start", size=11,
                          weight="bold" if i == rows - 1 else "normal"))
        body.append(_text(axes.x(value), y + 21, f"{value * 100:+.2f} pp", size=10, fill=colour))

    if truth is not None:
        body.append(f'<line x1="{axes.x(truth):.1f}" y1="{PAD_T}" x2="{axes.x(truth):.1f}" '
                    f'y2="{H - PAD_B}" stroke="{ACCENT}" stroke-width="1.6" stroke-dasharray="4 3"/>')
        body += _legend([(ACCENT, f"the true effect ({truth * 100:+.2f} pp)")], W - PAD_R - 210, PAD_T + 4)
    return _svg(body, "Four readings of the same campaign")


def decomposition_chart(decompositions, labels: dict[str, str]) -> str:
    """What each campaign's headline was actually made of.

    Observed = the effect the campaign delivered + the imbalance the coin flip
    handed over. Two identically designed campaigns, and in both of them the
    second bar is the bigger one.
    """
    values = [v for d in decompositions for v in (d.observed, d.delivered, d.imbalance)]
    lo, hi = min(values + [0.0]), max(values + [0.0])
    pad = (hi - lo) * 0.18 or 0.02
    gutter = 178
    axes = Axes(lo - pad, hi + pad, 0, 1, left=gutter)

    body = _x_axis(axes, "Where each campaign's headline came from",
                   "change in 90-day churn, percentage points",
                   _nice_ticks(lo - pad / 2, hi + pad / 2))

    series = [("delivered by the campaign", "delivered", POSITIVE),
              ("handed over by the flip", "imbalance", ACCENT),
              ("what the readout said", "observed", PRIMARY)]

    top, bottom = PAD_T + 22, H - PAD_B - 18
    height = (bottom - top) / (len(decompositions) * (len(series) + 1))
    row = 0
    for d in decompositions:
        body.append(_text(18, top + row * height + 10,
                          labels.get(d.campaign_id, d.campaign_id), anchor="start", size=11, weight="bold"))
        row += 1
        for label, attribute, colour in series:
            value = getattr(d, attribute)
            y = top + row * height
            x0, x1 = axes.x(min(0.0, value)), axes.x(max(0.0, value))
            body.append(f'<rect x="{x0:.1f}" y="{y:.1f}" width="{max(1.0, x1 - x0):.1f}" '
                        f'height="{height * 0.62:.1f}" fill="{colour}" fill-opacity="0.85"/>')
            body.append(_text(axes.x(value) + (7 if value >= 0 else -7), y + height * 0.48,
                              f"{value * 100:+.2f} pp", anchor="start" if value >= 0 else "end", size=10))
            body.append(_text(34, y + height * 0.48, label, anchor="start", size=10))
            row += 1
    return _svg(body, "Decomposition of each campaign's observed effect")


def power_chart(control_sizes: list[int], power: list[float], actual: int, actual_power: float,
                required: int, effect: float) -> str:
    """How big the held-back group had to be for the answer to be findable.

    The design question, asked at the only time it can be answered — which is
    before the campaign runs, not after it disappoints.
    """
    axes = Axes(0.0, max(control_sizes), 0.0, 1.0)
    body = [_text(18, 20, f"Chance of detecting the real effect ({effect * 100:.2f} pp) "
                  f"by control-group size", anchor="start", size=13)]
    for value in (0.0, 0.25, 0.5, 0.8, 1.0):
        y = axes.y(value)
        body.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}" '
                    f'stroke="{GRID}" stroke-opacity="0.18" stroke-width="1"/>')
        body.append(_text(PAD_L - 8, y + 4, f"{value:.0%}", anchor="end", size=10))
    for value in _nice_ticks(0, max(control_sizes)):
        body.append(_text(axes.x(value), H - PAD_B + 16, f"{int(value):,}", size=10))

    coords = " ".join(f"{axes.x(n):.1f},{axes.y(p):.1f}" for n, p in zip(control_sizes, power, strict=True))
    body.append(f'<polyline points="{coords}" fill="none" stroke="{PRIMARY}" stroke-width="2.4"/>')

    body.append(f'<line x1="{PAD_L}" y1="{axes.y(0.8):.1f}" x2="{W - PAD_R}" y2="{axes.y(0.8):.1f}" '
                f'stroke="{INK}" stroke-opacity="0.5" stroke-dasharray="5 4"/>')
    body.append(_text(PAD_L + 8, axes.y(0.8) - 8, "80% — the conventional bar", anchor="start", size=10))

    # The requirement is where the curve meets the bar, so both markers are
    # anchored to the curve and labelled away from it.
    body.append(f'<line x1="{axes.x(required):.1f}" y1="{axes.y(0.8):.1f}" x2="{axes.x(required):.1f}" '
                f'y2="{H - PAD_B}" stroke="{POSITIVE}" stroke-width="1.4" stroke-dasharray="4 3"/>')
    body.append(f'<circle cx="{axes.x(required):.1f}" cy="{axes.y(0.8):.1f}" r="5" fill="{POSITIVE}"/>')
    body.append(_text(axes.x(required) + 10, axes.y(0.8) + 26, f"needed: {required:,} held back",
                      anchor="start", size=11, fill=POSITIVE))

    body.append(f'<circle cx="{axes.x(actual):.1f}" cy="{axes.y(actual_power):.1f}" r="5.5" fill="{ACCENT}"/>')
    body.append(_text(axes.x(actual) + 12, axes.y(actual_power) + 22,
                      f"this campaign: {actual:,} held back, {actual_power:.0%}",
                      anchor="start", size=11, fill=ACCENT))

    body.append(f'<line x1="{PAD_L}" y1="{H - PAD_B}" x2="{W - PAD_R}" y2="{H - PAD_B}" '
                f'stroke="{INK}" stroke-opacity="0.45"/>')
    body.append(f'<line x1="{PAD_L}" y1="{PAD_T}" x2="{PAD_L}" y2="{H - PAD_B}" '
                f'stroke="{INK}" stroke-opacity="0.45"/>')
    body.append(_text((PAD_L + W - PAD_R) / 2, H - 8, "customers held back per campaign", size=11))
    return _svg(body, "Statistical power by control-group size")
