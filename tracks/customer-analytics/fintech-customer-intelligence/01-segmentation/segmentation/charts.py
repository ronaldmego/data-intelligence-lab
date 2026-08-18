"""Charts as hand-written SVG — visible on GitHub, deterministic, no dependencies.

Same palette and geometry as cases 02, 03 and 05, so the track reads as one body
of work. Case 03 recorded why these primitives are not a shared module: the
three existing versions had already diverged in their axis helpers, and merging
them would mean re-verifying two committed cases byte for byte to save a hundred
lines. That is still true, and this case adds a fourth divergence rather than
pretending otherwise — none of the charts here have a y-axis at all.

**Height is computed from the content, never fixed.** A canvas taller than what
is drawn on it reads fine inside the repository and badly the moment the file is
embedded in a page, where it scales to the container width and drags its empty
band along proportionally.
"""

from __future__ import annotations

import math

INK = "#8b949e"
GRID = "#8b949e"
PRIMARY = "#4c78a8"    # what the grid gets right
ACCENT = "#e45756"     # what it loses
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
    """Wrap the body in a canvas exactly as tall as what was drawn."""
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


GRID_TEXT = {
    "aria": "The risk-by-value grid and the expected value of each cell",
    "heading": "{cells} cells, {worth} worth contacting",
    "subhead": "expected profit per customer, at case 05's measured save rate",
    "members": "{count:,} customers",
    "churn": "churn {rate:.1%}",
    "risk": ("low risk", "mid risk", "high risk"),
    "value": ("low value", "mid value", "high value"),
    "pad_l": PAD_L,
}

# Same figure, same numbers, Spanish furniture — the same reason case 03 gives for
# `gates.es.svg`: it is embedded in a Spanish-language page, and a figure whose
# caption is in one language and whose labels are in another asks the reader to
# trust what they cannot read.
#
# Segment names are translated too, and they are the tight constraint: they are
# centred in a cell of about 200px and Spanish runs longer, so these are chosen to
# fit rather than to translate literally.
GRID_TEXT_ES = {
    "aria": "La grilla de riesgo por valor y el valor esperado de cada celda",
    "heading": "{cells} celdas, {worth} justifican un contacto",
    "subhead": "beneficio esperado por cliente, con la tasa de retención medida en el caso 05",
    "members": "{count:,} clientes",
    "churn": "abandono {rate:.1%}",
    "risk": ("riesgo bajo", "riesgo medio", "riesgo alto"),
    "value": ("valor bajo", "valor medio", "valor alto"),
    # Wider left gutter than the English figure, and this is the reason: the risk
    # labels are right-aligned against it, and "riesgo medio" is half again as long
    # as "mid risk" — at the shared 62px it ran off the left edge of the canvas.
    # Giving Spanish its own gutter keeps the English file byte-for-byte unchanged.
    "pad_l": 84,
}

SEGMENT_NAMES_ES = {
    "Rescue": "Rescatar",
    "Rescue (economy)": "Rescatar (económico)",
    "Let go": "Dejar ir",
    "Protect": "Proteger",
    "Watch": "Observar",
    "Reprice": "Reajustar producto",
    "Grow": "Crecer",
    "Grow (limit)": "Crecer (cupo)",
    "Self-serve": "Autogestión",
}


def grid_chart(segments, bands: int = 3, text: dict | None = None,
               names: dict[str, str] | None = None) -> str:
    """The grid itself, and the handful of cells that pay for a contact.

    The deliverable of a segmentation is usually presented as the segments. It
    is at least as much the *absence* of them: most cells carry a negative
    expected value per customer, and "do not contact these people" is the part
    of the output that survives meeting a budget.
    """
    text = text or GRID_TEXT
    names = names or {}
    pad_l = text.get("pad_l", PAD_L)
    by_key = {s.key: s for s in segments}
    cell_w = (W - pad_l - PAD_R) / bands
    cell_h = 92.0
    top = PAD_T + 26
    height = top + bands * cell_h + 44

    worth = sum(1 for s in segments if s.worth_contacting)
    body = [_text(18, 20, text["heading"].format(cells=len(segments), worth=worth),
                  anchor="start", size=13)]
    body.append(_text(18, 36, text["subhead"], anchor="start", size=10))

    for row in range(bands):                       # risk: highest band on top
        risk_band = bands - 1 - row
        for column in range(bands):                # value: lowest on the left
            segment = by_key.get((risk_band, column))
            x = pad_l + column * cell_w
            y = top + row * cell_h
            if segment is None:
                continue
            positive = segment.worth_contacting
            colour = POSITIVE if positive else INK
            body.append(
                f'<rect x="{x + 3:.1f}" y="{y + 3:.1f}" width="{cell_w - 6:.1f}" '
                f'height="{cell_h - 6:.1f}" fill="{colour}" '
                f'fill-opacity="{0.16 if positive else 0.06}" '
                f'stroke="{colour}" stroke-opacity="{0.55 if positive else 0.22}" stroke-width="1"/>'
            )
            centre = x + cell_w / 2
            body.append(_text(centre, y + 26, names.get(segment.name, segment.name),
                              size=12, weight="bold",
                              fill=INK if positive else INK, opacity=1.0 if positive else 0.75))
            body.append(_text(centre, y + 45, text["members"].format(count=len(segment)), size=10))
            body.append(_text(centre, y + 66, f"{segment.expected_value_per_customer:+.2f}",
                              size=15, weight="bold", fill=POSITIVE if positive else ACCENT))
            body.append(_text(centre, y + 81,
                              text["churn"].format(rate=segment.realised_churn), size=9))

    for row in range(bands):
        label = text["risk"][bands - 1 - row]
        body.append(_text(pad_l - 10, top + row * cell_h + cell_h / 2, label,
                          anchor="end", size=10))
    for column in range(bands):
        label = text["value"][column]
        body.append(_text(pad_l + column * cell_w + cell_w / 2, top + bands * cell_h + 18,
                          label, size=10))

    return _svg(body, text["aria"], height)


