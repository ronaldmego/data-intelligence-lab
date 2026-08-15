"""Charts as hand-written SVG — visible on GitHub, deterministic, no dependencies.

Same reasoning and the same palette as cases 02 and 05, so the track reads as
one body of work.

Case 05 left a note saying a third case wanting these primitives would be the
moment to promote them to a shared module. Having arrived: they had already
diverged. Case 05's ``Axes`` grew a ``left`` gutter that case 02's does not
have, its ``_text`` takes a weight that case 02's does not, and the two frame
helpers serve different chart families (curves against a y-axis there,
intervals and waterfalls against a zero line here). Promoting them now would
not be a move — it would be a merge into a widened API that both existing cases
would then have to be re-verified against, byte for byte, for a saving of about
a hundred lines. The note was right to ask the question and the answer, on
inspection, is still no. What is shared is the palette and the geometry, and
those are constants.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

INK = "#8b949e"        # axes, labels — readable on white and on dark
GRID = "#8b949e"
PRIMARY = "#4c78a8"    # the governed decision
ACCENT = "#e45756"     # what is lost
MUTED = "#9a6fb0"      # the ungoverned comparison
POSITIVE = "#54a24b"   # what survives

W, H = 720, 400
PAD_L, PAD_R, PAD_T, PAD_B = 62, 18, 34, 46

# Charts whose height is a function of how many rows they draw take it from the
# content instead of the constant (case 01's ``_svg(body, title, height)``, same
# reasoning). ``H`` stays for the ones drawn against an axis, where the frame is
# the point and a fixed canvas is correct.
ROW_H = 56.0


@dataclass(frozen=True)
class Axes:
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    left: float = PAD_L

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


def _svg(body: list[str], title: str, height: float = H) -> str:
    h = math.ceil(height)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" width="{W}" height="{h}" '
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


def _nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    """Ticks on round numbers inside [lo, hi]."""
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


def _linear(value: float, lo: float, hi: float, x0: float, x1: float) -> float:
    return x0 + (value - lo) / ((hi - lo) or 1.0) * (x1 - x0)


GATES_TEXT = {
    "aria": "What each governance gate removes",
    "heading": "What each gate removes from the list — and who they were",
    "removed": "customers removed",
    "churn": "churn rate they went on to have",
    "base": "base {rate}",
}

# The Spanish wording is kept short on purpose: the rule names are right-aligned
# against a 196px gutter, and Spanish runs about a fifth longer than English, so
# a literal translation overflows the left edge of the canvas.
GATES_TEXT_ES = {
    "aria": "Qué retira de la lista cada compuerta de gobierno",
    "heading": "Qué retira cada compuerta de la lista — y a quién",
    "removed": "clientes retirados",
    "churn": "tasa de abandono que tuvieron después",
    "base": "base {rate}",
}


def gates_chart(rules, base_rate: float, labels: dict[str, str],
                text: dict[str, str] | None = None) -> str:
    """Who each gate removes, and how much they were going to churn.

    Two panels, not one axis: volume and risk are different quantities in
    different units, and drawing a bar of 1,670 customers on the same line as a
    dot at 12.8% invites exactly the comparison that is meaningless. Split, they
    answer their two questions cleanly — how many, and who.

    A gate that removed a random slice of the base would put every dot on the
    dashed line. How far the dots spread either side of it is the case's central
    claim, and this is the chart that carries it. (Not that *every* dot is off
    the line — one sits a tenth of a point from it, which is why the wording
    around this figure says spread and not correlation.)

    The canvas is as tall as the rules it draws. Rows used to be stretched to
    fill a fixed 400px, which left the two vertical rules running a fifth of the
    height past the last row — dead band that reads as a cropped chart when the
    figure is embedded somewhere narrow.

    ``text`` overrides the wording (``GATES_TEXT`` are the defaults). The rule
    names come from ``labels``, which the caller already localises; the chart's
    own furniture had no such seam, so a translated render came out half in
    English.
    """
    words = {**GATES_TEXT, **(text or {})}
    rules = [r for r in rules if r.customers_removed > 0]
    top_removed = max([r.customers_removed for r in rules] + [1])
    top_churn = max([r.realised_churn_rate for r in rules] + [base_rate]) * 1.18

    gutter, bar_x0, bar_x1 = 196, 202, 408   # label column, then the bar panel
    dot_x0, dot_x1 = 470, W - PAD_R - 34     # the risk panel, with room for labels

    body = [_text(18, 20, words["heading"], anchor="start", size=13)]
    body.append(_text((bar_x0 + bar_x1) / 2, PAD_T + 8, words["removed"], size=10))
    body.append(_text((dot_x0 + dot_x1) / 2, PAD_T + 8, words["churn"], size=10))

    top = PAD_T + 24
    row = ROW_H
    # The bar of the last row is the lowest ink; the vertical rules stop just
    # under it and the canvas just under them.
    rules_bottom = top + max(0, len(rules) - 1) * row + row * 0.46 + 8
    height = rules_bottom + 12

    line = _linear(base_rate, 0.0, top_churn, dot_x0, dot_x1)
    body.append(f'<line x1="{line:.1f}" y1="{top:.1f}" x2="{line:.1f}" y2="{rules_bottom:.1f}" '
                f'stroke="{INK}" stroke-width="1.4" stroke-dasharray="5 4"/>')

    for i, rule in enumerate(rules):
        y = top + i * row
        width = _linear(rule.customers_removed, 0.0, top_removed, bar_x0, bar_x1) - bar_x0
        body.append(f'<rect x="{bar_x0}" y="{y:.1f}" width="{max(1.0, width):.1f}" '
                    f'height="{row * 0.46:.1f}" fill="{PRIMARY}" fill-opacity="0.32"/>')
        body.append(_text(gutter, y + row * 0.36, labels.get(rule.rule, rule.rule),
                          anchor="end", size=11))
        body.append(_text(bar_x0 + width + 6, y + row * 0.36,
                          f"{rule.customers_removed:,}", anchor="start", size=10))

        marker = rule.realised_churn_rate
        colour = ACCENT if marker > base_rate else POSITIVE
        cx = _linear(marker, 0.0, top_churn, dot_x0, dot_x1)
        body.append(f'<circle cx="{cx:.1f}" cy="{y + row * 0.32:.1f}" r="5.5" fill="{colour}"/>')
        body.append(_text(cx + 10, y + row * 0.36, f"{marker:.1%}",
                          anchor="start", size=10, fill=colour))

    body.append(_text(line, PAD_T + 22, words["base"].format(rate=f"{base_rate:.1%}"), size=10))
    body.append(f'<line x1="{(bar_x1 + dot_x0) / 2:.1f}" y1="{PAD_T + 14}" '
                f'x2="{(bar_x1 + dot_x0) / 2:.1f}" y2="{rules_bottom:.1f}" '
                f'stroke="{GRID}" stroke-opacity="0.25" stroke-width="1"/>')
    return _svg(body, words["aria"], height)


def plans_chart(steps: list[tuple[str, float]], totals: list[tuple[str, float, int, int]]) -> str:
    """A waterfall from the plan the business thought it had to the one it sends.

    Two subtractions, and the second is not a rule — it is the order the rules
    were applied in. Putting them on the same axis is the point: one of these is
    a policy decision somebody argued about, and the other is a bug.
    """
    # The waterfall starts at the first total and falls through each step onto
    # the next one; it does not start at zero. The totals themselves *are*
    # columns from zero, so the axis has to contain both.
    running = totals[0][1] if totals else 0.0
    marks = []
    for label, delta in steps:
        marks.append((label, running, running + delta, delta))
        running += delta

    top = max([value for _, value, _, _ in totals] + [0.0])
    axes = Axes(0.0, 1.0, 0.0, top * 1.16 or 1.0)

    body = [_text(18, 20, "From the plan that was promised to the list that goes out",
                  anchor="start", size=13)]
    for value in _nice_ticks(0.0, top * 1.16):
        y = axes.y(value)
        body.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}" '
                    f'stroke="{GRID}" stroke-opacity="0.18" stroke-width="1"/>')
        body.append(_text(PAD_L - 8, y + 4, f"{value:,.0f}", anchor="end", size=10))

    slots = len(marks) + len(totals)
    span = (W - PAD_L - PAD_R) / slots
    width = span * 0.50

    order: list[tuple[str, float, float, str, str]] = []
    for index, (label, value, n, capacity) in enumerate(totals):
        order.append((label, 0.0, value, "total", f"{n:,} of {capacity:,} contacts"))
        if index < len(marks):
            name, start, end, delta = marks[index]
            order.append((name, start, end, "step", ""))

    for i, (label, start, end, kind, note) in enumerate(order):
        cx = PAD_L + span * (i + 0.5)
        y0, y1 = axes.y(max(start, end)), axes.y(min(start, end))
        colour = ACCENT if kind == "step" else (MUTED if i == 0 else PRIMARY)
        body.append(f'<rect x="{cx - width / 2:.1f}" y="{y0:.1f}" width="{width:.1f}" '
                    f'height="{max(1.5, y1 - y0):.1f}" fill="{colour}" fill-opacity="0.85"/>')
        amount = (end - start) if kind == "step" else end
        body.append(_text(cx, y0 - 8, f"{amount:+,.0f}" if kind == "step" else f"{amount:,.0f}",
                          size=11, weight="bold" if kind == "total" else "normal",
                          fill=ACCENT if kind == "step" else INK))
        if note:
            body.append(_text(cx, y0 - 22, note, size=9))
        # A dropped connector, so the eye follows the fall from each total onto
        # the step that eats into it.
        if kind == "step":
            body.append(f'<line x1="{cx - span:.1f}" y1="{axes.y(start):.1f}" '
                        f'x2="{cx + width / 2:.1f}" y2="{axes.y(start):.1f}" '
                        f'stroke="{INK}" stroke-opacity="0.35" stroke-dasharray="3 3"/>')
            body.append(f'<line x1="{cx - width / 2:.1f}" y1="{axes.y(end):.1f}" '
                        f'x2="{cx + span:.1f}" y2="{axes.y(end):.1f}" '
                        f'stroke="{INK}" stroke-opacity="0.35" stroke-dasharray="3 3"/>')
        for line_no, part in enumerate(label.split("\n")):
            body.append(_text(cx, H - PAD_B + 16 + line_no * 12, part, size=10))

    body.append(f'<line x1="{PAD_L}" y1="{axes.y(0.0):.1f}" x2="{W - PAD_R}" y2="{axes.y(0.0):.1f}" '
                f'stroke="{INK}" stroke-opacity="0.55" stroke-width="1.2"/>')
    # No x-axis caption: the two-line column labels reach the bottom of the
    # frame, and a caption under them collides with every second one.
    body.append(_text(18, 34, "expected value of the wave", anchor="start", size=10))
    return _svg(body, "Expected value from the promised list to the sendable list")


def reach_chart(decompositions, labels: dict[str, str]) -> str:
    """Why a compliant campaign saved fewer people, split into its two terms.

    Volume is losing people; composition is the people who remain responding
    differently. Everyone assumes the second and it is the smaller one — and on
    this data it is not even resolvable from noise.
    """
    values = [v for d in decompositions for v in (d.volume, d.composition, d.total)]
    lo, hi = min(values + [0.0]), max(values + [0.0])
    pad = (hi - lo) * 0.20 or 1.0
    gutter = 190
    axes = Axes(lo - pad, hi + pad, 0.0, 1.0, left=gutter)

    body = [_text(18, 20, "Why a compliant campaign saves fewer customers", anchor="start", size=13)]
    for value in _nice_ticks(lo - pad / 2, hi + pad / 2):
        x = axes.x(value)
        body.append(f'<line x1="{x:.1f}" y1="{PAD_T + 14}" x2="{x:.1f}" y2="{H - PAD_B}" '
                    f'stroke="{GRID}" stroke-opacity="0.18" stroke-width="1"/>')
        body.append(_text(x, H - PAD_B + 16, f"{value:,.0f}", size=10))

    series = [("fewer people reached", "volume", ACCENT),
              ("the ones left responding differently", "composition", MUTED),
              ("customers no longer saved", "total", PRIMARY)]

    top, bottom = PAD_T + 26, H - PAD_B - 16
    rows = len(decompositions) * (len(series) + 1) + 0.35 * (len(decompositions) - 1)
    height = (bottom - top) / rows
    row = 0.0
    for block, d in enumerate(decompositions):
        if block:
            row += 0.35  # breathing room, so the second campaign reads as a block
        headline = (f"{labels.get(d.campaign_id, d.campaign_id)} — "
                    f"{d.exposed:,} contacted, {d.permitted:,} allowed")
        body.append(_text(18, top + row * height + 10, headline, anchor="start", size=11, weight="bold"))
        row += 1
        for label, attribute, colour in series:
            value = getattr(d, attribute)
            y = top + row * height
            x0, x1 = axes.x(min(0.0, value)), axes.x(max(0.0, value))
            body.append(f'<rect x="{x0:.1f}" y="{y:.1f}" width="{max(1.0, x1 - x0):.1f}" '
                        f'height="{height * 0.60:.1f}" fill="{colour}" fill-opacity="0.85"/>')
            body.append(_text(axes.x(value) + (7 if value >= 0 else -7), y + height * 0.48,
                              f"{value:+.1f}", anchor="start" if value >= 0 else "end", size=10))
            body.append(_text(30, y + height * 0.48, label, anchor="start", size=10))
            row += 1

    body.append(f'<line x1="{axes.x(0.0):.1f}" y1="{PAD_T + 14}" x2="{axes.x(0.0):.1f}" '
                f'y2="{H - PAD_B}" stroke="{INK}" stroke-opacity="0.55" stroke-width="1.2"/>')
    body.append(_text((gutter + W - PAD_R) / 2, H - 8, "customers saved, against the answer key", size=11))
    return _svg(body, "Reach decomposition of the compliance cost")


def cooloff_chart(points, chosen: float) -> str:
    """The cool-off window against what it suppresses.

    A step function, because campaigns happen on dates. The cost of the rule is
    not a smooth trade-off to be tuned — it is flat until the window crosses the
    last campaign, and nobody checks where that edge is until they cross it.
    """
    xs = [p.value for p in points]
    ys = [p.blocked_customers for p in points]
    axes = Axes(min(xs), max(xs), 0.0, max(ys) * 1.30 or 1.0)

    body = [_text(18, 20, "The cool-off window is a step, not a dial", anchor="start", size=13)]
    for value in _nice_ticks(0, max(ys) * 1.30 or 1.0):
        y = axes.y(value)
        body.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}" '
                    f'stroke="{GRID}" stroke-opacity="0.18" stroke-width="1"/>')
        body.append(_text(PAD_L - 8, y + 4, f"{value:,.0f}", anchor="end", size=10))
    for value in _nice_ticks(min(xs), max(xs)):
        body.append(_text(axes.x(value), H - PAD_B + 16, f"{value:,.0f}", size=10))

    coords = []
    for i, p in enumerate(points):
        if i:
            coords.append(f"{axes.x(p.value):.1f},{axes.y(points[i - 1].blocked_customers):.1f}")
        coords.append(f"{axes.x(p.value):.1f},{axes.y(p.blocked_customers):.1f}")
    body.append(f'<polyline points="{" ".join(coords)}" fill="none" stroke="{PRIMARY}" stroke-width="2.6"/>')

    # Label each plateau once, with the risk of the group it suppresses.
    seen: set[int] = set()
    for p in points:
        if p.blocked_customers in seen or p.blocked_customers == 0:
            continue
        seen.add(p.blocked_customers)
        x, y = axes.x(p.value), axes.y(p.blocked_customers)
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{ACCENT}"/>')
        # Near the right edge the label has to run back into the chart, or it
        # is silently cropped by the viewBox.
        flip = x > W * 0.55
        body.append(_text(x + (-10 if flip else 10), y - 10,
                          f"{p.blocked_customers:,} suppressed · "
                          f"{p.mean_churn_probability_blocked:.1%} modelled risk",
                          anchor="end" if flip else "start", size=10, fill=ACCENT))

    x = axes.x(chosen)
    body.append(f'<line x1="{x:.1f}" y1="{PAD_T + 14}" x2="{x:.1f}" y2="{H - PAD_B}" '
                f'stroke="{POSITIVE}" stroke-width="1.5" stroke-dasharray="4 3"/>')
    body.append(_text(x - 8, PAD_T + 26, f"policy: {chosen:,.0f} days", anchor="end", size=11, fill=POSITIVE))

    body.append(f'<line x1="{PAD_L}" y1="{H - PAD_B}" x2="{W - PAD_R}" y2="{H - PAD_B}" '
                f'stroke="{INK}" stroke-opacity="0.45"/>')
    body.append(f'<line x1="{PAD_L}" y1="{PAD_T}" x2="{PAD_L}" y2="{H - PAD_B}" '
                f'stroke="{INK}" stroke-opacity="0.45"/>')
    body.append(_text((PAD_L + W - PAD_R) / 2, H - 8,
                      "cool-off window, days since the last contact", size=11))
    return _svg(body, "Customers suppressed by the cool-off window")
