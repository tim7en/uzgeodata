"""Figures for the trend study: the correction cascade, and where the signal sits.

Two figures carry the argument.

The first is the cascade. For each variable, how many basins are called significant
before any correction, after correcting for serial persistence, and after controlling
false discovery across seven thousand simultaneous tests. It is the figure a reader
should see first, because for most variables the third bar is zero and the first is
in the thousands, and no amount of prose makes that as plain.

The second is the stratification: where the surviving signal sits, by basin system,
position, elevation and land cover. Drawn only for the variables that survive, because
a stratified map of a signal that did not survive control is a map of noise arranged
tidily.

Plain SVG, layout computed here, no chart library -- these belong in a paper as much as
in a browser.
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

TRENDS = ROOT / "PUBLISHED/data/trends"
INK, MUTED, GRID = "#1a202c", "#4a5568", "#e2e8e5"
RAW, AUTO, FDR = "#cbd5e0", "#90a6c4", "#1b4d7e"
UP, DOWN = "#1b7f5a", "#9b2c2c"


def cascade(report, out):
    """Significant basins before correction, after each correction."""
    rows = [(identifier, block) for identifier, block in sorted(report["summary"].items())]
    W = 1180
    left, top, row_h = 250, 130, 46
    H = top + len(rows) * row_h + 96
    peak = max(block["significant_uncorrected"] for _, block in rows) or 1
    scale = (W - left - 260) / peak
    tested = [block for _, block in rows if block["significant_uncorrected"] > 0
              or block.get("basins_tested", 0) > 0]
    lost = [block for block in tested if block["significant_after_fdr"] == 0]

    parts = [f'<rect width="{W}" height="{H}" fill="#fdfdfc"/>',
             f'<text x="24" y="40" font-size="19" font-weight="650" fill="{INK}">'
             f'What the corrections do to "significant"</text>',
             f'<text x="24" y="63" font-size="12.5" fill="{MUTED}">'
             f'Basins called significant at α=0.05, of 7,445 tested, for each variable in the '
             f'study: {len(tested)} testable at level 12, plus the two ERA5-Land variables '
             f'withheld as unresolved (their bars stay zero). Left to right: no correction, '
             f'corrected for serial persistence, then controlled for false discovery across '
             f'all basins.</text>',
             f'<text x="24" y="84" font-size="12.5" fill="{DOWN}">'
             f'For {len(lost)} of the {len(tested)} testable variables the third bar is zero.</text>']

    x = left
    for colour, label in ((RAW, "uncorrected"), (AUTO, "serial correlation corrected"),
                          (FDR, "false discovery controlled")):
        parts.append(f'<rect x="{x}" y="{top - 30}" width="20" height="10" rx="2" fill="{colour}"/>')
        parts.append(f'<text x="{x + 26}" y="{top - 21}" font-size="11.5" fill="{INK}">'
                     f'{label}</text>')
        x += 36 + len(label) * 6.6

    y = top
    for identifier, block in rows:
        name = identifier.replace("uz:", "").replace("-monthly-v1", "")
        values = [(block["significant_uncorrected"], RAW),
                  (block["significant_corrected"], AUTO),
                  (block["significant_after_fdr"], FDR)]
        parts.append(f'<text x="{left - 12}" y="{y + 22:.0f}" text-anchor="end" '
                     f'font-size="13" fill="{INK}">{html.escape(name)}</text>')
        bar_y = y + 6
        for value, colour in values:
            width = max(value * scale, 1.5 if value else 0)
            parts.append(f'<rect x="{left}" y="{bar_y:.1f}" width="{width:.1f}" height="9" '
                         f'rx="2" fill="{colour}">'
                         f'<title>{html.escape(f"{name}: {value:,} basins")}</title></rect>')
            if value == 0:
                parts.append(f'<text x="{left + 6}" y="{bar_y + 8:.1f}" font-size="10.5" '
                             f'fill="{DOWN}">none</text>')
            bar_y += 11
        final = block["significant_after_fdr"]
        parts.append(f'<text x="{W - 24}" y="{y + 26:.0f}" text-anchor="end" font-size="12.5" '
                     f'fill="{INK if final else DOWN}">'
                     f'{block["significant_uncorrected"]:,} → <tspan font-weight="650">'
                     f'{final:,}</tspan></text>')
        y += row_h

    parts.append(f'<text x="24" y="{H - 34}" font-size="11.5" fill="{MUTED}">'
                 f'Precipitation is the clearest case: its smallest p-value across all '
                 f'7,445 basins is 0.011, which clears no step-up threshold anywhere.</text>')
    parts.append(f'<text x="24" y="{H - 16}" font-size="11.5" fill="{MUTED}">'
                 f'Soil moisture is a modelled quantity, not an observation — see the '
                 f'caveat in the study text before reading it as drying.</text>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'font-family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif">'
           + "".join(parts) + '</svg>')
    Path(out).write_text(svg, encoding="utf-8")
    return {"svg": str(out), "bytes": len(svg.encode("utf-8"))}


def stratified(report, out, variable="uz:soil-monthly-v1", minimum=30):
    """Share of basins with a surviving signal, by stratum."""
    cells = [c for c in report["cross_tabulation"]
             if c["variable"] == variable and c["basins"] >= minimum]
    cells.sort(key=lambda c: -(c["significant_decrease"] + c["significant_increase"]) / c["basins"])
    W = 1180
    left, top, row_h = 430, 138, 26
    H = top + len(cells) * row_h + 74
    scale = (W - left - 190)

    label = variable.replace("uz:", "").replace("-monthly-v1", "")
    parts = [f'<rect width="{W}" height="{H}" fill="#fdfdfc"/>',
             f'<text x="24" y="40" font-size="19" font-weight="650" fill="{INK}">'
             f'Where the surviving signal sits — {html.escape(label)}</text>',
             f'<text x="24" y="63" font-size="12.5" fill="{MUTED}">'
             f'Share of basins in each stratum whose trend survives both corrections. '
             f'Strata with fewer than {minimum} basins are omitted rather than shown at a '
             f'width their sample cannot support.</text>',
             f'<text x="24" y="84" font-size="12.5" fill="{MUTED}">'
             f'System × position × elevation band × dominant land cover, from the '
             f'published reference atlas.</text>',
             f'<rect x="{left}" y="{top - 26}" width="16" height="9" rx="2" fill="{DOWN}"/>'
             f'<text x="{left + 22}" y="{top - 18}" font-size="11.5" fill="{INK}">'
             f'significant decrease</text>'
             f'<rect x="{left + 160}" y="{top - 26}" width="16" height="9" rx="2" fill="{UP}"/>'
             f'<text x="{left + 182}" y="{top - 18}" font-size="11.5" fill="{INK}">'
             f'significant increase</text>']

    y = top
    for cell in cells:
        text = (f'{cell["system"].replace("_", " ")} · {cell["position"]} · '
                f'{cell["elevation_band"]} · {cell["land_cover"]}')
        parts.append(f'<text x="{left - 10}" y="{y + 13:.0f}" text-anchor="end" '
                     f'font-size="11.5" fill="{INK}">{html.escape(text)}</text>')
        parts.append(f'<rect x="{left}" y="{y + 4:.0f}" width="{scale}" height="12" rx="2" '
                     f'fill="{GRID}"/>')
        offset = 0.0
        for count, colour in ((cell["significant_decrease"], DOWN),
                              (cell["significant_increase"], UP)):
            width = count / cell["basins"] * scale
            if width > 0:
                tip = f"{count} of {cell['basins']} basins"
                parts.append(f'<rect x="{left + offset:.1f}" y="{y + 4:.0f}" '
                             f'width="{width:.1f}" height="12" rx="2" fill="{colour}">'
                             f'<title>{html.escape(tip)}</title></rect>')
            offset += width
        share = (cell["significant_decrease"] + cell["significant_increase"]) / cell["basins"]
        parts.append(f'<text x="{left + scale + 10}" y="{y + 14:.0f}" font-size="11.5" '
                     f'fill="{MUTED}">{share:.0%} of {cell["basins"]}</text>')
        y += row_h

    parts.append(f'<text x="24" y="{H - 30}" font-size="11.5" fill="{MUTED}">'
                 f'Median Sen slope is published per stratum in the downloadable '
                 f'cross-tabulation; the bar shows only how much of each stratum moves.</text>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'font-family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif">'
           + "".join(parts) + '</svg>')
    Path(out).write_text(svg, encoding="utf-8")
    return {"svg": str(out), "bytes": len(svg.encode("utf-8"))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    report = json.loads((TRENDS / "index.json").read_text(encoding="utf-8"))
    figures = {
        "cascade": cascade(report, TRENDS / "trend-correction-cascade.svg"),
        "soil": stratified(report, TRENDS / "trend-strata-soil.svg", "uz:soil-monthly-v1"),
        "tmn": stratified(report, TRENDS / "trend-strata-tmn.svg", "uz:tmn-monthly-v1"),
    }
    print(json.dumps({"figures": figures, "generated_at": utc_now()}, indent=2))


if __name__ == "__main__":
    main()
