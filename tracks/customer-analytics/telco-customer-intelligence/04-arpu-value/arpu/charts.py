"""Charts as hand-written SVG — visible on GitHub, deterministic, no dependencies.

Same palette and geometry as cases 01, 02, 03 and 05, so the track reads as one
body of work. Case 03 recorded why these primitives are not a shared module: the
existing versions had already diverged in their axis helpers, and merging them
would mean re-verifying committed cases byte for byte to save a hundred lines.
That is still true.

**Height is computed from the content, never fixed.** A canvas taller than what
is drawn on it reads fine in the repository and badly the moment the file is
embedded in a page, where it scales to the container width and drags its empty
band along proportionally.
"""

from __future__ import annotations

import math

INK = "#8b949e"
GRID = "#8b949e"
PRIMARY = "#4c78a8"    # the honest reading
ACCENT = "#e45756"     # what it costs, or what is lost
MUTED = "#9a6fb0"      # the comparison
POSITIVE = "#54a24b"   # what survives

W = 720
PAD_L, PAD_R, PAD_T, PAD_B = 62, 18, 34, 26


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _text(x: float, y: float, content: str, anchor: str = "middle", size: int = 11,
          fill: str = INK, weight: str = "normal", opacity: float = 1.0) -> str:
    extra = f' fill-opacity="{opacity}"' if opacity < 1.0 else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" '
        f'font-weight="{weight}" font-family="ui-sans-serif,system-ui,sans-serif" '
        f'fill="{fill}"{extra}>{_escape(content)}</text>'
    )


def _svg(body: list[str], title: str, height: float) -> str:
    h = math.ceil(height)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" width="{W}" height="{h}" '
        f'role="img" aria-label="{_escape(title)}">\n  '
        + "\n  ".join(body)
        + "\n</svg>\n"
    )


def _linear(value: float, lo: float, hi: float, x0: float, x1: float) -> float:
    return x0 + (value - lo) / ((hi - lo) or 1.0) * (x1 - x0)


def _nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
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


# --- 1. the chain -----------------------------------------------------------


def chain_chart(rungs: list[tuple[str, float]], notes: dict[str, str]) -> str:
    """What a customer is worth, one subtraction at a time.

    Drawn as a ladder rather than a waterfall: the reader's question here is
    *how far apart are these four numbers*, and a waterfall answers *what was
    subtracted*, which the labels already say.
    """
    row_h = 46.0
    top = PAD_T + 34
    height = top + len(rungs) * row_h + 34
    x0, x1 = 190, W - PAD_R - 96
    top_value = max(value for _, value in rungs) * 1.06

    body = [_text(18, 20, "One customer, one month: four answers to what they are worth",
                  anchor="start", size=13)]
    body.append(_text(18, 36, "each rung is the one above it, plus or minus something the rung above ignores",
                      anchor="start", size=10))

    for value in _nice_ticks(0.0, top_value):
        x = _linear(value, 0.0, top_value, x0, x1)
        body.append(f'<line x1="{x:.1f}" y1="{top - 8:.1f}" x2="{x:.1f}" y2="{height - 28:.1f}" '
                    f'stroke="{GRID}" stroke-opacity="0.18" stroke-width="1"/>')
        body.append(_text(x, height - 14, f"{value:.0f}", size=10))

    for i, (label, value) in enumerate(rungs):
        y = top + i * row_h
        width = _linear(value, 0.0, top_value, x0, x1) - x0
        colour = PRIMARY if i == 0 else (POSITIVE if i == len(rungs) - 1 else MUTED)
        body.append(f'<rect x="{x0}" y="{y:.1f}" width="{max(1.5, width):.1f}" height="22" '
                    f'fill="{colour}" fill-opacity="0.78"/>')
        body.append(_text(x0 - 10, y + 12, label, anchor="end", size=11, weight="bold"))
        note = notes.get(label)
        if note:
            body.append(_text(x0 - 10, y + 26, note, anchor="end", size=9, opacity=0.85))
        body.append(_text(x0 + width + 8, y + 16, f"{value:,.2f}", anchor="start", size=11,
                          weight="bold", fill=colour))
        if i:
            step = value - rungs[i - 1][1]
            body.append(_text(x1 + 82, y + 16, f"{step:+,.2f}", anchor="end", size=10,
                              fill=POSITIVE if step > 0 else ACCENT))

    body.append(_text(x1 + 82, top - 12, "vs the rung above", anchor="end", size=9, opacity=0.85))
    body.append(f'<line x1="{x0}" y1="{top - 8:.1f}" x2="{x0}" y2="{height - 28:.1f}" '
                f'stroke="{INK}" stroke-opacity="0.55" stroke-width="1.2"/>')
    return _svg(body, "The customer value chain, per customer per month", height)


