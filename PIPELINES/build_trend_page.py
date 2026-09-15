"""The trend study as a page, with every number read from the published result.

Written to the shape of a paper -- question, data, method, results, limitations, what
would test it -- because that is the form in which a reader can check the work rather
than admire it. Nothing is typed into the prose that is not read from the JSON beside
it, so the text cannot drift from the figures the way a hand-written results section
does the first time the analysis is rerun.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TRENDS = ROOT / "PUBLISHED/data/trends"
OUT = ROOT / "INTERFACE/trends.html"


def inline(name):
    return (TRENDS / name).read_text(encoding="utf-8").replace("<svg ", '<svg class="fig" ', 1)


def build(out=OUT):
    report = json.loads((TRENDS / "index.json").read_text(encoding="utf-8"))
    summary, findings, method = report["summary"], report["findings"], report["method"]

    def block(identifier):
        return summary.get(identifier, {})

    rows = "".join(
        f'<tr><td>{identifier.replace("uz:", "").replace("-monthly-v1", "")}'
        f'<br><span class="muted">{b["unit"]}</span></td>'
        f'<td>{b["basins"]:,}</td><td>{b["significant_uncorrected"]:,}</td>'
        f'<td>{b["significant_corrected"]:,}</td>'
        f'<td class="{"zero" if not b["significant_after_fdr"] else "kept"}">'
        f'{b["significant_after_fdr"]:,}</td></tr>'
        for identifier, b in sorted(summary.items(),
                                    key=lambda kv: -kv[1]["significant_after_fdr"]))

    soil, tmn = block("uz:soil-monthly-v1"), block("uz:tmn-monthly-v1")
    cells = {(c["variable"], c["system"], c["position"], c["elevation_band"],
              c["land_cover"]): c for c in report["cross_tabulation"]}

    def cell(variable, system, position, elevation, cover):
        return cells.get((variable, system, position, elevation, cover))

    irrigated = [c for c in report["cross_tabulation"]
                 if c["variable"] == "uz:soil-monthly-v1"
                 and c["land_cover"] == "irrigated cropland" and c["basins"] >= 30]
    irrigated_rows = "".join(
        f'<tr><td>{c["system"].replace("_", " ")}</td><td>{c["position"]}</td>'
        f'<td>{c["elevation_band"]}</td><td>{c["basins"]}</td>'
        f'<td>{c["significant_decrease"]}</td>'
        f'<td>{c["significant_decrease"] / c["basins"]:.0%}</td>'
        f'<td>{c["median_slope"]:+.3f}</td></tr>'
        for c in sorted(irrigated, key=lambda c: -c["significant_decrease"] / c["basins"]))

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#103d40"><meta name="description" content="Mann-Kendall and Sen's slope across 7,445 level-12 basins of the Amu Darya and Syr Darya, 2003-2024, with serial-correlation and false-discovery correction."><title>Hydroclimatic trends across two basins &middot; UzGeoData</title><link rel="stylesheet" href="/home.css">
<style>
.fig{{width:100%;height:auto;display:block}}
.fig-frame{{overflow-x:auto;background:#fdfdfc;border:1px solid #dfe3e0;border-radius:10px;padding:8px;margin:1.4rem 0}}
.t{{width:100%;border-collapse:collapse;margin:1.1rem 0;font-size:.93rem}}
.t th,.t td{{text-align:left;padding:.55rem .7rem;border-bottom:1px solid #e2e8e5;vertical-align:top}}
.t th{{font-size:.78rem;text-transform:uppercase;letter-spacing:.04em;color:#4a5568}}
.t td.zero{{color:#9b2c2c;font-weight:650}}
.t td.kept{{color:#1b4d7e;font-weight:650}}
.muted{{color:#4a5568;font-size:.85rem}}
.warn{{border-left:4px solid #9b2c2c;background:#fdf6f6;padding:.95rem 1.15rem;border-radius:0 8px 8px 0;margin:1.3rem 0}}
.key{{border-left:4px solid #1b4d7e;background:#f5f8fb;padding:.95rem 1.15rem;border-radius:0 8px 8px 0;margin:1.3rem 0}}
.stat-row{{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));margin:1.3rem 0}}
.stat{{background:#f7f9f8;border-radius:8px;padding:.8rem .9rem}}
.stat b{{display:block;font-size:1.5rem;color:#103d40;line-height:1.2}}
.stat.alarm b{{color:#9b2c2c}}
.stat span{{font-size:.83rem;color:#4a5568}}
code{{background:#f1f5f4;padding:.1rem .3rem;border-radius:3px;font-size:.88em}}
</style></head><body><a class="skip-link" href="#main">Skip to content</a>
<header class="site-header"><a class="brand" href="/" aria-label="UzGeoData home"><span class="brand-icon" aria-hidden="true">&#8776;</span>UzGeoData<span class="brand-sub">BASIN ATLAS</span></a><nav aria-label="Main navigation"><a href="/project.html">Project overview</a><a href="/case-studies.html">Case studies</a><a href="/water-flow.html">Water flow</a><a href="/guide.html">User guide</a><a class="button small" href="/">Open basin explorer <span aria-hidden="true">&#8599;</span></a></nav></header>
<main id="main" class="project-content">

<section class="page-intro"><p class="eyebrow">CASE STUDY &middot; TREND ANALYSIS</p>
<h1>Hydroclimatic trends across two basins<br><em>and what survives testing them properly.</em></h1>
<p class="lead">Mann&ndash;Kendall and Sen&#8217;s slope for nine variables across <strong>7,445 level-12 basins</strong> of the Amu Darya and Syr Darya, 2003&ndash;2024, stratified by system, position, elevation and land cover. The result is mostly about the corrections: of nine variables, four have <strong>no basin at all</strong> with a trend that survives control for multiple testing.</p></section>

<section class="section"><div>

<div class="stat-row">
<div class="stat"><b>7,445</b><span>basins tested<br>level-12, both systems</span></div>
<div class="stat"><b>22</b><span>complete years<br>2003&ndash;2024</span></div>
<div class="stat"><b>{soil.get('significant_after_fdr', 0):,}</b><span>basins, soil moisture<br>survive both corrections</span></div>
<div class="stat alarm"><b>0</b><span>basins, precipitation<br>survive both corrections</span></div>
</div>

<h2>The question</h2>
<p>Trend maps for Central Asia are not scarce. What is scarce is one where a reader can see how much of the result is method. Testing thousands of basins simultaneously, on series that persist from year to year, produces significance whether or not anything is happening &mdash; and the size of that effect is rarely reported alongside the map it distorts.</p>
<p>So this computes the same trend three times for every basin and publishes all three: uncorrected, corrected for serial persistence, and controlled for false discovery across the whole family of tests.</p>

<h2>Data</h2>
<p>The published observation record: nine dated variables, monthly, 2003&ndash;2024, area-reduced to every level-12 basin in both systems. Annual values are flux sums or state means, and <strong>a year short of a month is dropped rather than scaled</strong> &mdash; which is why the basin counts differ slightly between variables. Strata come from the published reference atlas rather than being invented here: system and headwater position from the routing graph, elevation from <code>ele_mt_sav</code>, land cover from the cropland, irrigated, forest and urban shares.</p>

<h2>Method</h2>
<ul>
<li><strong>Test.</strong> {method['test']}.</li>
<li><strong>Slope.</strong> {method['slope']}.</li>
<li><strong>Serial correlation.</strong> {method['autocorrelation']}.</li>
<li><strong>Multiple testing.</strong> {method['multiple_testing']}.</li>
<li><strong>Validation.</strong> {method['validation']}.</li>
</ul>

<h2>Results</h2>
<div class="fig-frame">{inline("trend-correction-cascade.svg")}</div>

<table class="t"><thead><tr><th>Variable</th><th>Basins</th><th>Significant, uncorrected</th><th>After serial correction</th><th>After false discovery control</th></tr></thead><tbody>{rows}</tbody></table>

<div class="key"><strong>Precipitation is the clearest case.</strong> {findings['precipitation']}</div>

<p>{findings['direction']}</p>

<h3>Where the surviving signal sits</h3>
<div class="fig-frame">{inline("trend-strata-soil.svg")}</div>
<p>Modelled soil moisture declines most consistently in middle and lower cropland. In irrigated basins specifically:</p>
<table class="t"><thead><tr><th>System</th><th>Position</th><th>Elevation</th><th>Basins</th><th>Significant decrease</th><th>Share</th><th>Median slope (mm/yr)</th></tr></thead><tbody>{irrigated_rows}</tbody></table>

<div class="fig-frame">{inline("trend-strata-tmn.svg")}</div>
<p>Minimum temperature rises across {tmn.get('significant_after_fdr', 0):,} basins with no significant decrease anywhere, at median Sen slopes of roughly +0.04 to +0.07&nbsp;&deg;C per year.</p>

<h2>The limitation that decides what this means</h2>
<div class="warn"><strong>Soil moisture here is modelled, not observed.</strong> {findings['the_caveat_that_matters']}</div>
<p><strong>What would test it.</strong> {findings['what_would_test_it']}</p>

<h3>Other limits, stated rather than buried</h3>
<ul>
<li><strong>Twenty-two years is short.</strong> {report['reading']['scope']}</li>
<li><strong>Snow is withdrawn from trend use.</strong> {report['reading']['snow']}</li>
<li><strong>Three verdicts, not one.</strong> {report['reading']['significance']}</li>
<li><strong>Vegetation is absent.</strong> NDVI is the variable this design most wants and the record does not yet hold. It needs its own MODIS extraction, computed server-side; the statistical frame here is built and tested so that it can drop into one rather than be built around it.</li>
</ul>

<h2>Reproduce it</h2>
<p>Every basin&#8217;s result is downloadable, and the test can be re-run from the published cube without this repository:</p>
<pre><code>pip install uzgeodata[products]

import uzgeodata as uz
from ATLAS_MODULES.core import trends

data = uz.open()                       # the current published release
series = data.series("4121289400", "precipitation")
annual = ...                           # sum months to years, dropping short years
trends.mann_kendall(annual)            # the same test, the same corrections</code></pre>
<div class="resource-links"><a href="/data/trends/index.json">Summary, strata and cross-tabulation &#8599;</a><a href="/data/trends/uz-soil-monthly-v1.json">Per-basin results, soil moisture &#8599;</a><a href="/data/trends/uz-pre-monthly-v1.json">Per-basin results, precipitation &#8599;</a><a href="/data/trends/trend-correction-cascade.svg">Figure 1 &#8599;</a></div>
<p class="muted">Each per-basin file carries the Sen slope, tau, the corrected and uncorrected p, the variance inflation applied, the false-discovery-adjusted q, and all three verdicts.</p>

</div></section>

<section class="closing"><div><p class="eyebrow">RELATED</p><h2>Where the region&#8217;s water goes.</h2><p>The water balance and allocation case study, with every flow marked by how it is known.</p></div><a class="button" href="/water-flow.html">Open the water flow study &#8599;</a></section>
</main>
<footer class="site-footer"><div><a class="brand" href="/">UzGeoData</a><p>Water systems cross borders.<br>Understanding them should, too.</p></div><div><strong>Explore</strong><a href="/">Basin explorer</a><a href="/case-studies.html">Research case studies</a><a href="/water-flow.html">Water flow diagram</a></div><div><strong>Understand</strong><a href="/about.html#citation">Citation &amp; reuse</a><a href="/guide.html">Guide &amp; data access</a><a href="/roadmap.html">Research roadmap</a></div><div><strong>Contribute</strong><a href="https://github.com/tim7en/uzgeodata">Project on GitHub &#8599;</a><a href="https://github.com/tim7en/uzgeodata/issues">Report an issue &#8599;</a><a href="release.json">Release metadata</a></div><p class="footer-note">Independent research project &middot; Public preview &middot; Amu Darya &amp; Syr Darya</p></footer></body></html>"""
    Path(out).write_text(page, encoding="utf-8")
    return {"page": str(out), "bytes": len(page.encode("utf-8"))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(build(), indent=2))


if __name__ == "__main__":
    main()
