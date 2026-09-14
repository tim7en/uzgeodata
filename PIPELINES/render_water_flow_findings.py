"""Two figures: what the record shows, and what would have to change.

The first is a plot and not a diagram. The water flow diagram shows a mean year, and a
mean year is the one condition under which this system is comfortable. Everything
interesting is in the spread, so the spread gets its own figure: twenty-two years of
climatic surplus with the recorded diversion drawn across them as a flat line, because
allocation does not vary with the weather. Where the line crosses the bars is the
finding.

The second is a pathway rather than a Sankey. It is drawn from what is missing rather
than from what is known, so each step names the gap it closes and who can close it --
and the steps are ordered by whether the next one is possible without them. There is no
point modelling distribution losses before anyone measures a distribution loss.

Both are plain SVG with the layout computed here, for the same reason as the diagram:
these end up in reports and slide decks, not only in browsers.
"""
from __future__ import annotations
import argparse
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import utc_now

FLOW = ROOT / "PUBLISHED/data/water-flow"
SENSITIVITY = FLOW / "regional-water-flow-sensitivity.json"

GREEN, BLUE, AMBER, RED, INK, MUTED = "#1b7f5a", "#2b6cb0", "#b7791f", "#9b2c2c", "#1a202c", "#4a5568"


def sensitivity_chart(data, out):
    report = json.loads(Path(data).read_text(encoding="utf-8"))
    observed = report["observed"]
    annual = observed["annual"]
    diversion = observed["diversion_km3"]
    threshold = report["stress_threshold"]

    W, H = 1180, 470
    left, right, top, bottom = 70, 40, 96, 74
    plot_w, plot_h = W - left - right, H - top - bottom
    peak = max(row["surplus"] for row in annual) * 1.08
    step = plot_w / len(annual)
    bar_w = step * 0.62

    def y_of(value):
        return top + plot_h - (value / peak) * plot_h

    parts = [f'<rect width="{W}" height="{H}" fill="#fdfdfc"/>',
             f'<text x="24" y="34" font-size="18" font-weight="640" fill="{INK}">'
             f'The mean year is the comfortable one</text>',
             f'<text x="24" y="56" font-size="12.5" fill="{MUTED}">'
             f'Climatic surplus by year (precipitation less evapotranspiration, measured) '
             f'against the 2022 recorded diversion (administered, held flat — allocation '
             f'does not vary with the weather).</text>',
             f'<text x="24" y="74" font-size="12.5" fill="{RED}">'
             f'In {" and ".join(str(y) for y in observed["exceeded_years"])} the region '
             f'diverted more than the surplus generated inside the basin.</text>']

    for fraction in (0, 0.25, 0.5, 0.75, 1.0):
        value = peak * fraction
        y = y_of(value)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{W - right}" y2="{y:.1f}" '
                     f'stroke="#e2e8e5"/>')
        parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" '
                     f'font-size="11" fill="{MUTED}">{value:.0f}</text>')
    parts.append(f'<text x="20" y="{top - 10}" font-size="11" fill="{MUTED}">km³/yr</text>')

    for index, row in enumerate(annual):
        x = left + index * step + (step - bar_w) / 2
        y = y_of(row["surplus"])
        colour = RED if row["exceeded"] else (AMBER if row["stressed"] else GREEN)
        tip = (f'{row["year"]}: surplus {row["surplus"]} km³/yr, '
               f'diversion is {row["diversion_share"]:.0%} of it')
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
                     f'height="{top + plot_h - y:.1f}" fill="{colour}" fill-opacity="0.72" rx="2">'
                     f'<title>{html.escape(tip)}</title></rect>')
        if row["year"] % 2 == 1:
            parts.append(f'<text x="{x + bar_w / 2:.1f}" y="{top + plot_h + 16:.1f}" '
                         f'text-anchor="middle" font-size="10.5" fill="{MUTED}">'
                         f'{str(row["year"])[2:]}</text>')

    y_div = y_of(diversion)
    parts.append(f'<line x1="{left}" y1="{y_div:.1f}" x2="{W - right}" y2="{y_div:.1f}" '
                 f'stroke="{BLUE}" stroke-width="2.5"/>')
    parts.append(f'<text x="{W - right - 6}" y="{y_div - 8:.1f}" text-anchor="end" '
                 f'font-size="12" font-weight="600" fill="{BLUE}">'
                 f'Recorded diversion {diversion} km³/yr (2022)</text>')
    y_stress = y_of(diversion / threshold)
    parts.append(f'<line x1="{left}" y1="{y_stress:.1f}" x2="{W - right}" y2="{y_stress:.1f}" '
                 f'stroke="{AMBER}" stroke-width="1.5" stroke-dasharray="7 5"/>')
    parts.append(f'<text x="{W - right - 6}" y="{y_stress - 7:.1f}" text-anchor="end" '
                 f'font-size="11.5" fill="{AMBER}">'
                 f'Diversion at {threshold:.0%} of surplus — thin margin above this line</text>')

    legend = [(GREEN, "comfortable"), (AMBER, f"diversion ≥ {threshold:.0%} of surplus"),
              (RED, "diversion exceeded surplus")]
    x = left
    for colour, label in legend:
        parts.append(f'<rect x="{x}" y="{H - 34}" width="22" height="10" rx="2" '
                     f'fill="{colour}" fill-opacity="0.72"/>')
        parts.append(f'<text x="{x + 28}" y="{H - 25}" font-size="11.5" fill="{INK}">'
                     f'{html.escape(label)}</text>')
        x += 42 + len(label) * 6.4
    trend = observed["trend_km3_per_year"]["surplus"]
    halves = observed["halves_km3"]
    parts.append(f'<text x="24" y="{H - 8}" font-size="11.5" fill="{MUTED}">'
                 f'Surplus slope {trend:+.2f} km³/yr per year; first half of the record '
                 f'{halves["first"]} km³/yr, second half {halves["second"]} '
                 f'({halves["change_percent"]:+.0f}%). A slope over 22 years describes this '
                 f'record, not a cause.</text>')

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'font-family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif">'
           + "".join(parts) + '</svg>')
    Path(out).write_text(svg, encoding="utf-8")
    return {"svg": str(out), "bytes": len(svg.encode("utf-8"))}