# --- 2. the composition trap ------------------------------------------------


def usage_chart(evidence) -> str:
    """One correlation asked twice: over the base, and inside each tariff."""
    rows = [evidence.overall, *evidence.by_plan]
    row_h = 34.0
    top = PAD_T + 40
    height = top + len(rows) * row_h + 62
    x0, x1 = 178, W - PAD_R - 62

    lo = min(min(link.r - 2 * link.standard_error for link in rows), 0.0) - 0.02
    hi = max(link.r + 2 * link.standard_error for link in rows) + 0.03
    zero = _linear(0.0, lo, hi, x0, x1)

    body = [_text(18, 20, "Do customers who use more data generate more revenue?",
                  anchor="start", size=13)]
    body.append(_text(18, 36, "correlation of the non-fee part of an invoice with that month's usage, "
                              "with its own ±2 standard errors", anchor="start", size=10))

    axis_y = height - 44
    for value in _nice_ticks(lo, hi):
        x = _linear(value, lo, hi, x0, x1)
        body.append(f'<line x1="{x:.1f}" y1="{top - 10:.1f}" x2="{x:.1f}" y2="{axis_y:.1f}" '
                    f'stroke="{GRID}" stroke-opacity="0.16" stroke-width="1"/>')
        body.append(_text(x, axis_y + 14, f"{value:+.2f}", size=10))
    body.append(f'<line x1="{zero:.1f}" y1="{top - 10:.1f}" x2="{zero:.1f}" y2="{axis_y:.1f}" '
                f'stroke="{INK}" stroke-opacity="0.55" stroke-width="1.2"/>')

    for i, link in enumerate(rows):
        y = top + i * row_h
        aggregate = i == 0
        colour = ACCENT if aggregate else PRIMARY
        centre = _linear(link.r, lo, hi, x0, x1)
        half = (_linear(2 * link.standard_error, lo, hi, x0, x1) - zero)
        body.append(f'<line x1="{centre - half:.1f}" y1="{y + 10:.1f}" x2="{centre + half:.1f}" '
                    f'y2="{y + 10:.1f}" stroke="{colour}" stroke-opacity="0.55" stroke-width="2"/>')
        body.append(f'<circle cx="{centre:.1f}" cy="{y + 10:.1f}" r="{5.5 if aggregate else 4}" '
                    f'fill="{colour}"/>')
        label = "all plans together" if aggregate else f"within {link.scope}"
        body.append(_text(x0 - 10, y + 14, label, anchor="end", size=11,
                          weight="bold" if aggregate else "normal"))
        body.append(_text(x1 + 10, y + 14, f"{link.r:+.4f}", anchor="start", size=10, fill=colour))

    body.append(_text(18, height - 10, f"the aggregate is {evidence.ratio:.0f}× the largest reading "
                                       f"inside any single plan", anchor="start", size=10, fill=ACCENT))
    return _svg(body, "Usage and revenue, aggregated and within each tariff", height)


# --- 3. the bridge ----------------------------------------------------------


def bridge_chart(bridge) -> str:
    """Every month-to-month movement, with the noise it has to clear."""
    steps = bridge.steps
    plot_w = W - PAD_L - PAD_R
    slot = plot_w / max(1, len(steps))
    top = PAD_T + 32
    plot_h = 150.0
    height = top + plot_h + 62

    span = max(max(abs(s.total) + 2 * s.total_se for s in steps), 0.01) * 1.04
    mid = top + plot_h / 2

    readable = bridge.readable_steps
    body = [_text(18, 20, "Monthly ARPU movement, against its own measurement error",
                  anchor="start", size=13)]
    body.append(_text(18, 36, f"{len(steps)} transitions; {len(readable)} clears ±2 standard errors, "
                              f"and about one would be expected to by chance", anchor="start", size=10))

    for value in _nice_ticks(-span, span, 5):
        y = mid - value / span * (plot_h / 2)
        body.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}" '
                    f'stroke="{GRID}" stroke-opacity="0.16" stroke-width="1"/>')
        body.append(_text(PAD_L - 8, y + 4, f"{value:+.2f}", anchor="end", size=9))
    body.append(f'<line x1="{PAD_L}" y1="{mid:.1f}" x2="{W - PAD_R}" y2="{mid:.1f}" '
                f'stroke="{INK}" stroke-opacity="0.6" stroke-width="1.2"/>')

    for i, step in enumerate(steps):
        cx = PAD_L + slot * (i + 0.5)
        colour = ACCENT if step.readable("total") else PRIMARY
        y_value = mid - step.total / span * (plot_h / 2)
        y_hi = mid - (step.total + 2 * step.total_se) / span * (plot_h / 2)
        y_lo = mid - (step.total - 2 * step.total_se) / span * (plot_h / 2)
        body.append(f'<line x1="{cx:.1f}" y1="{y_hi:.1f}" x2="{cx:.1f}" y2="{y_lo:.1f}" '
                    f'stroke="{colour}" stroke-opacity="0.45" stroke-width="{max(2.0, slot * 0.42):.1f}"/>')
        body.append(f'<circle cx="{cx:.1f}" cy="{y_value:.1f}" r="2.6" fill="{colour}"/>')

    for i in (0, len(steps) - 1):
        cx = PAD_L + slot * (i + 0.5)
        body.append(_text(cx, top + plot_h + 18, steps[i].month_to[:7], size=9))

    first_month, first_arpu, first_n = bridge.first
    last_month, last_arpu, last_n = bridge.last
    body.append(_text(18, height - 26, f"ARPU {first_arpu:.2f} → {last_arpu:.2f} over the window "
                                       f"({bridge.level_range:.2f} between the highest and lowest month)",
                      anchor="start", size=10))
    body.append(_text(W - PAD_R, height - 26, "dot = the movement · band = ±2 standard errors",
                      anchor="end", size=9, opacity=0.8))
    body.append(_text(18, height - 12, f"meanwhile the base grew {bridge.base_growth:+.0%} "
                                       f"and revenue {bridge.revenue_growth:+.0%}",
                      anchor="start", size=10, fill=POSITIVE))
    return _svg(body, "Month-on-month ARPU movement with its confidence band", height)


