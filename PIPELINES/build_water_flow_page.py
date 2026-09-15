"""Generate the reviewed case study from its source-linked data and figures."""
from __future__ import annotations
import html
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
FLOW=ROOT/'PUBLISHED/data/water-flow'
OUT=ROOT/'INTERFACE/water-flow.html'


def build(out=OUT):
    d=json.loads((FLOW/'regional-water-flow.json').read_text())
    m=json.loads((FLOW/'regional-water-flow-sensitivity.json').read_text())
    sources={s['source_id']:s for s in d['sources']}
    esc=html.escape
    def cite(id):
        s=sources[id]
        return f'<a href="{esc(s["url"],quote=True)}">{esc(s["name"])}</a>'
    def figure(file,alt,caption):
        return f'<figure><a href="/data/water-flow/{file}"><img src="/data/water-flow/{file}" alt="{esc(alt)}" loading="lazy"/></a><figcaption>{caption} <a href="/data/water-flow/{file}">Open full-size SVG</a></figcaption></figure>'
    def table(head,rows,caption):
        return '<div class="table-scroll"><table><caption>'+caption+'</caption><thead><tr>'+''.join('<th scope="col">'+c+'</th>' for c in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(c)+'</td>' for c in r)+'</tr>' for r in rows)+'</tbody></table></div>'
    accounts=table(['Year','Country','Actual withdrawal','Limit','Limit used','Source'],[
       [r['year'],r['country'].title(),f"{r['withdrawal_km3']:.2f}",f"{r['limit_km3']:.2f}",f"{r['limit_utilisation_percent']:.1f}%",cite(f"cawater-yearbook-{r['year']}")] for r in d['country_withdrawals']], 'Amu Darya allocations: km³ per calendar year. Limit utilisation is calculated as actual ÷ limit.')
    totals=table(['Year','Amu reported withdrawal','Syr withdrawal above Shardara'],[[r['year'],f"{r['amu_withdrawal_km3']:.2f}",f"{r['syr_above_shardara_km3']:.2f}"] for r in d['reported_totals']], 'Reported withdrawals (km³/year). Boundaries differ; no combined regional water-stress denominator is inferred.')
    reservoirs=table(['Year','Reservoir','Inflow','Release','Inflow − release'],[[r['year'],r['reservoir'].title(),f"{r['inflow_km3']:.2f}",f"{r['release_km3']:.2f}",f"{r['inflow_minus_release_km3']:+.2f}"] for r in d['reservoir_accounts']], 'Reservoir accounts (km³/year), SIC ICWC yearbooks §2.1. The residual omits other water-balance terms.')
    env=table(['Year','Northern Aral','Amu delta, mixed delivery','Large Aral, collector drainage'],[[year]+[f"{next(r['volume_km3'] for r in d['environmental_deliveries'] if r['year']==year and r['scope']==scope):.4f}" for scope in ['northern_aral','amu_delta','large_aral']] for year in d['years']], 'Separate delivery records (km³/year), yearbooks §2.1–2.2.1. Additional display decimals do not imply measurement precision.')
    modeltable=table(['Product','Mean km³/year','Evidence type'],[[esc(m['variables'][v]['label']),f'{value:.2f}','Gridded model/estimate'] for v,value in m['means_km3'].items()]+[['TerraClimate P − AET',f"{m['means_km3']['pre_mm_s']-m['means_km3']['aet_mm_s']:.2f}",'Calculated difference']],f"Common complete years: {len(m['matched_years'])}. Spatial domain: {m['domain']['basins']:,} non-overlapping local basins.")
    missing=', '.join(esc(v['label']) for v in m['variables'].values() if v['status']!='available')
    optional=f'<p>Unavailable in this snapshot: {missing}. No replacement values are invented.</p>' if missing else '<p>Both runoff products are present in this snapshot and compared on identical years and basin areas. Their difference is a diagnostic of product disagreement, not evidence that either is correct.</p>'
    bibliography=''.join(f'<li id="source-{esc(s["source_id"])}">{cite(s["source_id"])}. {esc(s["role"])} <small>Accessed {esc(s["retrieved_at"])}.</small></li>' for s in d['sources'])
    download_names=[('regional-withdrawals.csv','Reported figures and row-level citations · CSV'),('regional-water-flow.json','Country, reservoir and delivery accounts · JSON'),('regional-model-annual.csv','Model annual totals and coverage · CSV'),('regional-water-flow-sensitivity.json','Model diagnostics, assumptions and input hashes · JSON'),('regional-water-flow-map.json','Map source hashes and landmark positions · JSON'),('sources.json','Source register · JSON')]
    downloads=''.join(f'<a href="/data/water-flow/{name}" download>{label} ↗</a>' for name,label in download_names)
    page=f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="Source-audited Amu Darya and Syr Darya withdrawals, reservoir flows and Aral deliveries, with TerraClimate and ERA5-Land model diagnostics."><title>Water withdrawals and downstream deliveries · UzGeoData</title><link rel="stylesheet" href="/home.css">
