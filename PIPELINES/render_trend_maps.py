"""Choropleth maps of the trend verdicts, drawn from the published geometry.

A table of counts says 46 per cent of basins; a map says which ones, and whether they
form a pattern or are scattered. Both are needed and neither substitutes.

Three decisions shape what these show.

**The verdict mapped is the corrected one.** Colour comes from the false-discovery
controlled class, not the raw p-value, so the map matches the numbers in the study
rather than the more dramatic ones a naive test would give. A map of uncorrected
significance would be the same data telling a different story.

**Withheld basins are drawn, not omitted.** A basin that holds too few source cells to
be tested is painted in its own neutral hatch rather than left white, because a white
gap on a choropleth reads as "no trend" and this is "no answer". For ERA5-Land at
level 12 that means the entire map is withheld, which is the honest picture of what
that product can say at that scale.

**Geometry is simplified, and the tolerance is stated.** 470,000 coordinate pairs will
not inline into a page. Douglas-Peucker at a stated tolerance is applied and the point
count before and after is reported, so a reader knows the outlines are indicative and
by how much. Simplification is never applied to the values, only to the drawing.
"""
from __future__ import annotations
import argparse
import html
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import utc_now

TRENDS = ROOT / "PUBLISHED/data/trends"
HYDRO = ROOT / "PUBLISHED/data/hydroclimate"

# Diverging, colour-blind safe, with the two significant classes clearly separated from
# the two non-significant ones -- the distinction the study is about.
COLOUR = {
    "significant decrease": "#b2182b",
    "decrease": "#f4a582",
    "stable": "#f7f7f7",
    "increase": "#a6cee3",
    "significant increase": "#2166ac",
    None: "#d9d9d9",              # tested, no verdict
}
WITHHELD = "#e8e6e3"              # not tested: too few source cells


def simplify(points, tolerance):
    """Douglas-Peucker. Drawing only; values are never simplified."""
    if len(points) < 3:
        return points
    first, last = points[0], points[-1]
    index, worst = 0, 0.0
    for i in range(1, len(points) - 1):
        d = _perpendicular(points[i], first, last)
        if d > worst:
            index, worst = i, d
    if worst > tolerance:
        left = simplify(points[:index + 1], tolerance)
        right = simplify(points[index:], tolerance)
        return left[:-1] + right
    return [first, last]


def _perpendicular(point, start, end):
    (x, y), (x1, y1), (x2, y2) = point, start, end
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def rings(geometry):
    if geometry["type"] == "Polygon":
        return geometry["coordinates"]
    return [ring for polygon in geometry["coordinates"] for ring in polygon]