# --- 4. the horizon ---------------------------------------------------------


def horizon_chart(comparison, cap_sweep, flat_overlap_label: str) -> str:
    """How long a save is credited for, and what the answer does to the list.

    The implied life is drawn as a curve over the base sorted by it, not as a
    histogram: every customer above the ceiling lands on the ceiling, so a
    histogram is one enormous bar at the right-hand edge and a smear everywhere
    else. Sorted, the same ceiling is a plateau — visible, honest, and it leaves
    the interesting half of the distribution readable.
    """
    months = sorted(comparison.hazard.months)
    n = len(months)
    row_h = 32.0
    top = PAD_T + 34
    plot_h = 150.0
    base_y = top + plot_h
    sweep_top = base_y + 78
    height = sweep_top + 18 + len(cap_sweep) * row_h + 26

    body = [_text(18, 20, "How many months of margin does saving a customer buy?",
                  anchor="start", size=13)]
    body.append(_text(18, 36, "the base sorted by the life its own churn probability implies",
                      anchor="start", size=10))

    x0, x1 = PAD_L, W - PAD_R - 26
    hi = max(months) * 1.04
    points = []
    for i, value in enumerate(months):
        x = x0 + (i / max(1, n - 1)) * (x1 - x0)
        points.append(f"{x:.1f},{base_y - value / hi * plot_h:.1f}")
    body.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{PRIMARY}" '
                f'stroke-width="2.2"/>')

    for value in _nice_ticks(0.0, hi):
        y = base_y - value / hi * plot_h
        body.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" '
                    f'stroke="{GRID}" stroke-opacity="0.16" stroke-width="1"/>')
        body.append(_text(x0 - 8, y + 4, f"{value:.0f}", anchor="end", size=9))
    body.append(f'<line x1="{x0}" y1="{base_y:.1f}" x2="{x1}" y2="{base_y:.1f}" '
                f'stroke="{INK}" stroke-opacity="0.55" stroke-width="1.2"/>')

    flat_y = base_y - comparison.flat_months / hi * plot_h
    body.append(f'<line x1="{x0}" y1="{flat_y:.1f}" x2="{x1}" y2="{flat_y:.1f}" '
                f'stroke="{ACCENT}" stroke-width="2" stroke-dasharray="5 3"/>')
    body.append(_text(x1, flat_y - 8, f"case 02 credits every customer with "
                                      f"{comparison.flat_months:.0f} months",
                      anchor="end", size=10, fill=ACCENT))

    cross_x = x0 + comparison.below_flat_share * (x1 - x0)
    body.append(f'<line x1="{cross_x:.1f}" y1="{flat_y:.1f}" x2="{cross_x:.1f}" y2="{base_y:.1f}" '
                f'stroke="{ACCENT}" stroke-opacity="0.45" stroke-width="1" stroke-dasharray="2 3"/>')
    body.append(_text(cross_x + 6, base_y - 8, f"{comparison.below_flat_share:.1%} have less life "
                                               f"than that", anchor="start", size=9, fill=ACCENT))
    body.append(_text(x0, base_y + 16, "0%", anchor="start", size=9, opacity=0.8))
    body.append(_text(x1, base_y + 16, "100%", anchor="end", size=9, opacity=0.8))
    body.append(_text((x0 + x1) / 2, base_y + 32, "customers, sorted by implied remaining life",
                      size=10))

    # the ceiling sweep
    body.append(_text(18, sweep_top - 26, f"and what the ceiling does to {flat_overlap_label}",
                      anchor="start", size=11, weight="bold"))
    bx0, bx1 = 176, W - PAD_R - 208
    col1, col2 = bx1 + 58, W - PAD_R
    body.append(_text(col1, sweep_top - 8, "kept from", anchor="middle", size=9, opacity=0.85))
    body.append(_text(col1, sweep_top + 4, "case 02's list", anchor="middle", size=9, opacity=0.85))
    body.append(_text(col2, sweep_top - 8, "…of which is", anchor="end", size=9, opacity=0.85))
    body.append(_text(col2, sweep_top + 4, "the richest alone", anchor="end", size=9, opacity=0.85))
    for i, point in enumerate(cap_sweep):
        y = sweep_top + 18 + i * row_h
        width = point.overlap_with_flat * (bx1 - bx0)
        body.append(f'<rect x="{bx0}" y="{y:.1f}" width="{max(1.5, width):.1f}" height="18" '
                    f'fill="{MUTED}" fill-opacity="0.78"/>')
        body.append(_text(bx0 - 10, y + 13, f"ceiling {point.cap:.0f} months", anchor="end", size=10))
        body.append(_text(col1, y + 13, f"{point.overlap_with_flat:.0%}", anchor="middle",
                          size=11, weight="bold", fill=MUTED))
        body.append(_text(col2, y + 13, f"{point.overlap_with_revenue_only:.0%}", anchor="end",
                          size=11, weight="bold", fill=POSITIVE))
    body.append(f'<line x1="{bx0}" y1="{sweep_top + 10:.1f}" x2="{bx0}" '
                f'y2="{sweep_top + 16 + len(cap_sweep) * row_h:.1f}" '
                f'stroke="{INK}" stroke-opacity="0.55" stroke-width="1.2"/>')
    return _svg(body, "Implied customer life and what the ceiling does to the target list", height)


