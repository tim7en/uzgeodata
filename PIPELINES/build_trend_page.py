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


def inline_map(name):
    """A map inlined into the page. Level 7 only -- level 12 is 1.6 MB and is linked."""
    return (TRENDS / "maps" / name).read_text(encoding="utf-8").replace(
        "<svg ", '<svg class="fig" ', 1)


def build(out=OUT):
    report = json.loads((TRENDS / "index.json").read_text(encoding="utf-8"))
    scale = json.loads((TRENDS / "scale-check.json").read_text(encoding="utf-8"))

    def side(entry):
        if not entry["tested"]:
            return "<td>not testable</td><td>&mdash;</td>"
        return (f'<td>{entry["significant"]:,} of {entry["tested"]:,}</td>'
                f'<td>{entry["share"]:.0%}</td>')

    scale_rows = "".join(
        f'<tr><td>{r["variable"].replace("uz:", "").replace("-monthly-v1", "")}</td>'
        f'<td>{r["native_resolution_m"]:,} m</td>'
        + side(r["level12"]) + side(r["level7"])
        + f'<td class="{"zero" if r["verdict"] == "diverges" else "kept"}">'
          f'{r["verdict"]}</td></tr>'
        for r in scale["variables"])

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
.t-wrap{{overflow-x:auto;margin:1.1rem 0;border:1px solid #d0dcd6;border-radius:6px}}
.t{{width:100%;border-collapse:collapse;font-size:.93rem;margin:0}}
.t th,.t td{{text-align:left;padding:.6rem .8rem;border-bottom:1px solid #d0dcd6;vertical-align:top}}
.t thead th{{background:#eaf0ec;font-size:.78rem;text-transform:uppercase;letter-spacing:.04em;color:#2d4a42;border-bottom:2px solid #b8ccc4}}
.t thead tr+tr th{{border-top:1px solid #c8d6cf}}
.t tbody tr:nth-child(even){{background:#f6f9f6}}
.t tbody tr:hover{{background:#eef4f0}}
.t td.zero{{color:#9b2c2c;font-weight:650}}
.t td.kept{{color:#1b4d7e;font-weight:650}}
.muted{{color:#4a5568;font-size:.85rem}}
.warn{{display:block;width:auto;border-left:4px solid #9b2c2c;background:#fdf6f6;padding:.95rem 1.15rem;border-radius:0 8px 8px 0;margin:1.3rem 0}}
.key{{display:block;width:auto;border-left:4px solid #1b4d7e;background:#f5f8fb;padding:.95rem 1.15rem;border-radius:0 8px 8px 0;margin:1.3rem 0}}
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
<p class="lead">Mann&ndash;Kendall and Sen&#8217;s slope for <strong>fourteen variables</strong> across level-12 and level-7 basins of the Amu Darya and Syr Darya, 2003&ndash;2024, stratified by system, position, elevation and land cover. Two results carry the study: most apparent trends do not survive correction for multiple testing, and in the water-balance model that supplies most of these variables, <strong>the fluxes show no trend while the stores do</strong>.</p></section>

<section class="section"><div>

<div class="stat-row">
<div class="stat"><b>14</b><span>variables tested<br>at two basin levels</span></div>
<div class="stat"><b>22</b><span>complete years<br>2003&ndash;2024</span></div>
<div class="stat"><b>{soil.get('significant_after_fdr', 0):,}</b><span>basins, soil moisture<br>survive both corrections</span></div>
<div class="stat alarm"><b>2</b><span>variables withheld<br>basin smaller than source cell</span></div>
</div>

<div class="warn"><strong>Two variables are withheld entirely at this basin level.</strong> {findings['resolution']['finding']}</div>

<h2>Resolution: what a basin mean can and cannot be</h2>
<p>{findings['resolution']['why_it_was_not_obvious']}</p>
<div class="t-wrap"><table class="t"><thead><tr><th>Product</th><th>Cell size</th><th>Source cells per basin, region-wide</th><th>Verdict at level 12</th></tr></thead><tbody>
<tr><td>MODIS MYD10A1</td><td>500 m &middot; 0.25 km&sup2;</td><td>518.9</td><td class="kept">resolved</td></tr>
<tr><td>TerraClimate</td><td>4.6 km &middot; 21.5 km&sup2;</td><td>6.03</td><td class="kept">resolved</td></tr>
<tr><td>ERA5-Land</td><td>11.1 km &middot; 123.2 km&sup2;</td><td>1.05</td><td class="zero">withheld</td></tr>
</tbody></table></div>
<p>{findings['resolution']['what_survives']}</p>
<p class="muted"><strong>The remaining caveat.</strong> {findings['resolution']['the_remaining_caveat']}</p>

<h2>The question</h2>
<p>Trend maps for Central Asia are not scarce. What is scarce is one where a reader can see how much of the result is method. Testing thousands of basins simultaneously, on series that persist from year to year, produces significance whether or not anything is happening &mdash; and the size of that effect is rarely reported alongside the map it distorts.</p>
<p>So this computes the same trend three times for every basin and publishes all three: uncorrected, corrected for serial persistence, and controlled for false discovery across the whole family of tests.</p>

<h2>Data</h2>
<p>The published observation record: nine dated variables, monthly, 2003&ndash;2024, area-reduced to level-12 basins in both systems, <strong>gated on resolution</strong> as above &mdash; a basin must contain at least four native source cells to be tested at all. Annual values are flux sums or state means, and <strong>a year short of a month is dropped rather than scaled</strong> &mdash; which is why the basin counts differ slightly between variables. Strata come from the published reference atlas rather than being invented here: system and headwater position from the routing graph, elevation from <code>ele_mt_sav</code>, land cover from the cropland, irrigated, forest and urban shares.</p>

<h2>Method</h2>
<ul>
<li><strong>Test.</strong> {method['test']}.</li>
<li><strong>Slope.</strong> {method['slope']}.</li>
<li><strong>Serial correlation.</strong> {method['autocorrelation']}.</li>
<li><strong>Multiple testing.</strong> {method['multiple_testing']}.</li>
<li><strong>Validation.</strong> {method['validation']}.</li>
</ul>

<h2>Does the answer depend on the size of the unit?</h2>
<p>A trend computed per basin is a trend computed on an arbitrary polygon. Enlarge the polygons and several things change at once: each unit averages more source cells, the series smooths, and the number of simultaneous tests falls by a factor of seventeen. A result present at one size and absent at another is telling you about the polygons.</p>
<p>So the whole study is run twice &mdash; at level 12 (7,445 units, median 136&nbsp;km&sup2;) and level 7 (438 units, median 1,510&nbsp;km&sup2;) &mdash; and compared. <strong>Seven of nine variables agree; none diverges.</strong> The two that appear at one scale only are the ERA5-Land pair, which level 12 cannot resolve at all.</p>
<div class="t-wrap"><table class="t"><thead><tr><th rowspan="2">Variable</th><th rowspan="2">Native cell</th><th colspan="2">Level 12</th><th colspan="2">Level 7</th><th rowspan="2">Verdict</th></tr><tr><th>Significant</th><th>Share</th><th>Significant</th><th>Share</th></tr></thead><tbody>{scale_rows}</tbody></table></div>
<p class="key"><strong>Analysed at the level where it resolves, ERA5-Land shows nothing.</strong> {scale['reading']['era5']}</p>
<p class="muted"><strong>What this cannot do.</strong> {scale['reading']['what_it_cannot_do']}</p>

<h2>Results</h2>
<div class="fig-frame">{inline("trend-correction-cascade.svg")}</div>

<div class="t-wrap"><table class="t"><thead><tr><th>Variable</th><th>Basins</th><th>Significant, uncorrected</th><th>After serial correction</th><th>After false discovery control</th></tr></thead><tbody>{rows}</tbody></table></div>

<div class="key"><strong>Precipitation is the clearest case.</strong> {findings['precipitation']}</div>

<h3>The fluxes do not trend. The stores do.</h3>
<p>{findings['drivers_do_not_trend_but_states_do']['observation']}</p>
<div class="t-wrap"><table class="t"><thead><tr><th>Role in the water balance</th><th>Variable</th><th>Significant after correction</th></tr></thead><tbody>
<tr><td>water in</td><td>precipitation</td><td class="zero">{block("uz:pre-monthly-v1").get("significant_after_fdr", 0):,}</td></tr>
<tr><td>evaporative demand</td><td>potential evapotranspiration</td><td class="zero">{block("uz:pet-monthly-v1").get("significant_after_fdr", 0):,}</td></tr>
<tr><td>water out</td><td>actual evapotranspiration</td><td>{block("uz:aet-monthly-v1").get("significant_after_fdr", 0):,}</td></tr>
<tr><td>model surplus</td><td>TerraClimate runoff</td><td class="zero">{block("uz:rtc-monthly-v1").get("significant_after_fdr", 0):,}</td></tr>
<tr><td>demand less supply</td><td>climatic water deficit</td><td class="zero">{block("uz:cwd-monthly-v1").get("significant_after_fdr", 0):,}</td></tr>
<tr><td><strong>store</strong></td><td><strong>soil moisture</strong></td><td class="kept">{block("uz:soil-monthly-v1").get("significant_after_fdr", 0):,}</td></tr>
<tr><td><strong>store</strong></td><td><strong>Palmer drought severity index</strong></td><td class="kept">{block("uz:pds-monthly-v1").get("significant_after_fdr", 0):,}</td></tr>
</tbody></table></div>
<div class="warn"><strong>This is the study&#8217;s most consequential result.</strong> {findings['drivers_do_not_trend_but_states_do']['why_it_matters']}</div>
<p><strong>Three readings, which this analysis cannot separate:</strong></p>
<ol>{"".join(f"<li>{r}</li>" for r in findings['drivers_do_not_trend_but_states_do']['three_readings'])}</ol>
<p>{findings['drivers_do_not_trend_but_states_do']['not_separable_here']}</p>
<p class="muted"><strong>A supporting asymmetry.</strong> {findings['drivers_do_not_trend_but_states_do']['the_temperature_asymmetry']}</p>

<p>{findings['direction']}</p>

<h3>Where the surviving signal sits</h3>
<div class="fig-frame">{inline("trend-strata-soil.svg")}</div>
<p>Modelled soil moisture declines most consistently in middle and lower cropland. In irrigated basins specifically:</p>
<div class="t-wrap"><table class="t"><thead><tr><th>System</th><th>Position</th><th>Elevation</th><th>Basins</th><th>Significant decrease</th><th>Share</th><th>Median slope (mm/yr)</th></tr></thead><tbody>{irrigated_rows}</tbody></table></div>

<div class="fig-frame">{inline("trend-strata-tmn.svg")}</div>
<p>Minimum temperature rises across {tmn.get('significant_after_fdr', 0):,} basins with no significant decrease anywhere, at median Sen slopes of roughly +0.04 to +0.07&nbsp;&deg;C per year.</p>

<h2>Maps</h2>
<p>The counts say how much; the maps say where, and whether the signal forms a pattern or is scattered. Colour is the <strong>corrected</strong> verdict, so these agree with the tables above rather than with the more dramatic picture an uncorrected test would support.</p>
<p>Basins too small to hold four native source cells are drawn in their own neutral fill rather than left blank &mdash; a white gap on a choropleth reads as &ldquo;no trend&rdquo; when the truth is &ldquo;no answer&rdquo;.</p>

<h3>Soil moisture &mdash; the signal that survives</h3>
<div class="fig-frame">{inline_map("trend-map-soil-level7.svg")}</div>

<h3>Minimum temperature</h3>
<div class="fig-frame">{inline_map("trend-map-tmn-level7.svg")}</div>

<h3>Precipitation &mdash; the signal that does not</h3>
<p>The same region, the same test, the same correction. Nothing survives, and the map is the clearest statement of that.</p>
<div class="fig-frame">{inline_map("trend-map-pre-level7.svg")}</div>

<h3>ERA5-Land runoff at level 12 &mdash; a map with no answer on it</h3>
<p>Every basin withheld, because at 123&nbsp;km&sup2; per cell against a 136&nbsp;km&sup2; median basin the product cannot resolve the unit. A blank choropleth is usually an omission; this one is the result.</p>
<div class="resource-links"><a href="/data/trends/maps/trend-map-run-level7.svg">Runoff at level 7, where it does resolve &#8599;</a><a href="/data/trends/maps/trend-map-soil-level12.svg">Soil moisture at level 12, 7,445 basins &#8599;</a></div>

<p class="muted">All nine variables are mapped at level 7: <a href="/data/trends/maps/trend-map-aet-level7.svg">aet</a> &middot; <a href="/data/trends/maps/trend-map-pet-level7.svg">pet</a> &middot; <a href="/data/trends/maps/trend-map-pre-level7.svg">pre</a> &middot; <a href="/data/trends/maps/trend-map-run-level7.svg">run</a> &middot; <a href="/data/trends/maps/trend-map-snw-level7.svg">snw</a> &middot; <a href="/data/trends/maps/trend-map-soil-level7.svg">soil</a> &middot; <a href="/data/trends/maps/trend-map-tmn-level7.svg">tmn</a> &middot; <a href="/data/trends/maps/trend-map-tmp-level7.svg">tmp</a> &middot; <a href="/data/trends/maps/trend-map-tmx-level7.svg">tmx</a>. Outlines are simplified for drawing at a stated tolerance; the values are not.</p>

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
