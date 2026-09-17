"""Build the SWOT lake/reservoir monitoring case study page.

Presents what NASA/CNES's SWOT satellite mission can and cannot currently
tell us about every lake and reservoir in the Syr Darya / Amu Darya
drainage basin: 378 water bodies tracked since mid-2023 by clipping
against the basin's real drainage outline (not a bounding rectangle,
which silently excludes the Aral Sea itself), the real per-pass data
quality issues and how they were handled, and where this can and cannot
plug into the site's discharge model.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CS = ROOT / "PUBLISHED/data/case-studies"
RES = CS / "reservoirs"
OUT = ROOT / "INTERFACE/reservoir-monitoring.html"

BOOT = (
    "<script>try{var t=localStorage.getItem('uzgeodata-theme');if(t!=='light'&&t!=='dark'){"
    "t=window.matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches?'dark':"
    "(new Date().getHours()>=7&&new Date().getHours()<19?'light':'dark')}"
    "document.documentElement.dataset.theme=t}catch(e){}</script>"
)

HEADER = (
    '<header class="site-header"><a class="brand" href="/" aria-label="UzGeoData home">'
    '<span class="brand-icon" aria-hidden="true">&#8776;</span>UzGeoData<span class="brand-sub">BASIN ATLAS</span></a>'
    '<nav aria-label="Main navigation">'
    '<a href="/project.html">Project overview</a>'
    '<a href="/examples.html">Use cases</a>'
    '<a href="/case-studies.html">Case studies</a>'
    '<a href="/guide.html">User guide</a>'
    '<a href="/projects.html">Projects</a>'
    '<a class="button small" href="/">Open basin explorer <span aria-hidden="true">&#8599;</span></a>'
    '</nav></header>'
)

FOOTER = (
    '<footer class="site-footer">'
    '<div><a class="brand" href="/">UzGeoData</a><p>Water systems cross borders.<br>Understanding them should, too.</p></div>'
    '<div><strong>Explore</strong><a href="/">Basin explorer</a><a href="/examples.html">Practical examples</a><a href="/case-studies.html">Research case studies</a></div>'
    '<div><strong>Understand</strong><a href="/research.html">Research foundations</a><a href="/about.html#citation">Citation &amp; reuse</a><a href="/guide.html">Guide &amp; data access</a><a href="/roadmap.html">Research roadmap</a></div>'
    '<div><strong>Contribute</strong><a href="https://github.com/tim7en/uzgeodata">Project on GitHub &#8599;</a><a href="https://github.com/tim7en/uzgeodata/issues">Report an issue &#8599;</a><a href="/release.json">Release metadata</a></div>'
    '<p class="footer-note">Independent research project &middot; Public preview &middot; Amu Darya &amp; Syr Darya</p></footer>'
)

STYLE = """<style>
.metric-pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:18px;margin:1.4rem 0}
.metric-pair article{border:1px solid #c3cdd3;border-radius:10px;padding:1.2rem 1.4rem;background:#fbfcfc}
[data-theme="dark"] .metric-pair article{background:#0c1215;border-color:#1d282d}
.metric-pair h3{margin:.1rem 0 .4rem;font-size:1.05rem}
.metric-pair .big{display:block;font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:2.4rem;line-height:1;margin:.4rem 0}
.metric-pair p{font-size:.9rem;margin:.3rem 0 0}
.tag{font:600 .68rem 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;padding:.2rem .5rem;border-radius:3px;border:1px solid #c3cdd3;color:#515f64}
[data-theme="dark"] .tag{border-color:#2a3a41;color:#8497a0}
figure.map{margin:1.6rem 0;border:1px solid #c3cdd3;border-radius:10px;overflow:hidden;background:#fbfcfc}
[data-theme="dark"] figure.map{background:#0c1215;border-color:#1d282d}
figure.map img{width:100%;display:block}
figure.map figcaption{padding:.8rem 1rem;font-size:.85rem;color:#515f64;line-height:1.55}
[data-theme="dark"] figure.map figcaption{color:#9fb3bb}
table.skill{border-collapse:collapse;width:100%;font-size:.9rem;margin:1rem 0}
.skill th,.skill td{padding:.6rem .8rem;border-bottom:1px solid #c3cdd3;text-align:left}
[data-theme="dark"] .skill th,[data-theme="dark"] .skill td{border-bottom-color:#1d282d}
.skill th{background:#e7ebee;font:600 .72rem 'Barlow Condensed',sans-serif;letter-spacing:.09em;text-transform:uppercase;color:#515f64}
[data-theme="dark"] .skill th{background:#10161a;color:#8497a0}
.skill td.num{font-variant-numeric:tabular-nums}
.ladder{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:1rem;margin:1.2rem 0}
.ladder div{border-left:3px solid #0c6f8d;padding:.2rem 0 .2rem 1rem}
[data-theme="dark"] .ladder div{border-left-color:#4cc9f0}
.ladder b{display:block}
.ladder span{font-size:.85rem;color:#3b4a52}
[data-theme="dark"] .ladder span{color:#9fb3bb}
.warn{border-left:4px solid #b58135;background:#faf5e9;padding:1rem 1.2rem;border-radius:0 8px 8px 0;margin:1.3rem 0}
[data-theme="dark"] .warn{background:#241f10;border-left-color:#8a6a34}
.downloads{display:flex;flex-wrap:wrap;gap:.7rem;margin:1rem 0}
.downloads a{padding:.7rem 1rem;background:#eef1f3;border-radius:6px;font-size:.85rem}
[data-theme="dark"] .downloads a{background:#14231d}
</style>"""


def esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build() -> dict:
    summary = pd.read_csv(RES / "reservoir_summary.csv", dtype={"pld_id": str})
    manifest = json.loads((RES / "reservoir_manifest.json").read_text(encoding="utf-8"))
    inventory = pd.read_csv(RES / "lake_inventory.csv", dtype={"pld_id": str})

    named = summary[summary.name.notna() & (summary.n_overpasses > 0)].sort_values("pld_ref_area_km2", ascending=False)
    n_countries = named["country"].str.split("/").explode().str.strip().nunique()
    unnamed = summary[summary.name.isna()].copy()
    unnamed_with_data = unnamed[unnamed.n_overpasses > 0].copy()
    # Absolute change (km2), not percent: several of these lakes were near
    # SWOT's detection floor (a few hundred square metres) at their first
    # observation, so dividing by that first value produces percentages in
    # the thousands for a change of a couple of km2 — a real number that
    # tells a reader nothing. Ranking by absolute change surfaces the lakes
    # that actually moved, not the ones that started closest to zero.
    unnamed_with_data["area_change_km2"] = unnamed_with_data.latest_area_km2 - unnamed_with_data.first_area_km2
    movers = unnamed_with_data.dropna(subset=["area_change_km2"]).reindex(
        unnamed_with_data.area_change_km2.abs().sort_values(ascending=False).index
    ).head(8)

    named_rows = "\n".join(
        f"<tr><td>{esc(r.name)}</td><td>{esc(r.river or '')}</td><td>{esc(r.country or '')}</td>"
        f"<td class='num'>{(r.known_area_km2 if pd.notna(r.known_area_km2) else r.pld_ref_area_km2):,.0f}</td>"
        f"<td class='num'>{r.max_area_km2:,.0f}</td>"
        f"<td class='num'>{r.n_overpasses}</td>"
        f"<td>{r.first_obs[:10]}&ndash;{r.last_obs[:10]}</td></tr>"
        for r in named.itertuples() if pd.notna(r.first_obs)
    )

    mover_rows = "\n".join(
        f"<tr><td>{esc(r.pld_id)}</td><td class='num'>{r.lat:.2f}, {r.lon:.2f}</td>"
        f"<td class='num'>{r.pld_ref_area_km2:,.1f}</td>"
        f"<td class='num'>{r.first_area_km2:,.1f}</td><td class='num'>{r.latest_area_km2:,.1f}</td>"
        f"<td class='num'>{r.area_change_km2:+,.1f}</td></tr>"
        for r in movers.itertuples()
    )

    last_obs_dates = pd.to_datetime(summary["last_obs"].dropna())
    first_obs_dates = pd.to_datetime(summary["first_obs"].dropna())
    most_recent = last_obs_dates.max()
    oldest_recent = first_obs_dates.min()
    total_overpasses = int(summary["n_overpasses"].sum())
    n_with_data = int((summary.n_overpasses > 0).sum())

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#103d40">
<meta name="description" content="Watching {len(inventory):,} lakes and reservoirs across the real Syr Darya / Amu Darya drainage basin from NASA/CNES's SWOT satellite mission, including the Aral Sea itself: what it can measure today, what data quality actually looks like, and where it can feed the discharge model.">
<title>Watching every lake in the basin from orbit &middot; UzGeoData</title>
<link rel="stylesheet" href="/home.css">{BOOT}
{STYLE}</head><body><a class="skip-link" href="#main">Skip to content</a>
{HEADER}
<main id="main" class="project-content">
<section class="page-intro"><p class="eyebrow">CASE STUDY &middot; SATELLITE RESERVOIR &amp; LAKE MONITORING</p>
<h1>Every reservoir and lake<br><em>in a basin no single country owns.</em></h1>
<p class="lead">Toktogul, Kayrakkum, Nurek, Charvak, the Aral Sea itself: each sits in one country and regulates or reflects flow that several others depend on. NASA/CNES's SWOT mission has measured the water surface elevation and area of {len(inventory):,} lakes and reservoirs across the entire Syr Darya / Amu Darya drainage basin, every ~21 days since mid-2023 &mdash; from orbit, without needing any upstream country to share a reading.</p>
<nav class="topic-links" aria-label="Sections"><a href="#named">Named water bodies &#8595;</a><a href="#quality">What the raw data actually looks like &#8595;</a><a href="#basinwide">378 lakes, basin-wide &#8595;</a><a href="#modelling">Using this for modelling &#8595;</a><a href="#next">Reproduce or extend it &#8595;</a></nav></section>

<section class="section" id="named"><h2>{len(named)} named water bodies, {n_countries} countries</h2>
<div class="metric-pair">
<article><span class="tag nowcast">Source</span><h3>SWOT KaRIn radar</h3>
<span class="big">{total_overpasses:,}</span>
<p>satellite overpasses across all {len(inventory):,} lakes since {oldest_recent.date() if pd.notna(oldest_recent) else '2023'}, none of it requiring any country in the basin to publish a reading.</p></article>
<article><span class="tag transfer">Basin-wide coverage</span><h3>Real drainage outline, not a rectangle</h3>
<span class="big">{n_with_data:,}<i style="font-style:normal;font-size:1.1rem">/{len(inventory):,}</i></span>
<p>lakes &ge;1&nbsp;km&sup2; returned at least one overpass. Clipped against the actual Syr Darya / Amu Darya HydroBASINS outline &mdash; a bounding rectangle here would have silently excluded the Aral Sea itself, which sits north of where earlier drafts of this study stopped looking.</p></article>
</div>
<table class="skill"><thead><tr><th>Water body</th><th>River / basin</th><th>Country</th><th>Reference area (km&sup2;)</th><th>Max observed 2023&ndash;present (km&sup2;)</th><th>Overpasses</th><th>Record</th></tr></thead>
<tbody>
{named_rows}
</tbody></table>
<div class="warn"><strong>Two Aral Sea segments have no processed SWOT record at all.</strong> The North Aral Sea and the eastern basin of the South Aral Sea both exist as large polygons in the Prior Lake Database &mdash; large enough that the PLD's own reference area puts them among the biggest water bodies in the entire basin &mdash; but PO.DAAC's Hydrocron API returns "results not found" for both, for the full 2023&ndash;present window, not a data-quality problem this pipeline's filtering caused. Only the western basin of the South Aral Sea has a usable time series, included above. This is reported as a genuine gap in the operational SWOT lake product, not explained away as anything about the lakes' physical state.</div>
<p class="muted">Reference areas for the five dams are public knowledge (full-pool surface area); for the Aral Sea remnant, the PLD polygon's own reference area. Both are used only to identify which SWOT Prior Lake Database polygon is which named water body &mdash; PLD itself carries no names. Two more dam candidates, Andijan and Tuyamuyun, were attempted and dropped for the same reason: {manifest['dropped_reason']}.</p>
<figure class="map"><img src="/data/case-studies/reservoirs/reservoir_status.png" alt="Two panels: a map of all monitored lakes with the named water bodies highlighted, and a bar chart comparing each named water body's latest SWOT-observed area against its reference area.">
<figcaption><strong>Where they are, and how full they look from orbit.</strong> Left: every lake &ge;1&nbsp;km&sup2; SWOT has observed inside the real basin outline; the named water bodies stand out by size. Right: latest monthly-max observed area against each one's reference area &mdash; a rough fill indicator, not a calibrated storage estimate.</figcaption></figure>
<figure class="map"><img src="/data/case-studies/reservoirs/reservoir_timeseries.png" alt="Small multiples: monthly maximum SWOT-observed surface area for each named water body since 2023, each on its own scale.">
<figcaption><strong>Surface area over time, each water body on its own scale.</strong> Aydarkul/Arnasay swings by roughly its own full area as it receives and loses Syr Darya's flood-season overflow; Toktogul and Nurek, both deep valley reservoirs built for multi-year hydropower regulation, show a slower drawdown/refill cycle; the three Aral Sea remnants are the record this entire satellite mission's lake product was, in part, built to keep.</figcaption></figure>
</section>

<section class="section" id="quality"><h2>What the raw satellite data actually looks like</h2>
<p>SWOT's KaRIn radar swath is about 50&nbsp;km wide, and a single overpass often does not cross an entire lake &mdash; especially the long, valley-shaped reservoirs like Toktogul. The raw per-pass <code>area_total</code> field is exactly what that one pass saw, not a corrected whole-lake estimate: Toktogul's own raw record clusters at two very different area values (roughly 20&nbsp;km&sup2; and 225&nbsp;km&sup2;) depending on whether a given pass crossed a sliver of the reservoir or nearly all of it. A partial pass can only under-count true extent, never over-count it, so this dataset uses the <strong>monthly maximum</strong> observed area as the extent estimate everywhere, not the mean &mdash; averaging the two clusters would invent a number that was never actually true on any date.</p>
<p>Water surface elevation does not have this problem (a partial view of a lake's surface still gives a true elevation reading), but a small number of passes are outright broken: four Toktogul passes reported elevations above 1,000&nbsp;m against a normal range of roughly 830&ndash;900&nbsp;m, all carrying the same "suspect" quality flag as most of the good passes around them. Those are dropped by a per-lake statistical outlier filter (median &plusmn; 6&times;MAD), applied to all {len(inventory):,} lakes, not by the quality flag alone, because the quality flag did not catch them.</p>
<p>Monthly-max does not fully remove the partial-swath effect either: a month with only one or two overpasses, none of them a near-full view, still reports whatever partial value it has &mdash; visible as single-month spikes or dips in several of the named water bodies' time series above (Kayrakkum, Toktogul and Charvak all show at least one such isolated point). A one-month outlier that does not persist into the next month is more likely this artefact than a real, brief flood or drawdown; treating it as one requires checking the underlying per-pass record, which is why the full per-pass CSV, not just the monthly summary, is offered in the downloads below.</p>
<div class="warn"><strong>Known boundary.</strong> The earliest observation in this dataset is {oldest_recent.date() if pd.notna(oldest_recent) else 'mid-2023'} &mdash; SWOT's pre-science-orbit fast-sampling phase reaches back this far for some lakes, but most usable coverage begins with the 21-day science orbit that started 2023-07-21. Either way this is about three years, far shorter than the gauge records elsewhere on this site. Revisit is irregular, roughly one to four passes per 21-day cycle depending on location, not a fixed daily monitoring cadence. Latest available observations in this dataset run through {most_recent.date() if pd.notna(most_recent) else 'the most recent refresh'}; whether that reflects a real processing gap or simply when this dataset was last refreshed needs checking against PO.DAAC's own product status before being read as "monitoring stopped."</div></section>

<section class="section" id="basinwide"><h2>{len(inventory):,} lakes, basin-wide</h2>
<p>Every lake and reservoir &ge;1&nbsp;km&sup2; inside the real Syr Darya / Amu Darya drainage outline is fetched the same way as the named water bodies above, just without a name attached &mdash; PLD carries no names, so the other {len(inventory) - len(named):,} are identified only by their Prior Lake Database id and coordinates. Combined they cover {inventory.area_km2.sum():,.0f}&nbsp;km&sup2; of surface water. The table below is not a curated top-N: it is every one of those unnamed lakes with the largest area change (either direction) between its first and most recent monthly observation, sorted by size of change &mdash; a way to surface what the raw data itself flags as notable, rather than what we already knew to look for.</p>
<table class="skill"><thead><tr><th>PLD id</th><th>Location (lat, lon)</th><th>Reference area (km&sup2;)</th><th>First observed (km&sup2;)</th><th>Latest observed (km&sup2;)</th><th>Change (km&sup2;)</th></tr></thead>
<tbody>
{mover_rows}
</tbody></table>
<p class="muted">Full inventory and per-lake summary: see downloads below. A large swing here can mean a real hydrological event, a seasonal wetland that is supposed to disappear and refill, or a partial-swath measurement artefact that the monthly-max aggregation did not fully absorb &mdash; each one needs a look at its own time series before being read as a finding.</p></section>

<section class="section" id="modelling"><h2>Using this for modelling</h2>
<div class="ladder">
<div><b>Not a discharge history replacement</b><span>Three years of records cannot retrain a model built on 40+ years of gauge data (see the <a href="/dry-spell.html">discharge case study</a>). It is not trying to.</span></div>
<div><b>A real missing feature</b><span>Reservoir release timing is exactly what breaks the precip-to-flow relationship the pooled transfer model relies on at regulated gauges (Vaksh, Pyandzh) &mdash; their largest errors. Reservoir fill state as a feature could explain some of that residual, once enough months of overlap exist between this record and the gauge record.</span></div>
<div><b>An independent, gauge-free cross-check</b><span>Water surface elevation and area trends since 2023 can be compared against the pooled model's predictions for the same period at nearby gauges &mdash; a validation signal that needs no discharge measurement of its own.</span></div>
</div>
<div class="warn"><strong>Not yet done.</strong> None of the three uses above are wired into the discharge model on this site today. This case study is the data and the quality-control work that would have to come first.</div></section>

<section class="section" id="next"><h2>Reproduce or extend it</h2>
<div class="downloads">
<a href="/data/case-studies/reservoirs/reservoir_summary.csv">Per-lake summary, all {len(inventory):,} lakes (CSV)</a>
<a href="/data/case-studies/reservoirs/reservoir_timeseries_monthly.csv">Monthly max/median time series, all lakes (CSV)</a>
<a href="/data/case-studies/reservoirs/named_reservoirs_raw_timeseries.csv">Full per-pass series, named water bodies (CSV)</a>
<a href="/data/case-studies/reservoirs/lake_inventory.csv">Basin-wide lake inventory (CSV)</a>
<a href="/data/case-studies/reservoirs/reservoir_manifest.json">Manifest &amp; methodology (JSON)</a>
</div>
<p class="muted">Pipeline: <code>python PIPELINES/fetch_swot_reservoirs.py</code> re-queries the live Hydroweb WFS (geometry) and PO.DAAC Hydrocron (time series) APIs directly &mdash; both public, no account or token needed, verified live while building this page &mdash; and clips against the real basin outline in <code>PUBLISHED/data/hydroclimate/basins-level10.geojson</code>. <code>python PIPELINES/build_reservoir_charts.py</code> regenerates the two figures. Source: NASA/CNES Surface Water and Ocean Topography (SWOT) mission; SWOT Prior Lake Database geometry served via CNES/Theia Hydroweb; time series via NASA PO.DAAC's Hydrocron API.</p></section>
</main>
{FOOTER}
<script type="module" src="/site-boot.js"></script></body></html>
"""
    OUT.write_text(html, encoding="utf-8")
    return {"page": str(OUT), "bytes": OUT.stat().st_size, "n_lakes": len(inventory), "n_named": len(named)}


if __name__ == "__main__":
    print(json.dumps(build()))