# --- 5. the value axis ------------------------------------------------------


def axis_chart(axis) -> str:
    """Where the value axis moves, tariff by tariff."""
    rows = axis.by_plan
    row_h = 36.0
    top = PAD_T + 46
    height = top + len(rows) * row_h + 42
    x0, x1 = 200, W - PAD_R - 88
    top_value = max(max(p.share_moved for p in rows), 0.05) * 1.15

    body = [_text(18, 20, "Which customers change value band in six months?", anchor="start", size=13)]
    body.append(_text(18, 36, f"{axis.share_moved:.1%} of the base overall — and where it comes from",
                      anchor="start", size=10))

    for value in _nice_ticks(0.0, top_value):
        x = _linear(value, 0.0, top_value, x0, x1)
        body.append(f'<line x1="{x:.1f}" y1="{top - 8:.1f}" x2="{x:.1f}" y2="{height - 26:.1f}" '
                    f'stroke="{GRID}" stroke-opacity="0.18" stroke-width="1"/>')
        body.append(_text(x, height - 12, f"{value:.0%}", size=10))

    for i, plan in enumerate(rows):
        y = top + i * row_h
        width = _linear(plan.share_moved, 0.0, top_value, x0, x1) - x0
        colour = ACCENT if plan.straddles else INK
        if plan.moved:
            body.append(f'<rect x="{x0}" y="{y:.1f}" width="{max(1.5, width):.1f}" height="18" '
                        f'fill="{colour}" fill-opacity="0.80"/>')
        body.append(_text(x0 - 10, y + 8, f"{plan.plan_id} · {plan.monthly_fee:.0f}/month",
                          anchor="end", size=11, weight="bold"))
        body.append(_text(x0 - 10, y + 22,
                          "straddles a band threshold" if plan.straddles else "never crosses a threshold",
                          anchor="end", size=9, opacity=0.85))
        if plan.moved:
            body.append(_text(x0 + width + 8, y + 13, f"{plan.share_moved:.1%}", anchor="start",
                              size=11, weight="bold", fill=colour))
        else:
            body.append(_text(x0 + 8, y + 13, "not one customer", anchor="start", size=10,
                              fill=POSITIVE))
        body.append(_text(x1 + 20, y + 13, f"{plan.customers:,}", anchor="start", size=9, opacity=0.8))

    body.append(_text(x1 + 20, top - 12, "customers", anchor="start", size=9, opacity=0.85))
    body.append(f'<line x1="{x0}" y1="{top - 8:.1f}" x2="{x0}" y2="{height - 26:.1f}" '
                f'stroke="{INK}" stroke-opacity="0.55" stroke-width="1.2"/>')
    return _svg(body, "Value-band movement by tariff between the two cutoffs", height)