def axes_chart(letters, repaired) -> str:
    """What each RFM dimension is worth on a subscription.

    Two panels because they are two different failures: a dimension can carry no
    variation at all, or carry plenty and still not separate the outcome.
    """
    rows = [*letters, repaired]
    row_h = 44.0
    top = PAD_T + 40
    height = top + len(rows) * row_h + 30

    bar_x0, bar_x1 = 250, 430
    dot_x0, dot_x1 = 500, W - PAD_R - 46
    top_spread = max([letter.readable_spread for letter in rows] + [0.01]) * 1.25

    body = [_text(18, 20, "What each dimension is worth in a subscription", anchor="start", size=13)]
    body.append(_text((bar_x0 + bar_x1) / 2, PAD_T + 22, "share of the base on one value", size=10))
    body.append(_text((dot_x0 + dot_x1) / 2, PAD_T + 22, "churn gap, top vs bottom fifth", size=10))

    for i, letter in enumerate(rows):
        y = top + i * row_h
        body.append(_text(18, y + 14, f"{letter.symbol} · {letter.name}", anchor="start",
                          size=11, weight="bold"))
        body.append(_text(18, y + 28, letter.short, anchor="start", size=9, opacity=0.85))

        width = _linear(letter.modal_share, 0.0, 1.0, bar_x0, bar_x1) - bar_x0
        colour = ACCENT if letter.degenerate else PRIMARY
        body.append(f'<rect x="{bar_x0}" y="{y + 4:.1f}" width="{max(1.0, width):.1f}" '
                    f'height="16" fill="{colour}" fill-opacity="0.32"/>')
        share = "<1%" if letter.modal_share < 0.005 else f"{letter.modal_share:.0%}"
        # Past ~90% the bar reaches the panel divider, so the label goes inside
        # it rather than on top of the rule.
        inside = width > (bar_x1 - bar_x0) * 0.90
        body.append(_text(bar_x0 + width + (-6 if inside else 6), y + 17, share,
                          anchor="end" if inside else "start", size=10, fill=colour))
        body.append(_text(bar_x0 - 8, y + 17, f"{letter.distinct:,} distinct", anchor="end", size=9))

        spread = letter.readable_spread
        cx = _linear(spread, 0.0, top_spread, dot_x0, dot_x1)
        if letter.quintiles_separate:
            body.append(f'<circle cx="{cx:.1f}" cy="{y + 12:.1f}" r="5.5" fill="{PRIMARY}"/>')
            body.append(_text(cx + 10, y + 16, f"{spread:.1%}", anchor="start", size=10))
        else:
            body.append(f'<line x1="{dot_x0 - 4:.1f}" y1="{y + 12:.1f}" x2="{dot_x0 + 4:.1f}" '
                        f'y2="{y + 12:.1f}" stroke="{ACCENT}" stroke-width="2.5"/>')
            body.append(_text(dot_x0 + 12, y + 16, "no variation to read",
                              anchor="start", size=10, fill=ACCENT))

    body.append(f'<line x1="{(bar_x1 + dot_x0) / 2:.1f}" y1="{PAD_T + 30}" '
                f'x2="{(bar_x1 + dot_x0) / 2:.1f}" y2="{height - 24:.1f}" '
                f'stroke="{GRID}" stroke-opacity="0.25" stroke-width="1"/>')
    return _svg(body, "Variation and separation of each RFM dimension", height)


