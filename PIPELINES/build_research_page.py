"""Build the research foundations page from the publications registry.

The registry (PUBLISHED/data/research/publications.json) is the source of
truth; this page is its public rendering. Every entry is bound to the four
scientific layers and to a role in verification or validation, and the page
states plainly which side of the reproduction gate each use currently sits on.
Listing a method's paper here means the project implements or ingests it --
never that the project's implementation has passed independent scientific
reproduction.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "PUBLISHED/data/research/publications.json"
OUT = ROOT / "INTERFACE/research.html"

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

LAYER_LEDES = {
    "1": ("Reference atlas",
          "What characterises this place under a stated edition or baseline. Verification here means re-running published attribute recipes against pinned inputs and comparing family by family -- the reproduction gate no attribute has passed yet."),
    "2": ("Dated observations and evidence",
          "What was recorded or estimated here during this period. Verification here means unit, coverage and provenance checks on ingestion -- numerical support, not measurement accuracy."),
    "3": ("Analytical products",
          "How the record compares, varies or changes. Verification here means the analysis code is tested against reference implementations and every result carries its period, baseline and corrections."),
    "4": ("Evaluated models",
          "Can declared inputs explain or predict a target. Verification here means held-out evaluation against a seasonal-climatology benchmark, published with its split -- and separate from that, validation against external observations."),
}

ROLE_LABELS = {
    "method-source": "method source",
    "input-data": "input data",
    "reported-record": "reported record",
    "validation-target": "validation target",
    "verification-reference": "verification reference",
    "regional-context": "regional context",
}

STATUS_LABELS = {
    "in-use": "in use",
    "method-implemented": "method implemented",
    "reported-record": "reported record",
    "planned-integration": "planned integration",
}


def esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def entry_html(pub: dict) -> str:
    authors = esc(pub.get("authors", ""))
    title = esc(pub["title"])
    venue = esc(pub.get("venue") or "")
    link = pub.get("url")
    title_html = f'<a href="{esc(link)}" rel="noopener">{title}</a>' if link else title
    badges = " ".join(
        f'<span class="pub-badge role-{role}">{esc(ROLE_LABELS[role])}</span>'
        for role in [pub["role"]]
    ) + "".join(
        f'<span class="pub-badge status-{status}">{esc(STATUS_LABELS.get(status, status))}</span>'
        for status in [pub["status"]]
    )
    used_by = esc(", ".join(pub.get("used_by", [])))
    return (
        f'<article class="pub">'
        f'<p class="pub-citation">{authors} ({pub["year"]}). {title_html}.'
        + (f' <em>{venue}</em>.' if venue else "")
        + (f' <a href="{esc(link)}" rel="noopener">Open online &#8599;</a>' if link else "")
        + "</p>"
        f'<p class="pub-badges">{badges}</p>'
        f'<p class="pub-use">{esc(pub["use"])}</p>'
        + (f'<p class="pub-usedby">Used by: {used_by}.</p>' if used_by else "")
        + "</article>"
    )


def build() -> dict:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    layer_sections = []
    for key in "1234":
        pubs = [p for p in registry["publications"] if int(key) in p["layers"]]
        title, lede = LAYER_LEDES[key]
        articles = "\n".join(entry_html(p) for p in pubs)
        layer_sections.append(
            f'<section class="section" id="layer{key}">'
            f'<p class="eyebrow">LAYER {key} &middot; {esc(title).upper()}</p>'
            f"<h2>{esc(title)}</h2><p>{esc(lede)}</p>"
            f"{articles}</section>"
        )
    layers_html = "\n".join(layer_sections)

    planned = "\n".join(
        f'<article class="pub planned"><p class="pub-citation"><strong>{esc(t["name"])}</strong></p>'
        f'<p class="pub-use">{esc(t["note"])}</p>'
        f'<p class="pub-usedby">Citation status: {esc(t["citation_status"])}.</p></article>'
        for t in registry["planned_validation_targets"]
    )

    STYLE = (
        '<style>'
        '.pub{border:1px solid #c3cdd3;border-radius:8px;padding:1rem 1.2rem;margin:1rem 0;background:#fbfcfc}'
        '[data-theme="dark"] .pub{background:#0c1215;border-color:#1d282d}'
        '.pub-citation{margin:0 0 .5rem;font-size:.95rem;line-height:1.55}'
        '.pub-citation a{color:inherit}'
        '.pub-badges{margin:0 0 .55rem;display:flex;gap:.4rem;flex-wrap:wrap}'
        '.pub-badge{font-size:.68rem;font-weight:650;letter-spacing:.09em;text-transform:uppercase;padding:.22rem .5rem;border-radius:3px;border:1px solid #c3cdd3;color:#515f64}'
        '[data-theme="dark"] .pub-badge{border-color:#2a3a41;color:#8497a0}'
        '.pub-badge.role-method-source,.pub-badge.role-input-data{border-color:#7fb5c9;color:#0c6f8d}'
        '[data-theme="dark"] .pub-badge.role-method-source,[data-theme="dark"] .pub-badge.role-input-data{border-color:#2f6d8e;color:#6fc4de}'
        '.pub-badge.role-validation-target,.pub-badge.role-verification-reference{border-color:#c9a06b;color:#8a5a12}'
        '[data-theme="dark"] .pub-badge.role-validation-target,[data-theme="dark"] .pub-badge.role-verification-reference{border-color:#8a6a34;color:#d9b06a}'
        '.pub-badge.status-planned-integration{border-style:dashed}'
        '.pub-use{margin:0;font-size:.9rem;line-height:1.65;color:#3b4a52}'
        '[data-theme="dark"] .pub-use{color:#9fb3bb}'
        '.pub-usedby{margin:.45rem 0 0;font-size:.78rem;color:#515f64}'
        '[data-theme="dark"] .pub-usedby{color:#8497a0}'
        '.pub.planned{border-style:dashed}'
        '.ladder{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem;margin:1.3rem 0}'
        '.ladder div{border-left:3px solid #0c6f8d;padding:.2rem 0 .2rem 1rem}'
        '[data-theme="dark"] .ladder div{border-left-color:#4cc9f0}'
        '.ladder b{display:block;font-size:.95rem}'
        '.ladder span{font-size:.83rem;color:#3b4a52}'
        '[data-theme="dark"] .ladder span{color:#9fb3bb}'
        '</style>'
    )

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#103d40">
<meta name="description" content="Published research and data foundations of the UzGeoData public preview, bound to the four scientific layers with verification and validation status.">
<title>Research foundations &middot; UzGeoData</title>
<link rel="stylesheet" href="/home.css">{BOOT}
{STYLE}</head><body><a class="skip-link" href="#main">Skip to content</a>
{HEADER}
<main id="main" class="project-content">
<section class="page-intro"><p class="eyebrow">RESEARCH FOUNDATIONS</p>
<h1>Published research behind<br><em>every layer of the atlas.</em></h1>
<p class="lead">The datasets, methods and reported records this public preview is built from, bound to the four scientific layers and to a role in verification or validation. Listing a paper means we implement or ingest it -- it does not mean our implementation has passed independent scientific reproduction.</p>
<nav class="topic-links" aria-label="Layers"><a href="#layer1">01 Reference &#8595;</a><a href="#layer2">02 Observations &#8595;</a><a href="#layer3">03 Analysis &#8595;</a><a href="#layer4">04 Models &#8595;</a><a href="#planned">Validation targets &#8595;</a></nav></section>

<section class="section"><h2>How verification and validation are used here</h2>
<div class="ladder">
<div><b>Computational support</b><span>Inputs hashed, units checked, coverage retained. Establishes that a number was computed as declared -- not that it is accurate.</span></div>
<div><b>Held-out evaluation</b><span>Models scored on periods excluded from fitting, against a seasonal-climatology benchmark, with the split published beside the score.</span></div>
<div><b>Independent reproduction</b><span>Recipes re-run against pinned inputs by someone other than the original author, compared to the published baseline. The gate no atlas attribute has passed yet.</span></div>
</div>
<p class="muted">The registry behind this page is published as <a href="/data/research/publications.json">publications.json</a> and carries the same layer, role and status fields the page renders.</p></section>

{layers_html}

<section class="section" id="planned"><p class="eyebrow">PLANNED INTEGRATION</p>
<h2>Validation targets not yet integrated</h2>
<p>External evidence the research programme intends to compare against. Citations are completed at integration time rather than asserted in advance.</p>
{planned}</section>
</main>
{FOOTER}
<script type="module" src="/site-boot.js"></script></body></html>
"""
    OUT.write_text(html, encoding="utf-8")
    return {"page": str(OUT), "bytes": OUT.stat().st_size}


if __name__ == "__main__":
    print(json.dumps(build()))
