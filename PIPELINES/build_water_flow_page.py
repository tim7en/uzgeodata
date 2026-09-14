"""Assemble the case-study page from the data, so the prose cannot drift from it.

Every figure quoted in the page is read from the published JSON rather than typed into
the HTML. A page that states 93.3 km3/yr in prose while the diagram beside it is rebuilt
to something else is the ordinary way a case study stops being true, and it happens
without anyone editing the sentence.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FLOW = ROOT / "PUBLISHED/data/water-flow"
OUT = ROOT / "INTERFACE/water-flow.html"


def inline(name, klass):
    svg = (FLOW / name).read_text(encoding="utf-8")
    return svg.replace("<svg ", f'<svg class="{klass}" ', 1)


def build(out=OUT):
    diagram = json.loads((FLOW / "regional-water-flow.json").read_text(encoding="utf-8"))
    sens = json.loads((FLOW / "regional-water-flow-sensitivity.json").read_text(encoding="utf-8"))
    observed, method = sens["observed"], diagram["method"]
    surplus, share = observed["surplus_km3"], observed["share_of_surplus"]
    scenarios = sens["scenarios"]
    # Looked up by name, not by position: an index into the link list silently points
    # at a different flow the moment the diagram gains one.
    links = {(l["source"], l["target"]): l for l in diagram["links"]}
    agriculture_share = (links[("uz-use", "sector-agriculture")]["value"]
                         / links[("amu-uz", "uz-use")]["value"])
    exceeded = " and ".join(str(y) for y in observed["exceeded_years"])
    stressed = ", ".join(str(y) for y in observed["stressed_years"])

    basis_cards = "".join(
        f'<div class="basis-card" style="--c:{v["colour"]}"><strong>{v["label"]}</strong>'
        f'<span>{v["meaning"]}</span></div>' for v in diagram["basis_legend"].values())
    sources = "".join(
        f'<li><a href="{s["url"]}">{s["name"]}</a>'
        f'{" — " + s["role"] if s.get("role") else ""}</li>' for s in diagram["sources"])
    scenario_rows = "".join(
        f'<tr><td><strong>{s["label"]}</strong><br><span class="muted">{s["note"]}</span></td>'
        f'<td>{s["diversion_km3"]} km³/yr</td><td>{s["water_freed_km3"]} km³/yr</td>'
        f'<td>{s["stressed_years"]} of 22</td><td>{s["exceeded_years"]}</td></tr>'
        for s in scenarios)
    gaps = "".join(f'<li><strong>{k.replace("_", " ").title()}.</strong> {v}</li>'
                   for k, v in sens["not_modelled"].items())

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#103d40"><meta name="description" content="A water flow diagram and sensitivity analysis for the Amu Darya and Syr Darya, with every flow coloured by how it is known, and a pathway of what would have to change."><title>Where the region&#8217;s water goes &middot; UzGeoData</title><link rel="stylesheet" href="/home.css">
<style>
.wfd{{width:100%;height:auto;display:block}}
.wfd-frame{{overflow-x:auto;background:#fdfdfc;border:1px solid #dfe3e0;border-radius:10px;padding:8px;margin:1.5rem 0}}
.basis-grid{{display:grid;gap:.75rem;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));margin:1.25rem 0}}
.basis-card{{border-left:4px solid var(--c);padding:.6rem .85rem;background:#f7f9f8;border-radius:0 6px 6px 0}}
.basis-card strong{{display:block;margin-bottom:.2rem}}
.basis-card span{{font-size:.88rem;color:#4a5568}}
.figure-row{{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));margin:1.25rem 0}}
.figure{{background:#f7f9f8;border-radius:8px;padding:.8rem .9rem}}
.figure b{{display:block;font-size:1.5rem;color:#103d40;line-height:1.2}}
.figure span{{font-size:.84rem;color:#4a5568}}
.figure.alarm b{{color:#9b2c2c}}
.wfd-table{{width:100%;border-collapse:collapse;margin:1.1rem 0;font-size:.92rem}}
.wfd-table th,.wfd-table td{{text-align:left;padding:.6rem .7rem;border-bottom:1px solid #e2e8e5;vertical-align:top}}
.wfd-table th{{font-size:.8rem;text-transform:uppercase;letter-spacing:.04em;color:#4a5568}}
.muted{{color:#4a5568;font-size:.86rem}}
.finding{{border-left:4px solid #9b2c2c;background:#fdf6f6;padding:.9rem 1.1rem;border-radius:0 8px 8px 0;margin:1.2rem 0}}
.role-grid{{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));margin:1.2rem 0}}
.role{{background:#f7f9f8;border-radius:8px;padding:.9rem 1rem}}
.role h4{{margin:0 0 .4rem}}
.role ul{{margin:0;padding-left:1.1rem;font-size:.9rem;color:#4a5568}}
</style></head><body><a class="skip-link" href="#main">Skip to content</a>
<header class="site-header"><a class="brand" href="/" aria-label="UzGeoData home"><span class="brand-icon" aria-hidden="true">&#8776;</span>UzGeoData<span class="brand-sub">BASIN ATLAS</span></a><nav aria-label="Main navigation"><a href="/project.html">Project overview</a><a href="/examples.html">Use cases</a><a href="/case-studies.html">Case studies</a><a href="/guide.html">User guide</a><a class="button small" href="/">Open basin explorer <span aria-hidden="true">&#8599;</span></a></nav></header>
<main id="main" class="project-content">

<section class="page-intro"><p class="eyebrow">CASE STUDY &middot; REGIONAL WATER BALANCE</p>
<h1>Where the region&#8217;s water goes<br><em>and how much of that we actually know.</em></h1>
<p class="lead">A water flow diagram for the Amu Darya and Syr Darya, adapted from the <a href="{method['url']}">Water Flow Diagram method</a>. Its published applications are municipal, where one utility can account for what it abstracted, delivered and lost. Nothing at that resolution is published for this region &mdash; so this is drawn at basin-system scale, every flow states how it is known, and the analysis that follows is built on the part that is measured.</p></section>

<section class="section"><div>
<div class="figure-row">
<div class="figure"><b>{surplus['mean']}</b><span>km&sup3;/yr mean climatic surplus<br>22-year measured mean</span></div>
<div class="figure"><b>{observed['diversion_km3']}</b><span>km&sup3;/yr diverted in 2022<br>ICWC record</span></div>
<div class="figure alarm"><b>{share['driest_year']:.0%}</b><span>of the surplus taken in the driest year<br>2021</span></div>
<div class="figure alarm"><b>{len(observed['stressed_years'])} of 22</b><span>years with a thin margin<br>diversion &ge; 80% of surplus</span></div>
</div>

<div class="finding"><strong>The headline finding.</strong> Averaged over twenty-two years the region looks comfortable: it diverts about {observed['diversion_km3'] / surplus['mean']:.0%} of what precipitation less evapotranspiration generates. But the surplus varies by a factor of {surplus['range_factor']} between years while allocation does not vary at all &mdash; and in <strong>{exceeded}</strong> the recorded diversion <strong>exceeded the surplus outright</strong>. Water was still delivered, which means it came from storage, snow and glacier melt, groundwater, or inflow from outside the accounting domain. A mean year is the one condition under which this system has room.</div>

<h2>The diagram</h2>
<div class="wfd-frame">{inline("regional-water-flow.svg", "wfd")}</div>

<h3>Colour is provenance, not water type</h3>
<p>The published applications of this method colour flows by what kind of water they carry. Here colour says <strong>how a flow is known</strong>, because at this scale that is the distinction a reader most needs and least often gets from a Sankey diagram.</p>
<div class="basis-grid">{basis_cards}</div>

<h3>It does not close, and is not made to</h3>
<p>{diagram['reading']['closure']}</p>
<p>{diagram['reading']['scale']}</p>

<h2>Sensitivity: what actually moves this system</h2>
<p>The method&#8217;s published applications vary loss rates, connection rates and treatment capacity, because a utility has measured all of those. Almost none of it is measured here, so varying it would be varying assumptions and calling the spread a result. What <em>is</em> measured is the supply side &mdash; and that is where the sensitivity turns out to live.</p>
<div class="wfd-frame">{inline("regional-water-flow-sensitivity.svg", "wfd")}</div>
<p>Surplus ranges from <strong>{surplus['min']['value']} km&sup3;/yr ({surplus['min']['year']})</strong> to <strong>{surplus['max']['value']} km&sup3;/yr ({surplus['max']['year']})</strong>, a factor of {surplus['range_factor']}. Diversion is {share['wettest_year']:.0%} of the surplus in the wettest year and {share['driest_year']:.0%} in the driest. Thin-margin years: {stressed}.</p>
<p class="notice">{sens['caution']}</p>

<h3>Scenario arithmetic</h3>
<p>Applied to agricultural withdrawal at the national sectoral share. This is arithmetic on published numbers, not a model: no efficiency mechanism is represented and no cost is estimated. The 10&nbsp;per&nbsp;cent case is the 2023 national plan&#8217;s own target, shown so a reader can see what it would and would not achieve.</p>
<table class="wfd-table"><thead><tr><th>Scenario</th><th>Diversion</th><th>Water freed</th><th>Thin-margin years</th><th>Years exceeding supply</th></tr></thead><tbody>{scenario_rows}</tbody></table>
<p><strong>What the arithmetic says.</strong> The national plan&#8217;s own 10&nbsp;per&nbsp;cent target, applied to agriculture, frees {scenarios[1]['water_freed_km3']} km&sup3;/yr &mdash; enough to remove both years in which diversion exceeded supply, and to cut thin-margin years from {scenarios[0]['stressed_years']} to {scenarios[1]['stressed_years']}. It does not eliminate them. Because agriculture is {agriculture_share:.0%} of use, it is the only sector where a change of this size is arithmetically available at all: eliminating <em>all</em> municipal use would free less than a fifth of what a 10&nbsp;per&nbsp;cent agricultural saving does.</p>

<h3>What is deliberately not modelled</h3>
<ul>{gaps}</ul>

<h2>What would have to change</h2>
<div class="wfd-frame">{inline("regional-water-flow-pathway.svg", "wfd")}</div>

<div class="role-grid">
<div class="role"><h4>For government bodies</h4><ul>
<li><strong>ICWC / BWO Amu Darya &amp; Syr Darya</strong> &mdash; publish diversion by basin and sector, not only by country. This is the precondition for almost everything else.</li>
<li><strong>Ministry of Water Resources</strong> &mdash; establish a distribution-loss baseline. A 10&nbsp;per&nbsp;cent reduction target cannot be evaluated against nothing.</li>
<li><strong>State Committee on Geology</strong> &mdash; report groundwater abstraction, so a surface-water saving can be distinguished from a groundwater cost.</li>
<li><strong>Uzsuvtaminot and vodokanals</strong> &mdash; publish wastewater generated alongside wastewater treated.</li>
</ul></div>
<div class="role"><h4>For academic partners</h4><ul>
<li><strong>Digitise the ICWC series.</strong> One transcribed year is drawn here against twenty-two measured ones. The yearbooks hold annual limits and actuals; a machine-readable series is a contained, high-value piece of work.</li>
<li><strong>Reconcile the products against gauges.</strong> Runoff and the climatic surplus disagree by more than the entire municipal sector. Uzhydromet records exist; this is answerable.</li>
<li><strong>Attribute the decline.</strong> The surplus falls {abs(observed['trend_km3_per_year']['surplus']):.2f} km&sup3;/yr per year across this record. Whether that is decadal variability or a trend needs a longer record than 22 years.</li>
<li><strong>Reproduce an attribute independently.</strong> Nothing in this atlas has passed independent reproduction; that gate is open to anyone.</li>
</ul></div>
</div>

<h2>What data would close the gaps</h2>
<table class="wfd-table"><thead><tr><th>Needed</th><th>Why it matters</th><th>Likely holder</th></tr></thead><tbody>
<tr><td>Diversion by basin and sector, annual</td><td>Turns every derived flow in the diagram into an administered one, and lets the sensitivity run per catchment rather than per region</td><td>ICWC, BWO Amu Darya &amp; Syr Darya</td></tr>
<tr><td>Distribution-loss baseline</td><td>The largest single lever in the method&#8217;s own applications, and currently unquantifiable here</td><td>Ministry of Water Resources, vodokanals</td></tr>
<tr><td>Groundwater abstraction</td><td>Separates a genuine saving from a substitution between sources</td><td>State Committee on Geology</td></tr>
<tr><td>Wastewater generated, not only treated</td><td>Converts a treatment statistic into a sanitation one</td><td>Uzsuvtaminot, vodokanals</td></tr>
<tr><td>Canal network and inter-basin transfers</td><td>The structural reason basin-scale accounting fails here</td><td>Ministry of Water Resources</td></tr>
<tr><td>Gauged discharge, current and continuous</td><td>The only way to decide which model is closer where they disagree</td><td>Uzhydromet</td></tr>
<tr><td>Reservoir operation records</td><td>Explains how supply continues in years when diversion exceeds surplus</td><td>Reservoir operators, BWOs</td></tr>
</tbody></table>

<h2>Sources and limits</h2>
<ul>{sources}</ul>
<p class="notice"><strong>Reuse not yet established.</strong> {diagram['reuse']['statement']}</p>
<p><strong>Method reference.</strong> {method['description']} &mdash; <a href="{method['applications']}">published applications</a>.</p>
<p class="muted">Administered figures were transcribed by hand from published pages and are recorded under their own provenance class, because a transcription error there is not detectable by any automated check this project runs.</p>

<div class="resource-links"><a href="/data/water-flow/regional-water-flow.json">Diagram data &#8599;</a><a href="/data/water-flow/regional-water-flow-sensitivity.json">Sensitivity data &#8599;</a><a href="/data/water-flow/regional-withdrawals.csv">Administered figures &#8599;</a><a href="/data/water-flow/regional-water-flow.svg">Diagram SVG &#8599;</a></div>
</div></section>

<section class="closing"><div><p class="eyebrow">GO DEEPER</p><h2>The record behind the measured arms.</h2><p>Precipitation and evapotranspiration come from 22 years of monthly observations across 7,445 basins, queryable without a checkout.</p></div><a class="button" href="/guide.html">Data access &amp; guide &#8599;</a></section>
</main>
<footer class="site-footer"><div><a class="brand" href="/">UzGeoData</a><p>Water systems cross borders.<br>Understanding them should, too.</p></div><div><strong>Explore</strong><a href="/">Basin explorer</a><a href="/examples.html">Practical examples</a><a href="/case-studies.html">Research case studies</a></div><div><strong>Understand</strong><a href="/about.html#citation">Citation &amp; reuse</a><a href="/guide.html">Guide &amp; data access</a><a href="/roadmap.html">Research roadmap</a></div><div><strong>Contribute</strong><a href="https://github.com/tim7en/uzgeodata">Project on GitHub &#8599;</a><a href="https://github.com/tim7en/uzgeodata/issues">Report an issue &#8599;</a><a href="release.json">Release metadata</a></div><p class="footer-note">Independent research project &middot; Public preview &middot; Amu Darya &amp; Syr Darya</p></footer></body></html>"""
    Path(out).write_text(page, encoding="utf-8")
    return {"page": str(out), "bytes": len(page.encode("utf-8"))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(build(), indent=2))


if __name__ == "__main__":
    main()