def drift_chart(migration) -> str:
    """The aggregate holds still while the individuals underneath do not."""
    entries = [
        ("customers who changed cell", migration.share(migration.cell_changed), ACCENT),
        ("… because their risk band moved", migration.share(migration.risk_band_changed), ACCENT),
        ("… because their value band moved", migration.share(migration.value_band_changed), MUTED),
        ("customers whose contact decision flipped", migration.share(migration.contact_decision_changed), PRIMARY),
        ("largest change in any segment's size", migration.size_drift, POSITIVE),
    ]
    row_h = 40.0
    top = PAD_T + 30
    height = top + len(entries) * row_h + 34
    x0, x1 = 330, W - PAD_R - 52
    top_value = max(value for _, value, _ in entries) * 1.18

    body = [_text(18, 20, "Six months later: the report is stable, the customers are not",
                  anchor="start", size=13)]
    body.append(_text(18, 36, f"same rule applied at both cutoffs, {migration.n:,} customers present in both "
                              f"({migration.basis})", anchor="start", size=10))

    for value in _nice_ticks(0.0, top_value):
        x = _linear(value, 0.0, top_value, x0, x1)
        body.append(f'<line x1="{x:.1f}" y1="{top - 6:.1f}" x2="{x:.1f}" y2="{height - 28:.1f}" '
                    f'stroke="{GRID}" stroke-opacity="0.18" stroke-width="1"/>')
        body.append(_text(x, height - 14, f"{value:.0%}", size=10))

    for i, (label, value, colour) in enumerate(entries):
        y = top + i * row_h
        width = _linear(value, 0.0, top_value, x0, x1) - x0
        body.append(f'<rect x="{x0}" y="{y:.1f}" width="{max(1.5, width):.1f}" height="20" '
                    f'fill="{colour}" fill-opacity="0.80"/>')
        body.append(_text(x0 - 10, y + 15, label, anchor="end", size=11))
        body.append(_text(x0 + width + 8, y + 15, f"{value:.1%}", anchor="start", size=11,
                          weight="bold", fill=colour))

    body.append(f'<line x1="{x0}" y1="{top - 6:.1f}" x2="{x0}" y2="{height - 28:.1f}" '
                f'stroke="{INK}" stroke-opacity="0.55" stroke-width="1.2"/>')
    return _svg(body, "Segment migration between the two observation cutoffs", height)


def reach_chart(rows) -> str:
    """Whether each play can be delivered, and which kind of rule refuses it."""
    row_h = 46.0
    top = PAD_T + 34
    height = top + len(rows) * row_h + 46
    x0, x1 = 210, W - PAD_R - 40

    body = [_text(18, 20, "Can the action reach the segment it was written for?",
                  anchor="start", size=13)]
    body.append(_text(18, 36, "judged against case 03's permission layer, per offer type",
                      anchor="start", size=10))

    for row_index, row in enumerate(rows):
        y = top + row_index * row_h
        total = max(1, row.members)
        pieces = [
            (row.reachable, POSITIVE, "reachable"),
            (row.blocked_by_policy, PRIMARY, "out of policy"),
            (row.blocked_by_eligibility, ACCENT, "ineligible"),
        ]
        x = float(x0)
        for count, colour, _ in pieces:
            width = (count / total) * (x1 - x0)
            if width > 0:
                body.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="20" '
                            f'fill="{colour}" fill-opacity="0.80"/>')
                if width > 34:
                    body.append(_text(x + width / 2, y + 15, f"{count:,}", size=10, fill="#ffffff"))
            x += width
        body.append(_text(x0 - 10, y + 10, row.segment, anchor="end", size=11, weight="bold"))
        article = "an" if row.offer_type[:1].lower() in "aeiou" else "a"
        body.append(_text(x0 - 10, y + 24, f"send {article} {row.offer_type.replace('_', ' ')}",
                          anchor="end", size=9, opacity=0.85))
        body.append(_text(x1 + 8, y + 15, f"{row.reach:.0%}", anchor="start", size=11,
                          weight="bold", fill=POSITIVE if row.reach >= 0.5 else ACCENT))

    legend_y = height - 22
    legend = ((POSITIVE, "reachable"), (PRIMARY, "refused by contact policy"),
              (ACCENT, "refused by the catalogue"))
    # Laid out from the left margin with a measured stride, so the last entry
    # ends inside the canvas instead of being cropped by the viewBox.
    stride = (W - PAD_R - 30 - PAD_L) / len(legend)
    for i, (colour, label) in enumerate(legend):
        x = PAD_L + i * stride
        body.append(f'<rect x="{x:.1f}" y="{legend_y - 9}" width="12" height="12" '
                    f'fill="{colour}" fill-opacity="0.80"/>')
        body.append(_text(x + 17, legend_y + 1, label, anchor="start", size=9))

    return _svg(body, "Deliverability of each segment's action", height)
