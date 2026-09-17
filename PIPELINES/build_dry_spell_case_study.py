"""Build the dry-spell / discharge-modelling case study page.

Presents the two-model experiment exactly as validated: a gauge-anchored
nowcast (discharge lags allowed, useless without a gauge) and a pooled,
gauge-unseen transfer model (climate forcing and basin attributes only, one
shared model across all gauges, scored on gauges held out of training
entirely) with a per-gauge calibration layer on top, plus the dry-spell
reconstruction numbers and the explicit boundary between what is validated
and what is still a design.
"""
from __future__ import annotations
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CS = ROOT / "PUBLISHED/data/case-studies"
OUT = ROOT / "INTERFACE/dry-spell.html"

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
.metric-pair{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:1.4rem 0}
.metric-pair article{border:1px solid #c3cdd3;border-radius:10px;padding:1.2rem 1.4rem;background:#fbfcfc}
[data-theme="dark"] .metric-pair article{background:#0c1215;border-color:#1d282d}
.metric-pair h3{margin:.1rem 0 .4rem;font-size:1.05rem}
.metric-pair .big{display:block;font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:2.4rem;line-height:1;margin:.4rem 0}
.metric-pair p{font-size:.9rem;margin:.3rem 0 0}
.tag{font:600 .68rem 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;padding:.2rem .5rem;border-radius:3px;border:1px solid #c3cdd3;color:#515f64}
[data-theme="dark"] .tag{border-color:#2a3a41;color:#8497a0}
.tag.nowcast{border-color:#7fb5c9;color:#0c6f8d}
[data-theme="dark"] .tag.nowcast{border-color:#2f6d8e;color:#6fc4de}
.tag.transfer{border-color:#c9a06b;color:#8a5a12}
[data-theme="dark"] .tag.transfer{border-color:#8a6a34;color:#d9b06a}
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
    ga = json.loads((CS / "gauge_uncertainty_calibration.json").read_text(encoding="utf-8"))
    ga_gauges = ga["gauges"]
    ga_n = ga["summary"]["n_gauges"]
    ga_positive = sum(1 for v in ga_gauges.values() if v["r2"] > 0)
    ga_best = max(v["r2"] for v in ga_gauges.values())
    ga_worst = min(v["r2"] for v in ga_gauges.values())

    basins = pd.read_csv(CS / "gauge_basin_lookup.csv", dtype={"gauge_code": str})
    excluded = basins[~basins.aral_drainage]
    excluded_by_basin = excluded.groupby("BASIN").gauge_code.nunique().sort_values(ascending=False)
    excluded_note = ", ".join(f"{b.title().replace('_', ' ')} ({n})" for b, n in excluded_by_basin.items())

    error_df = pd.read_csv(CS / "dry_spell_error_analysis.csv")
    dry = error_df[error_df.dry_spell_state == "dry_spell"]
    normal = error_df[error_df.dry_spell_state == "normal"]
    manifest = json.loads((CS / "dry_spell_error_analysis.manifest.json").read_text(encoding="utf-8"))

    enhanced = pd.read_csv(CS / "enhanced_discharge_features_aral.csv", dtype={"gauge_code": str})
    total_records = len(enhanced)
    climate_cov = enhanced.groupby("gauge_code")["basin_precip_mm"].apply(lambda s: s.notna().mean())
    gauges_without_climate = int((climate_cov < 0.5).sum())

    pooled = json.loads((CS / "pooled_transfer_summary.json").read_text(encoding="utf-8"))
    pooled_importance = pd.read_csv(CS / "pooled_transfer_importance.csv")
    calibration = pd.read_csv(CS / "pooled_transfer_calibration.csv", dtype={"gauge_code": str})
    calibration = calibration.dropna(subset=["r2_pooled_calibrated"]).sort_values("r2_pooled_calibrated", ascending=False)
    cal_rows = "\n".join(
        f"<tr><td>{esc(row.gauge_code)}</td><td class='num'>{row.n_test}</td>"
        f"<td class='num'>{row.calibration_ratio:.2f}&times;</td>"
        f"<td class='num'>{row.r2_pooled_uncalibrated:.3f}</td>"
        f"<td class='num'><strong>{row.r2_pooled_calibrated:.3f}</strong></td></tr>"
        for row in calibration.head(8).itertuples()
    )
    pooled_importance_ranked = pooled_importance.reset_index(drop=True)
    top_area_feature_rank = int(pooled_importance_ranked.query("feature=='basin_area_km2'").index[0]) + 1
    top3_features = ", ".join(pooled_importance_ranked["feature"].head(3))
    mb = pooled["mass_balance_check"]

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#103d40">
<meta name="description" content="Gauge-anchored and pooled gauge-unseen discharge modelling across {ga_n} Syr Darya / Amu Darya CA-discharge gauges, with per-gauge calibration and dry-spell reconstruction: what is validated, what is not, and what comes next.">
<title>Dry spells and river flow without gauges &middot; UzGeoData</title>
<link rel="stylesheet" href="/home.css">{BOOT}
{STYLE}</head><body><a class="skip-link" href="#main">Skip to content</a>
{HEADER}
<main id="main" class="project-content">
<section class="page-intro"><p class="eyebrow">CASE STUDY &middot; DISCHARGE ENSEMBLE &amp; DRY SPELLS</p>
<h1>River flow without<br><em>a gauge in the basin.</em></h1>
<p class="lead">{ga_n} CA-discharge gauges &mdash; every one of them inside the Syr Darya or Amu Darya (Aral Sea) drainage &mdash; with monthly {total_records:,}-record modelling and chronological holdouts ({manifest['n_validation_records']:,} held-out records). The model that matters for ungauged basins predicts discharge from <strong>climate and basin attributes alone, pooled across gauges and validated on gauges it never trained on</strong> &mdash; then a small per-gauge coefficient calibrates it wherever a gauge actually exists.</p>
<nav class="topic-links" aria-label="Sections"><a href="#models">Two models &#8595;</a><a href="#pooled">Pooled transfer model &#8595;</a><a href="#calibration">Per-gauge calibration &#8595;</a><a href="#maps">Error atlas &#8595;</a><a href="#dryspell">Dry spells &#8595;</a><a href="#next">What would make it a forecast &#8595;</a></nav></section>

<section class="section" id="models"><h2>Two deliberately different models</h2>
<div class="metric-pair">
<article><span class="tag nowcast">Gauge-anchored nowcast</span><h3>With discharge history</h3>
<span class="big">{ga_positive}<i style="font-style:normal;font-size:1.1rem">/{ga_n}</i></span>
<p>gauges with positive held-out R&sup2; (chronological 80/20). Best gauge {ga_best:.3f}; worst {ga_worst:.3f}. Uses discharge lags, quantiles and baseflow &mdash; so it describes flows <strong>where a gauge already reports</strong>. It cannot move to a basin whose gauge is missing: its strongest inputs do not exist there.</p></article>
<article><span class="tag transfer">Pooled transfer model</span><h3>No discharge feature, no per-gauge fitting</h3>
<span class="big">{pooled['per_gauge_positive']}<i style="font-style:normal;font-size:1.1rem">/{pooled['per_gauge_total']}</i></span>
<p>gauges positive on gauges the model never trained on (5-fold, held out by gauge, not by month). Pooled reconstruction R&sup2; {pooled['overall_r2']:.2f} across every held-out record. Climate, terrain, land cover and <strong>basin area</strong> only, no calendar feature &mdash; this is the model an ungauged basin can actually receive, because it is one shared model, not {pooled['n_gauges']} separate ones.</p></article>
</div>
<div class="warn"><strong>Why the old "transfer" number was wrong.</strong> An earlier version of this page fit a separate model per gauge and called it gauge-independent because it dropped discharge features. But a model trained on one gauge's rows alone cannot learn anything from basin area or elevation &mdash; they never change within a single gauge's history, so a tree has zero variance to split on, and there was no shared model to hand to a new basin. The pooled model above is fit once, across all {pooled['n_gauges']} gauges together, and scored only on gauges withheld from training entirely &mdash; that is what "usable at an ungauged basin" actually requires.</div>
<div class="warn"><strong>Basin scope.</strong> CA-discharge covers {ga_n + int(excluded_by_basin.sum())} Central Asian gauges with usable multi-decade history, not just Syr Darya / Amu Darya. {int(excluded_by_basin.sum())} of them &mdash; {excluded_note} &mdash; drain elsewhere (Harirud and Murghab toward Turkmenistan/Iran; the rest are separate endorheic basins) and are excluded from every number on this page.</div></section>

<section class="section" id="pooled"><h2>Pooled transfer model: climate and basin attributes only</h2>
<p>The model predicts <strong>specific discharge</strong> (millimetres per day, i.e. flow normalised by basin area) rather than raw m3/s, because a 98 km2 catchment and a 121,000 km2 one are not comparable on the same scale. Discharge is then reconstructed as <code>specific discharge &times; basin area</code> &mdash; so basin area's role is structural, multiplying every prediction, not just one input among many the model has to rediscover; it still ranks {top_area_feature_rank} of {len(pooled['features'])} among the features shaping the specific-discharge estimate itself. There is no calendar feature anywhere in this model &mdash; no month-of-year, no day-of-year encoding. Seasonality has to come from the physical variables that actually carry it (temperature is negative in winter on its own, precipitation has its own seasonal cycle), and it does: the top three predictors are {top3_features}. Dropping the calendar encoding cost a little pooled skill (R&sup2; {pooled['overall_r2']:.2f} vs 0.80 with it) &mdash; a real but modest amount of seasonal information beyond raw climate, most likely snowmelt timing that lags temperature by weeks in glacier-fed basins.</p>
<p>Land cover is real here for the first time: the previous version of this pipeline read the wrong landcover codebook (ESA WorldCover codes that don't exist in CA-discharge's own Copernicus CGLS-LC100 columns), never divided by basin area, and had no mapping for permanent snow and ice at all &mdash; so every basin's forest/water/urban/glacier percentage was either silently wrong or a hardcoded 0.0. <code>landcover_snow_ice_pct</code> is now the real glacier/permanent-snow fraction per basin (up to 17% in the most glaciated catchments here) and lands inside the top 12 predictors.</p>
<figure class="map"><img src="/data/case-studies/pooled_transfer_atlas.png" alt="Two panels: log-log scatter of observed versus predicted discharge on gauges the model never trained on, and a horizontal bar chart of feature importance for the specific-discharge model.">
<figcaption><strong>Gauge-unseen prediction and feature importance.</strong> Left: every point is a held-out record from a gauge excluded from that fold's training entirely (GroupKFold by gauge, 5 folds). Log-log axes because discharge spans four orders of magnitude across these basins. Right: what actually drives the specific-discharge estimate &mdash; basin area is folded into the reconstruction itself rather than fought for here.</figcaption></figure>
<div class="warn"><strong>Mass-balance plausibility check, real traced topology.</strong> Each Aral-scope gauge has an exact delineated catchment polygon (CA-discharge's own <code>basins</code> layer, HydroSHEDS-derived); a gauge's catchment sitting almost entirely inside another gauge's catchment means the first is upstream of the second, whatever their basin names are &mdash; the earlier version of this check compared gauges by matching basin name plus area instead, which misses every cross-basin confluence (Naryn into Syr Darya, tributaries into the Vaksh). Across {mb['comparisons']} confirmed confluences (a downstream gauge and its single largest measured upstream tributary), predicted discharge is inverted (downstream less than its tributary) in {mb['violations_predicted']} ({mb['violation_rate_predicted_pct']}%) &mdash; and the <em>observed</em> discharge is inverted at exactly the same {mb['violations_observed']} confluences ({mb['violation_rate_observed_pct']}%). The model is not introducing mass-balance breaks beyond what the gauge records themselves already show at those specific junctions (likely real regulation or a timing mismatch between the two records, not a modelling error).</div></section>

<section class="section" id="calibration"><h2>Per-gauge calibration</h2>
<p>The pooled model above is one shared estimate for every basin. Where a gauge actually exists, its own record can sharpen that estimate: fit a single ratio &mdash; observed &divide; pooled-predicted, using only that gauge's first 80% of months &mdash; and apply it to the last 20%, a genuine forward-in-time test. This is the "coefficient per basin" the pooled model can be calibrated with, and it is exactly as much local fitting as a gauge that exists can support &mdash; nothing here reaches back into an ungauged basin.</p>
<div class="metric-pair">
<article><span class="tag transfer">Before calibration</span><h3>Pooled estimate as-is</h3>
<span class="big">{pooled['calibration']['positive_uncalibrated']}<i style="font-style:normal;font-size:1.1rem">/{pooled['calibration']['n_gauges_calibrated']}</i></span>
<p>gauges positive on each gauge's own later months; median R&sup2; {pooled['calibration']['median_r2_uncalibrated']:.2f}.</p></article>
<article><span class="tag nowcast">After calibration</span><h3>+ one ratio per gauge</h3>
<span class="big">{pooled['calibration']['positive_calibrated']}<i style="font-style:normal;font-size:1.1rem">/{pooled['calibration']['n_gauges_calibrated']}</i></span>
<p>gauges positive; median R&sup2; {pooled['calibration']['median_r2_calibrated']:.2f}. Same held-out months, same pooled prediction, one multiplier fit from that gauge's own earlier record.</p></article>
</div>
<table class="skill"><thead><tr><th>Gauge</th><th>Held-out months</th><th>Calibration ratio</th><th>R&sup2; pooled</th><th>R&sup2; calibrated</th></tr></thead>
<tbody>
{cal_rows}
</tbody></table>
<p class="muted">Full table: <a href="/data/case-studies/pooled_transfer_calibration.csv">pooled_transfer_calibration.csv</a>. A ratio far from 1&times; means the pooled model is systematically biased at that gauge before calibration &mdash; usually a regulated reach or a basin shape the pooled model under-represents &mdash; and the local fit corrects a consistent offset, not noise.</p></section>

<section class="section" id="maps"><h2>Held-out error atlas</h2>
<p>Every point below is a chronological hold-out record &mdash; months the models never saw.</p>
<figure class="map"><img src="/data/case-studies/dry_spell_error_atlas.png" alt="Two panels: predicted versus observed discharge coloured by dry-spell state, and mean absolute error by dry-spell state grouped by basin.">
<figcaption><strong>Error atlas, {manifest['n_gauges']} gauges (gauge-anchored model).</strong> Left: held-out predictions against observations, coloured by dry-spell state. Right: MAE by observed dry-spell state, aggregated per basin (14 Syr Darya / Amu Darya sub-basins &mdash; per-gauge bars stop being readable past a handful of gauges).</figcaption></figure>
<figure class="map"><img src="/data/case-studies/dry_spell_gauge_error_map.png" alt="Map of the Syr Darya and Amu Darya basins: one marker per gauge, colour showing held-out RMSE, marker size showing observed dry-spell months.">
<figcaption><strong>Where the errors live.</strong> One marker per gauge on real BasinATLAS geometry, Syr Darya / Amu Darya gauges only; colour is held-out RMSE, size is observed dry-spell months. Two exact duplicate station rows were removed rather than plotted twice.</figcaption></figure>
</section>

<section class="section" id="dryspell"><h2>Dry spells: reconstruction now, warning next</h2>
<p>A dry-spell month here means discharge below that gauge's Q25 &mdash; a relative low-flow proxy, not a drought-impact definition. On the {len(error_df):,} chronological held-out records, <strong>{len(dry)} dry-spell months</strong> were observed; mean absolute error during them is <strong>{dry.absolute_error_m3s.mean():.2f} m&sup3;/s against {normal.absolute_error_m3s.mean():.2f} m&sup3;/s</strong> in normal months. Low, stable flow is easier to describe than floods &mdash; so the model reconstructs dry periods well. That is reconstruction from concurrent conditions, not warning ahead of them.</p>
<div class="ladder">
<div><b>Validated today</b><span>Monthly discharge reconstruction at {manifest['n_gauges']} Syr Darya / Amu Darya gauges under chronological holdouts; interval coverage {manifest['overall_interval_coverage_pct']:.1f}% (below nominal 90% &mdash; stated, not sold as calibrated).</span></div>
<div><b>Designed, not yet run</b><span>Lead-time dry-spell classification (h = 1&ndash;3 months) with event recall, false-alarm rate and PR-AUC against climatology and persistence baselines.</span></div>
<div><b>Required inputs</b><span>Real gridded forcing (WorldClim/EClim-class) for the {gauges_without_climate} gauges without station climate coverage; per-basin variable-importance shading on BasinATLAS geometry.</span></div>
</div>
<div class="warn"><strong>Known boundary.</strong> Regulated gauges break precipitation-to-flow reasoning; the Q25 proxy is relative, not an impact measure; and one split is one split &mdash; rolling-origin evaluation is specified before any forecasting claim.</div></section>

<section class="section" id="next"><h2>Reproduce or extend it</h2>
<div class="downloads">
<a href="/data/case-studies/pooled_transfer_summary.json">Pooled transfer summary (JSON)</a>
<a href="/data/case-studies/pooled_transfer_predictions.csv">Pooled transfer predictions (CSV)</a>
<a href="/data/case-studies/pooled_transfer_importance.csv">Pooled feature importance (CSV)</a>
<a href="/data/case-studies/pooled_transfer_calibration.csv">Per-gauge calibration (CSV)</a>
<a href="/data/case-studies/gauge_uncertainty_calibration.json">Gauge-anchored calibration (JSON)</a>
<a href="/data/case-studies/gauge_basin_lookup.csv">Basin scope lookup (CSV)</a>
<a href="/data/case-studies/gauge_topology.csv">Traced gauge nesting, all confirmed pairs (CSV)</a>
<a href="/data/case-studies/gauge_topology_dominant_upstream.csv">Confluence pairs used in the mass-balance check (CSV)</a>
<a href="/data/case-studies/dry_spell_error_analysis.csv">Dry-spell error analysis (CSV)</a>
<a href="/data/case-studies/dry_spell_error_report.md">Held-out error report (MD)</a>
<a href="/data/case-studies/dry_spell_precursor_analysis.csv">Dry-spell precursors (CSV)</a>
</div>
<p class="muted">Pipelines: <code>python PIPELINES/build_gauge_topology.py</code> traces real upstream/downstream gauge nesting from CA-discharge's own delineated catchment polygons, then <code>python PIPELINES/train_pooled_transfer_model.py</code> re-runs the pooled model, calibration and mass-balance check end to end from <code>enhanced_discharge_features_aral.csv</code>. The <code>_aral</code> suffix marks feature files pre-filtered to Syr Darya / Amu Darya gauges and 1950+ (the years with real climate-station coverage). The modelling audit, including the leakage corrections and this study's stated limitations, ships in the repository under <code>CASE_STUDIES/</code>.</p></section>
</main>
{FOOTER}
<script type="module" src="/site-boot.js"></script></body></html>
"""
    OUT.write_text(html, encoding="utf-8")
    return {"page": str(OUT), "bytes": OUT.stat().st_size, "gauges_positive": pooled["per_gauge_positive"]}


if __name__ == "__main__":
    print(json.dumps(build()))
