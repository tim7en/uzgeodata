"""Draw the water flow diagram as SVG, with widths that mean what they look like.

Two decisions carry most of the honesty here.

**Two panels, not one.** The flows span precipitation at 312 km3/yr down to thermal
power at 0.08 -- four orders of magnitude. On one linear scale every human use is a
hairline; on a compressed scale the widths stop being proportional, which in a Sankey
is a lie, because width is the only quantity a Sankey encodes. So the natural balance
and the human use are drawn as separate panels, each linear within itself, with the
shared quantity named on both so a reader can tie them together.

**Colour is provenance.** The published applications of this method colour by water
type. Here colour says how a flow is known -- measured, administered, derived, or not
quantified at all -- because at this scale that is the distinction a reader most needs
and least often gets. A flow nobody has quantified is drawn at a fixed hairline width
with a dashed edge: present, visibly unmeasured, and impossible to mistake for small.

No JavaScript and no chart library. The layout is computed here and the result is an
SVG that renders anywhere, including in a PDF and in a printed report, which is where
diagrams like this usually end up.
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
DATA = FLOW / "regional-water-flow.json"
OUT = FLOW / "regional-water-flow.svg"

WIDTH, NODE_W, GAP = 1180, 13, 16
UNQUANTIFIED_W = 3          # a fixed hairline: visible, and never read as a magnitude


def layered(links, order):
    """Assign each node a column from an explicit order, not from graph depth.

    Explicit because the meaning of a column here is editorial -- source, allocation,
    country, sector, return -- and a depth-first walk would put the gaps and the
    returns in whatever column the graph happened to imply.
    """
    column = {}
    for index, names in enumerate(order):
        for name in names:
            column[name] = index
    return column


def panel(title, subtitle, nodes, links, order, top, scale, height):
    """One linear panel: columns of nodes, ribbons between them."""
    column = layered(links, order)
    label = {node["id"]: node for node in nodes}
    columns = {}
    for name, index in column.items():
        columns.setdefault(index, []).append(name)

    span = (WIDTH - 240) / max(len(order) - 1, 1)
    x = {index: 150 + index * span for index in columns}

    # Vertical placement: each column packs its nodes by the larger of what flows in or
    # out, so a node is never drawn thinner than the ribbon it must carry.
    weight = {}
    for name in column:
        incoming = sum(l["value"] or 0 for l in links if l["target"] == name)
        outgoing = sum(l["value"] or 0 for l in links if l["source"] == name)
        weight[name] = max(incoming, outgoing)

    box, parts = {}, []
    for index, names in sorted(columns.items()):
        names.sort(key=lambda n: -weight[n])
        total = sum(max(weight[n] * scale, UNQUANTIFIED_W) for n in names)
        y = top + max(0, (height - total - GAP * (len(names) - 1)) / 2)
        for name in names:
            h = max(weight[name] * scale, UNQUANTIFIED_W)
            box[name] = {"x": x[index], "y": y, "h": h}
            y += h + GAP

    used = {name: {"in": 0.0, "out": 0.0} for name in column}
    for link in sorted(links, key=lambda l: -(l["value"] or 0)):
        source, target = link["source"], link["target"]
        if source not in box or target not in box:
            continue
        value = link["value"]
        thickness = UNQUANTIFIED_W if value is None else max(value * scale, 1.0)
        sy = box[source]["y"] + used[source]["out"]
        ty = box[target]["y"] + used[target]["in"]
        used[source]["out"] += thickness
        used[target]["in"] += thickness
        x0, x1 = box[source]["x"] + NODE_W, box[target]["x"]
        mid = (x0 + x1) / 2
        colour = COLOUR[link["basis"]]
        dash = ' stroke-dasharray="6 4"' if value is None else ""
        reading = "not quantified" if value is None else f"{value:,.3g} km³/yr"
        tip = f"{link['label']} — {reading} ({link['basis']})"
        if link.get("operation"):
            tip += f"\n{link['operation']}"
        if link.get("note"):
            tip += f"\n{link['note']}"
        parts.append(
            f'<path d="M{x0:.1f},{sy + thickness / 2:.1f} C{mid:.1f},{sy + thickness / 2:.1f} '
            f'{mid:.1f},{ty + thickness / 2:.1f} {x1:.1f},{ty + thickness / 2:.1f}" '
            f'fill="none" stroke="{colour}" stroke-width="{thickness:.1f}" '
            f'stroke-opacity="{0.85 if value is None else 0.42}"{dash}>'
            f'<title>{html.escape(tip)}</title></path>')

    for name, place in box.items():
        entry = label.get(name, {})
        text = entry.get("label", name)
        value = weight[name]
        parts.append(
            f'<rect x="{place["x"]:.1f}" y="{place["y"]:.1f}" width="{NODE_W}" '
            f'height="{max(place["h"], 2):.1f}" rx="2" fill="#2d3748">'
            f'<title>{html.escape(text + (chr(10) + entry["note"] if entry.get("note") else ""))}</title></rect>')
        anchor = "end" if place["x"] < WIDTH / 2 else "start"
        tx = place["x"] - 8 if anchor == "end" else place["x"] + NODE_W + 8
        amount = "" if value == 0 else f' <tspan fill="#4a5568">{value:,.3g}</tspan>'
        parts.append(
            f'<text x="{tx:.1f}" y="{place["y"] + place["h"] / 2 + 4:.1f}" '
            f'text-anchor="{anchor}" font-size="12.5" fill="#1a202c">'
            f'{html.escape(text)}{amount}</text>')

    header = (f'<text x="24" y="{top - 34}" font-size="16" font-weight="600" '
              f'fill="#1a202c">{html.escape(title)}</text>'
              f'<text x="24" y="{top - 16}" font-size="12" fill="#4a5568">'
              f'{html.escape(subtitle)}</text>')
    return header + "".join(parts)


COLOUR = {}


def render(data=DATA, out=OUT):
    report = json.loads(Path(data).read_text(encoding="utf-8"))
    COLOUR.update({key: entry["colour"] for key, entry in report["basis_legend"].items()})
    nodes, links = report["nodes"], report["links"]

    natural = ["precipitation", "evapotranspiration", "surplus", "amu", "syr", "unaccounted"]
    human = ["amu-uz", "uz-use", "sector-agriculture", "sector-municipal", "sector-industry",
             "sector-fisheries", "sector-thermal_power", "sector-other", "wastewater",
             "drainage", "environment", "gap-losses", "gap-groundwater", "gap-untreated"]

    top_links = [l for l in links if l["source"] in natural and l["target"] in natural]
    low_links = [l for l in links if l["source"] in human and l["target"] in human]

    # Each panel is linear within itself; the scales differ and both are stated.
    top_scale = 300 / 312.5
    low_scale = 300 / 16.76

    body = panel(
        "Where the water comes from, and what is taken",
        "22-year mean annual volumes over 965,725 km² (measured) against the 2022 "
        "hydrological year of recorded diversion (administered). 1 mm of width ≈ "
        f"{1 / top_scale:.2f} km³/yr.",
        nodes, top_links,
        [["precipitation"], ["evapotranspiration", "surplus"], ["amu", "syr", "unaccounted"]],
        top=120, scale=top_scale, height=360)

    body += panel(
        "Where Uzbekistan's Amu Darya water goes",
        "Drawn at its own scale: these flows are twenty times smaller than those above. "
        "Sector shares are national, applied to one basin's diversion — proportions, not "
        f"basin measurements. 1 mm of width ≈ {1 / low_scale:.3f} km³/yr.",
        nodes, low_links,
        [["amu-uz"], ["uz-use"],
         ["sector-agriculture", "sector-municipal", "sector-industry", "sector-fisheries",
          "sector-thermal_power", "sector-other", "gap-losses", "gap-groundwater",
          "gap-untreated"],
         ["wastewater", "drainage"], ["environment"]],
        top=640, scale=low_scale, height=420)

    legend, x = [], 24
    for key, entry in report["basis_legend"].items():
        legend.append(
            f'<rect x="{x}" y="1108" width="26" height="11" rx="2" fill="{entry["colour"]}" '
            f'fill-opacity="0.55"/>'
            f'<text x="{x + 32}" y="1118" font-size="12" fill="#1a202c">'
            f'{html.escape(entry["label"])}<title>{html.escape(entry["meaning"])}</title></text>')
        x += 40 + len(entry["label"]) * 7.6
    legend.append(f'<text x="24" y="1142" font-size="11.5" fill="#4a5568">'
                  f'Colour is how a flow is known, not what kind of water it is. '
                  f'Dashed hairlines are flows nobody has quantified — drawn at a fixed '
                  f'width so they are never read as small.</text>')

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} 1165" '
           f'width="{WIDTH}" height="1165" font-family="system-ui, -apple-system, '
           f'Segoe UI, Roboto, sans-serif">'
           f'<rect width="{WIDTH}" height="1165" fill="#fdfdfc"/>'
           f'<text x="24" y="42" font-size="22" font-weight="650" fill="#1a202c">'
           f'Where the region\'s water goes</text>'
           f'<text x="24" y="64" font-size="13" fill="#4a5568">'
           f'Amu Darya and Syr Darya · 7,445 level-12 basins · adapted from the Water '
           f'Flow Diagram method (waterflowdiagram.ch)</text>'
           f'<text x="24" y="84" font-size="12" fill="#9b2c2c">'
           f'This diagram does not close, and is not made to — see the note beneath it.</text>'
           + body + "".join(legend) + '</svg>')
    Path(out).write_text(svg, encoding="utf-8")
    return {"svg": str(out), "bytes": len(svg.encode("utf-8")),
            "links_drawn": len(top_links) + len(low_links), "generated_at": utc_now()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(OUT))
    arguments = parser.parse_args()
    print(json.dumps(render(out=Path(arguments.out)), indent=2))


if __name__ == "__main__":
    main()