STEPS = [
    ("1", "Publish withdrawal by basin and sector",
     "ICWC / BWO Amu Darya & Syr Darya",
     "The single change that unlocks everything below. Diversion is recorded by country "
     "and canal; nothing here can be attributed to a catchment until it is also recorded "
     "by one.", "unlocks every step that follows", BLUE),
    ("2", "Measure distribution losses once",
     "Ministry of Water Resources, vodokanals",
     "The method's own applications usually find this the largest single lever. The 2023 "
     "national plan sets a 10 per cent reduction target with no published baseline, so "
     "the target cannot be evaluated even in principle.", "makes the largest lever visible", AMBER),
    ("3", "Report groundwater abstraction",
     "State Committee on Geology, Ministry of Water Resources",
     "Usable groundwater is given nationally as 0.5 km³/yr against an estimated 27.6 "
     "km³/yr yield. Without abstraction figures, substitution between surface and "
     "groundwater is invisible, and a surface-water saving may be a groundwater cost.",
     "separates a saving from a substitution", AMBER),
    ("4", "Publish generated as well as treated wastewater",
     "Vodokanals, Uzsuvtaminot",
     "The inventory holds what 53 plants treat. What is generated and never reaches a "
     "plant is the quantity that determines whether a river is receiving it.",
     "turns a treatment figure into a sanitation one", GREEN),
    ("5", "Extend the diversion record across years",
     "SIC ICWC, academic partners",
     "One transcribed year is drawn against twenty-two measured ones. ICWC publishes "
     "limits and actuals annually; digitising the series would let allocation and supply "
     "be compared year by year instead of once.", "makes the comparison a time series", GREEN),
    ("6", "Reconcile the models against gauges",
     "Uzhydromet, universities",
     "Runoff at 153.7 km³/yr exceeds the surplus at 93.3: two products on different grids "
     "disagree by more than the entire municipal sector. Gauge records exist and are the "
     "only way to say which is closer.", "closes the diagram", RED),
]


def pathway_chart(out):
    W = 1180
    card_h, gap = 118, 16
    H = 120 + len(STEPS) * (card_h + gap)
    parts = [f'<rect width="{W}" height="{H}" fill="#fdfdfc"/>',
             f'<text x="24" y="36" font-size="18" font-weight="640" fill="{INK}">'
             f'What would have to change, and who can change it</text>',
             f'<text x="24" y="58" font-size="12.5" fill="{MUTED}">'
             f'Ordered by dependency, not by ambition. Each step names the gap it closes; '
             f'the first is a precondition for most of the rest.</text>',
             f'<text x="24" y="78" font-size="12" fill="{MUTED}">'
             f'None of these require new instruments. Every one is a matter of publishing '
             f'something that is already recorded somewhere.</text>']

    y = 104
    for number, title, who, why, unlocks, colour in STEPS:
        parts.append(f'<rect x="24" y="{y}" width="{W - 48}" height="{card_h}" rx="8" '
                     f'fill="#f7f9f8" stroke="#e2e8e5"/>')
        parts.append(f'<rect x="24" y="{y}" width="5" height="{card_h}" rx="2.5" fill="{colour}"/>')
        parts.append(f'<circle cx="58" cy="{y + 32}" r="15" fill="{colour}" fill-opacity="0.14"/>')
        parts.append(f'<text x="58" y="{y + 37}" text-anchor="middle" font-size="15" '
                     f'font-weight="700" fill="{colour}">{number}</text>')
        parts.append(f'<text x="86" y="{y + 28}" font-size="15" font-weight="620" fill="{INK}">'
                     f'{html.escape(title)}</text>')
        parts.append(f'<text x="86" y="{y + 48}" font-size="12" fill="{colour}" '
                     f'font-weight="600">{html.escape(who)}</text>')
        words, line, lines = why.split(), "", []
        for word in words:
            if len(line) + len(word) > 118:
                lines.append(line); line = word
            else:
                line = f"{line} {word}".strip()
        lines.append(line)
        for index, text in enumerate(lines[:3]):
            parts.append(f'<text x="86" y="{y + 68 + index * 15}" font-size="12" '
                         f'fill="{MUTED}">{html.escape(text)}</text>')
        parts.append(f'<text x="{W - 48}" y="{y + card_h - 12}" text-anchor="end" '
                     f'font-size="11.5" font-style="italic" fill="{colour}">'
                     f'{html.escape(unlocks)}</text>')
        if number != STEPS[-1][0]:
            parts.append(f'<path d="M{W / 2},{y + card_h} l0,{gap - 5}" stroke="#cbd5d0" '
                         f'stroke-width="1.5"/>')
        y += card_h + gap

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'font-family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif">'
           + "".join(parts) + '</svg>')
    Path(out).write_text(svg, encoding="utf-8")
    return {"svg": str(out), "bytes": len(svg.encode("utf-8"))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    one = sensitivity_chart(SENSITIVITY, FLOW / "regional-water-flow-sensitivity.svg")
    two = pathway_chart(FLOW / "regional-water-flow-pathway.svg")
    print(json.dumps({"sensitivity": one, "pathway": two, "generated_at": utc_now()}, indent=2))


if __name__ == "__main__":
    main()