<style>
.wf-study{{max-width:1120px;margin:auto;padding:0 24px 64px;color:#243c40}}.wf-study h1{{font-size:clamp(34px,5vw,64px);line-height:1.08;letter-spacing:-.04em;margin:18px 0}}.wf-study h2{{font-size:30px;line-height:1.2;margin:0 0 20px}}.wf-study h3{{font-size:21px;margin-top:28px}}.wf-study p,.wf-study li{{line-height:1.75}}.wf-study a{{color:#126575;text-decoration:underline;text-underline-offset:3px}}.wf-study section{{padding:42px 0;border-bottom:1px solid #d8e2df;scroll-margin-top:25px}}.wf-study .lead{{font-size:20px;max-width:900px}}.wf-study .eyebrow{{letter-spacing:.12em;font-size:12px;font-weight:700;color:#176957}}.wf-study .notice{{border-left:4px solid #b58135;background:#faf5e9;padding:18px 22px}}.wf-study .summary{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:26px 0}}.wf-study .summary article{{background:#f0f5f3;padding:22px;border-radius:8px}}.wf-study .summary strong{{display:block;font-size:25px;color:#116a57}}.wf-study .summary span{{display:block;font-size:13px;margin-top:8px}}.wf-study .toc{{display:flex;flex-wrap:wrap;gap:14px 22px;font-size:14px;margin-top:28px}}.wf-study figure{{margin:26px 0}}.wf-study figure img{{width:100%;height:auto;display:block;background:#fcfcfa;border:1px solid #dce5e1;border-radius:8px}}.wf-study figcaption{{font-size:13px;line-height:1.6;margin-top:10px;color:#526669}}.wf-study .table-scroll{{overflow:auto;margin:24px 0}}.wf-study table{{border-collapse:collapse;width:100%;font-size:14px;min-width:620px}}.wf-study caption{{text-align:left;font-size:13px;padding:0 0 12px;color:#526669}}.wf-study th,.wf-study td{{padding:12px;text-align:left;border-bottom:1px solid #dce5e1;vertical-align:top}}.wf-study th{{background:#f0f5f3;font-weight:600}}.wf-study small{{font-size:12px;color:#526669}}.wf-study .equation{{background:#f0f5f3;padding:18px;font:16px/1.7 monospace;overflow-wrap:anywhere}}.wf-study .downloads{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}}.wf-study .downloads a{{padding:16px;background:#f0f5f3;border-radius:6px}}.wf-study details{{border:1px solid #dce5e1;padding:18px;margin:20px 0;border-radius:8px}}.wf-study summary{{cursor:pointer;font-weight:600}}@media(max-width:680px){{.wf-study{{padding:0 16px 40px}}.wf-study .summary,.wf-study .downloads{{grid-template-columns:1fr}}.wf-study h2{{font-size:26px}}.wf-study figure{{margin-inline:-6px}}.site-header nav{{flex-wrap:wrap}}}}
</style></head><body><a class="skip-link" href="#main">Skip to content</a>
<header class="site-header"><a class="brand" href="/">UzGeoData</a><nav aria-label="Main navigation"><a href="/case-studies.html">All case studies</a><a href="/guide.html">Data guide</a><a href="/">Basin explorer ↗</a></nav></header>
<main id="main" class="wf-study">
<section><p class="eyebrow">REGIONAL WATER ACCOUNTING · SOURCE REVIEW {d['reviewed_at']}</p>
<h1>Water withdrawals.<br>Downstream deliveries.<br>What the evidence supports.</h1>
<p class="lead">A study of the Amu Darya and Syr Darya that distinguishes reported withdrawals, reservoir flows and environmental deliveries from modelled land-water estimates.</p>
<p class="notice"><strong>Evidence status:</strong> descriptive accounting checked against cited primary reports. This study is not an independently validated national water balance or a discharge forecast. Reported numbers are traceable; uncertainty and missing flows remain explicit.</p>
<div class="summary"><article><strong>{len(d['years'])} reporting years</strong><span>2022–2024 · January–December</span></article><article><strong>{len(m['matched_years'])} common years</strong><span>Model comparison · 2003–2024</span></article><article><strong>{m['domain']['basins']:,} basins</strong><span>Model domain · {m['domain']['area_km2']:,.1f} km²</span></article></div>
<nav class="toc" aria-label="Study sections"><a href="#geography">Geography</a><a href="#accounts">Country accounts</a><a href="#reservoirs">Reservoirs</a><a href="#aral">Aral deliveries</a><a href="#models">Model comparison</a><a href="#validation">Discharge modelling</a><a href="#savings">Water savings</a><a href="#evidence">Sources &amp; downloads</a></nav></section>
<section id="geography"><p class="eyebrow">01 / SPATIAL CONTEXT</p><h2>Follow the reporting boundary before the number</h2>
{figure('regional-water-flow-map.svg','Mapped Amu Darya and Syr Darya basin systems, river network and selected reservoir landmarks.','Figure 1. Real published geometries, simplified for display. Country borders and water transfers are not inferred from basin boundaries. The same map appears on the case-study directory card.')}
<p>The two rivers cross political borders and managed water can cross catchment divides through canals. Afghanistan is an Amu Darya riparian, but its abstraction is outside the three-country table transcribed here. Missing entries for Afghanistan, Kyrgyzstan or Kazakhstan must not be read as zero water use.</p>
<p>The model domain is the project’s mapped basin union. The ICWC accounts describe specific river reaches and water-management systems. Equal units do not make those spatial supports equivalent. A regional rainfall total cannot be split into national inflows using country withdrawal shares.</p></section>
<section id="accounts"><p class="eyebrow">02 / REPORTED WITHDRAWALS</p><h2>Country withdrawals are not country inflows and outflows</h2>
<p>The yearbooks distinguish hydrological-year quota setting from their calendar-year reporting. This study uses the latter. The Amu Darya country withdrawals reconcile with each reported annual total. Limits are shown as separate markers, not extra water. Sources: {cite('cawater-yearbook-2022')}, {cite('cawater-yearbook-2023')}, {cite('cawater-yearbook-2024')}.</p>
{figure('regional-water-flow.svg','Three zero-based country withdrawal charts for 2022, 2023 and 2024, with allocation limits marked separately.','Figure 2. Identical horizontal scales; bar length encodes withdrawal only. Exact source values are in the table below.')}
{accounts}{totals}
<p>The Syr Darya figures cover withdrawal upstream of the entry to Shardara reservoir. A country breakdown is not supplied in this transcription. Kazakhstan’s downstream withdrawals are outside that total, but this does not imply that all Kazakhstan abstractions are downstream. The aggregate is not coloured as if it belonged solely to Uzbekistan.</p>
<h3>The balance a national flow diagram would actually need</h3>
<p class="equation">ΔS = P + Q_in + G_in + T_in − ET − Q_out − G_out − T_out</p>
<p>All terms must share a boundary and period: storage change (ΔS), precipitation (P), evaporation/transpiration (ET), river flows (Q), groundwater exchanges (G), and managed transfers (T). Withdrawals and return flows inside that boundary are internal transfers; subtracting withdrawals again after counting their evaporation can double-count water. A country diagram additionally needs cross-border gauges, canals, return flows and reservoir storage.</p>
<p>No complete country inflow/outflow dataset is assembled here. Those quantities are null in the downloadable accounts. The former connected diagram has been replaced because a plausible-looking link was implying a physical balance the source data did not establish.</p></section>
<section id="reservoirs"><p class="eyebrow">03 / MATCHED INFLOW AND RELEASE</p><h2>Use actual reservoir accounts where available</h2>
{reservoirs}
<p>These paired figures refer to the same named reservoir and year. A release greater than inflow can reflect storage drawdown; it is not automatically a data error. Conversely, inflow minus release is not a fully observed storage change because precipitation, evaporation, seepage and reporting differences also enter the balance. The yearbooks are the source for these records; they are not independent gauges validated by this project.</p></section>
<section id="aral"><p class="eyebrow">04 / DOWNSTREAM OUTCOMES</p><h2>The delta and the sea are different destinations</h2>
{figure('regional-water-flow-deliveries.svg','Reported annual delivery volumes at the Northern Aral, Amu delta and Large Aral for 2022–2024.','Figure 3. Separate observed reporting destinations. Bars are not stacked because the observations do not define a complete additive partition.')}
{env}
<p>The delta series includes mixed river, canal and drainage deliveries. The cited records identify the South Karakalpak collecting drain as the Large Aral supply route in these years, bypassing the delta. Consequently, the study does not draw a delta-to-sea arrow for that drainage, or deduct delta deliveries from Uzbekistan’s country withdrawal. Detailed source locations are retained in every CSV row.</p></section>
<section id="models"><p class="eyebrow">05 / MODEL DIAGNOSTICS</p><h2>TerraClimate is already the precipitation input</h2>
<p>The published precipitation and actual evapotranspiration series use TerraClimate. ERA5-Land supplies a separate runoff estimate. TerraClimate runoff is treated as another product with its own identity; replacing precipitation and replacing runoff are different modelling decisions.</p>
{figure('regional-water-flow-sensitivity.svg','Annual TerraClimate precipitation and evapotranspiration, followed by separate P minus AET and runoff comparisons on the same domain.','Figure 4. Gridded estimates, not measured national water supply. Lines use the downloadable annual totals. Missing domain-years are withheld; zero is a real zero only.')}
{modeltable}{optional}
<h3>Reproducible calculation and completeness</h3>
<p class="equation">Annual volume (km³) = Σ_basins [Σ_12 months depth (mm) × local basin area (km²) × 10⁻⁶]</p>
<p>The calculation uses the files named by the cube manifest and a fixed 2003–2024 window. Each basin/variable/year must contain 12 distinct finite monthly values. A regional total is withheld unless every domain basin is complete. Duplicates, incompatible units and unknown basin IDs fail the build. Means use the common set of complete years; intermediate arithmetic is not rounded.</p>
<p>These checks establish numerical support, not measurement accuracy. The compact cube lacks pixel-level coverage, detailed revisions and gauge validation. The downloads retain the cube, geometry and partition SHA-256 hashes used for this calculation.</p>
<h3>What the model difference means</h3>
<p>TerraClimate uses a simplified climatic water-balance model; its runoff is not routed discharge. Its published validation discusses mountain precipitation biases and limitations of the bucket model. Agreement between its P − AET and runoff is partly shared model structure, not independent confirmation. {cite('terraclimate-paper')}.</p>
<p>Its provider cautions about inherited temporal variability and fixed land-cover assumptions. Finer grid spacing alone does not establish more accurate precipitation or discharge in these headwaters. {cite('terraclimate-provider')}. Band units and scaling are documented in {cite('terraclimate-ee')}; the reanalysis runoff definition is documented by {cite('era5-provider')}.</p>
<p class="notice">P − AET is a land-water diagnostic. It is not a measured volume available for diversion. This revision removes historical “stress” and “supply exceeded” counts that compared it with a constant 2022 withdrawal, and removes an unsupported regional balance residual.</p></section>
<section id="validation"><p class="eyebrow">06 / DISCHARGE MODEL DESIGN</p><h2>Test TerraClimate fairly before selecting a winner</h2>
<p>A global comparison of precipitation forcings found strong geographical variation in discharge performance; no single product won everywhere. That evidence supports local testing, not automatic replacement. {cite('precipitation-evaluation')}. Work on the Naryn demonstrates why snow/glacier processes and gauge evaluation matter in Central Asian headwaters. {cite('naryn-model')}.</p>
<ol><li><strong>Define the target.</strong> Choose a gauge and delineate its contributing catchment. Distinguish observed regulated flow from reconstructed natural flow. Convert discharge to monthly volume using actual elapsed seconds and retain missing-day counts.</li>
<li><strong>Match the comparison.</strong> Extract TerraClimate and alternative precipitation over exactly the same geometry and period. Record source versions, gauge elevation, units and any bias correction. Keep corrections fitted on training data only.</li>
<li><strong>Separate forcing from model structure.</strong> Run the same snow/soil/storage/routing model with each precipitation forcing. Compare provider runoff products in a separate experiment. Include reservoirs, abstractions and returns for managed downstream gauges; precipitation alone cannot represent them.</li>
<li><strong>Validate out of sample.</strong> Use chronological training and held-out evaluation, with wet/dry and snowmelt seasons represented. Compare NSE, KGE, volume bias, seasonal timing and low-flow errors against a training-derived seasonal climatology. Evaluate uncertainty and sensitivity across plausible parameters and forcing products.</li>
<li><strong>Promote only supported results.</strong> Publish paired observations/predictions, excluded periods, parameters, input hashes and the decision criterion. A locally better forcing does not automatically transfer to every basin.</li></ol>
<p>The repository’s <a href="/case-studies/chirchik">Pskem/Chirchik study</a> provides an existing modelling and evaluation context. This accounting review does not retrain that model or claim that TerraClimate has passed a new gauge benchmark.</p></section>
<section id="savings"><p class="eyebrow">07 / WATER-SAVING CLAIMS</p><h2>Distinguish reduced withdrawal from real basin savings</h2>
<p>FAO distinguishes withdrawal reductions from real savings in consumption and non-recoverable flows. If reduced canal seepage previously returned downstream, improved delivery efficiency can reduce return flow as well as withdrawal. {cite('fao-real-savings')}.</p>
{figure('regional-water-flow-pathway.svg','Hypothetical efficiency example showing identical gross withdrawal reductions but different downstream gains as return-flow recoverability changes.','Figure 5. Dimensionless illustration, not a calibrated scenario. Recoverable fractions are selected examples, not measured bounds.')}
<p class="equation">Gross reduction = W₀ × (1 − η₀ / η₁)<br>Illustrative net gain = gross reduction × (1 − recoverable fraction)</p>
<p>The illustration holds delivered demand fixed and uses efficiencies of 0.63 and 0.73. Its units are per 100 initially withdrawn, not km³ per year. It assumes no expansion or rebound and does not predict an environmental delivery. National targets from different jurisdictions and reporting scales are not summed into a basin forecast.</p></section>
<section id="evidence"><p class="eyebrow">08 / EVIDENCE AND REPRODUCTION</p><h2>Sources, downloadable numbers and review trail</h2>
<div class="downloads">{downloads}</div>
<h3>Source register</h3><ol>{bibliography}</ol>
<details><summary>What changed in this scientific review</summary><ul>
<li>Corrected calendar-year labels and expanded reported accounting to 2022–2024.</li>
<li>Removed invented connections between modelled climatic balance, country withdrawals, sectoral allocations, wastewater and environmental flows.</li>
<li>Corrected the collector-drainage route and removed misleading single-country colouring of the Syr Darya aggregate.</li>
<li>Rebuilt annual model totals with non-null, duplicate-month and full-domain coverage checks.</li>
<li>Removed extrapolated historical shortage counts and multi-country policy savings; added explicit return-flow arithmetic.</li>
<li>Added the geographic overview, matching data tables, source locators and executable regression checks.</li></ul></details>
<h3>Limits and next evidence</h3><p>Source summaries do not provide comparable uncertainty intervals for these figures. Country withdrawals omit parts of the wider regional system; model fields omit managed routing. A closed accounting study needs matched border gauges and canal transfers, reservoir storage, return-flow quantity and quality, groundwater abstraction and consumptive use. Future extensions should add those records before constructing a national flow balance.</p>
<p>Reported statistics are cited with their publishers; no blanket upstream reuse licence is asserted. Code and input hashes enable computational checks, while independent scientific validation requires external measurements and review.</p>
<p><small>Built {d['generated_at']}. Model diagnostics built {m['generated_at']}. Rebuild from the repository with <code>npm run cases:water-flow</code>. Review details: <a href="https://github.com/tim7en/uzgeodata/blob/main/docs/WATER_FLOW_REVIEW.md">method and validation notes</a>.</small></p></section>
</main><footer class="site-footer"><a href="/case-studies.html">All research case studies</a><a href="/">Explore the basin atlas</a><a href="/guide.html">Data access and citation</a></footer></body></html>'''
    Path(out).write_text(page,encoding='utf-8')
    return {'page':str(out),'bytes':len(page.encode())}


if __name__=='__main__':print(build())