def render(level, variable, verdicts, withheld, out, tolerance=0.01, width=1180):
    collection = json.loads((HYDRO / f"basins-level{int(level):02d}.geojson")
                            .read_text(encoding="utf-8"))
    features = collection["features"]

    west = min(x for f in features for r in rings(f["geometry"]) for x, _ in r)
    east = max(x for f in features for r in rings(f["geometry"]) for x, _ in r)
    south = min(y for f in features for r in rings(f["geometry"]) for _, y in r)
    north = max(y for f in features for r in rings(f["geometry"]) for _, y in r)
    # Equirectangular with a cosine correction at the mid-latitude: adequate for a
    # regional figure and honest about being a figure rather than a projection anyone
    # should measure from.
    stretch = math.cos(math.radians((south + north) / 2))
    top, pad = 118, 20
    scale = (width - 2 * pad) / ((east - west) * stretch)
    height = int((north - south) * scale) + top + 76

    def place(x, y):
        return (pad + (x - west) * stretch * scale, top + (north - y) * scale)

    before = after = 0
    paths, counts = [], {}
    for feature in features:
        basin = str(feature["properties"]["HYBAS_ID"])
        if basin in withheld:
            fill, verdict = WITHHELD, "withheld"
        else:
            verdict = verdicts.get(basin)
            fill = COLOUR.get(verdict, COLOUR[None])
        counts[verdict] = counts.get(verdict, 0) + 1
        segments = []
        for ring in rings(feature["geometry"]):
            before += len(ring)
            reduced = simplify(ring, tolerance)
            after += len(reduced)
            if len(reduced) < 3:
                continue
            points = [place(x, y) for x, y in reduced]
            segments.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in points) + "Z")
        if segments:
            paths.append(f'<path d="{"".join(segments)}" fill="{fill}" stroke="#ffffff" '
                         f'stroke-width="0.25"><title>{html.escape(basin + ": " + str(verdict))}'
                         f'</title></path>')

    name = variable.replace("uz:", "").replace("-monthly-v1", "")
    legend, x = [], pad
    order = ["significant decrease", "decrease", "stable", "increase",
             "significant increase"]
    for verdict in order:
        if not counts.get(verdict):
            continue
        legend.append(f'<rect x="{x}" y="{height - 52}" width="20" height="11" rx="2" '
                      f'fill="{COLOUR[verdict]}" stroke="#cbd5d0" stroke-width="0.5"/>'
                      f'<text x="{x + 26}" y="{height - 43}" font-size="11.5" '
                      f'fill="#1a202c">{verdict} ({counts[verdict]:,})</text>')
        x += 42 + len(verdict) * 6.7 + len(str(counts[verdict])) * 7
    if counts.get("withheld"):
        legend.append(f'<rect x="{x}" y="{height - 52}" width="20" height="11" rx="2" '
                      f'fill="{WITHHELD}" stroke="#cbd5d0" stroke-width="0.5"/>'
                      f'<text x="{x + 26}" y="{height - 43}" font-size="11.5" '
                      f'fill="#9b2c2c">withheld, too few source cells '
                      f'({counts["withheld"]:,})</text>')

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
           f'font-family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif">'
           f'<rect width="{width}" height="{height}" fill="#fdfdfc"/>'
           f'<text x="{pad}" y="40" font-size="18" font-weight="640" fill="#1a202c">'
           f'{html.escape(name)} — trend by basin, level {level}</text>'
           f'<text x="{pad}" y="62" font-size="12.5" fill="#4a5568">'
           f'Verdicts after correction for serial persistence and false discovery across '
           f'all tested basins. 2003–2024 annual values, Mann–Kendall with Sen slope.</text>'
           f'<text x="{pad}" y="82" font-size="12" fill="#4a5568">'
           f'Outlines simplified for drawing at {tolerance}° tolerance '
           f'({before:,} → {after:,} points); values are not simplified.</text>'
           f'<text x="{pad}" y="100" font-size="11.5" fill="#718096">'
           f'Equirectangular with a cosine correction at the mid-latitude — a figure, '
           f'not a projection to measure from.</text>'
           + "".join(paths) + "".join(legend) + '</svg>')
    Path(out).write_text(svg, encoding="utf-8")
    return {"svg": str(out), "bytes": len(svg.encode("utf-8")), "features": len(features),
            "points": {"before": before, "after": after}, "counts": counts}


def load(level, variable):
    folder = TRENDS if str(level) == "12" else TRENDS / f"level{level}"
    path = folder / f"{variable.replace(':', '-').replace('/', '-')}.json"
    if not path.is_file():
        return {}, set(), None
    block = json.loads(path.read_text(encoding="utf-8"))
    verdicts = {row["basin_id"]: row["trend_fdr"] for row in block["results"]}
    tested = set(verdicts)
    geometry = json.loads((HYDRO / f"basins-level{int(level):02d}.geojson")
                          .read_text(encoding="utf-8"))
    everything = {str(f["properties"]["HYBAS_ID"]) for f in geometry["features"]}
    return verdicts, everything - tested, block


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", default="7", choices=("7", "12"))
    parser.add_argument("--tolerance", type=float, default=0.01)
    parser.add_argument("--variables", nargs="*")
    arguments = parser.parse_args()

    index = json.loads((TRENDS / ("index.json" if arguments.level == "12"
                                  else f"level{arguments.level}/index.json")
                        ).read_text(encoding="utf-8"))
    wanted = arguments.variables or sorted(index["summary"])
    out = TRENDS / "maps"
    out.mkdir(parents=True, exist_ok=True)
    made = {}
    for variable in wanted:
        verdicts, withheld, block = load(arguments.level, variable)
        name = variable.replace("uz:", "").replace("-monthly-v1", "")
        target = out / f"trend-map-{name}-level{arguments.level}.svg"
        made[variable] = render(arguments.level, variable, verdicts, withheld, target,
                                tolerance=arguments.tolerance)
        print(f"{name:8s} level {arguments.level}  {made[variable]['bytes'] / 1000:6.0f} kB  "
              f"{made[variable]['points']['before']:,} -> {made[variable]['points']['after']:,} pts")
    print(json.dumps({"generated_at": utc_now(), "level": arguments.level,
                      "maps": len(made)}, indent=2))


if __name__ == "__main__":
    main()
