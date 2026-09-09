import React, { useState } from 'react';
import { Download, Check, X, CircleDashed } from 'lucide-react';
import usePublishedData from './usePublishedData.js';

const SOURCE = '/data/case-studies/reproducibility-package.json';
const BASE = '/data/case-studies/';

const R_SNIPPET = [
  'daily  <- read.csv("pskem_daily.csv")',
  'scores <- read.csv("model_scores.csv")',
  'subset(scores, evaluation == "chronological" & metric == "nse")',
].join(String.fromCharCode(10));

const TABS = [
  ['data', 'Data', 'Can I obtain the same input data?'],
  ['method', 'Method', 'Can I run the same procedure?'],
  ['results', 'Results', 'What did this study actually produce?'],
  ['verification', 'Verification', 'Do I obtain approximately the same result?'],
  ['tests', 'Tests', 'What is checked automatically?'],
  ['transferability', 'Transfer', 'Does the method work elsewhere, or later?'],
  ['downloads', 'Tables', 'How do I get this into R or pandas?'],
];

const short = value => (value == null ? '—' : String(value).slice(0, 12));
const number = value => (typeof value === 'number' ? value.toLocaleString('en', { maximumFractionDigits: 3 }) : value);
const kb = bytes => (bytes == null ? '—' : bytes > 1e6 ? `${(bytes / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1000))} kB`);

/**
 * The study as a package someone else could pick up.
 *
 * Everything shown is read from `reproducibility-package.json`, which the
 * pipeline refuses to write unless every stage resolves to a real npm script,
 * every declared artefact is on disk, and every published number can be read
 * back out of the file that holds it. So this section cannot describe a
 * procedure the repository no longer contains — if it drifts, the build fails
 * before the page is written.
 */
export default function ReproducibilityPackage() {
  const { data, error, retry } = usePublishedData(SOURCE);
  const [tab, setTab] = useState('data');

  if (error) return <section id="reproducibility" className="cs-panel" role="alert">
    <h2>Reproducibility package unavailable</h2><p>{error}</p>
    <button onClick={retry}>Retry</button>
  </section>;
  if (!data) return <section id="reproducibility" className="cs-panel" role="status">Loading the reproducibility package…</section>;

  const { counts, verification, transferability } = data;
  const rerun = verification.rerun;

  return <section id="reproducibility" className="cs-panel cs-package">
    <div className="cs-section-head">
      <div>
        <span className="cs-eyebrow">RESEARCH PACKAGE / DATA · METHOD · RESULTS · TESTS · DOWNLOAD</span>
        <h2>Everything needed to run this study again.</h2>
      </div>
      <p>{data.study.question}</p>
    </div>

    <div className="cs-score-grid cs-package-tally">
      <div><strong>{counts.inputFiles}</strong><span>Input files, each hashed</span></div>
      <div><strong>{counts.stages}</strong><span>Pipeline stages, each runnable</span></div>
      <div><strong>{counts.testCases}</strong><span>Automated checks</span></div>
      <div><strong>{rerun.reproduced ? 'Yes' : 'No'}</strong><span>Rebuild reproduces the published study</span></div>
    </div>

    <div className="cs-package-tabs" role="tablist" aria-label="Reproducibility package sections">
      {TABS.map(([id, label, question]) => <button key={id} role="tab" aria-selected={tab === id}
        onClick={() => setTab(id)} title={question}>{label}</button>)}
    </div>
    <p className="cs-note cs-package-question">{TABS.find(([id]) => id === tab)[2]}</p>

    {tab === 'data' && <>
      <div className="cs-table-wrap"><table>
        <thead><tr><th>Input file</th><th>Role</th><th>Size</th><th>SHA-256</th><th>State</th></tr></thead>
        <tbody>{data.data.files.map(file => <tr key={file.path}>
          <td><code>{file.path}</code></td>
          <td>{file.role}</td>
          <td>{kb(file.bytes)}</td>
          <td><code>{short(file.sha256)}</code></td>
          <td>{!file.available ? <span className="cs-status">missing</span>
            : file.changedSinceRecorded ? <span className="cs-status">changed since recorded</span>
              : <span><Check size={12} /> matches</span>}</td>
        </tr>)}</tbody>
      </table></div>
      {data.data.remoteAssets.length > 0 && <>
        <h3>Remote sources</h3>
        <div className="cs-table-wrap"><table>
          <thead><tr><th>Catalogue asset</th><th>Used as</th><th>Reduced on</th></tr></thead>
          <tbody>{data.data.remoteAssets.map(asset => <tr key={asset.asset}>
            <td><code>{asset.asset}</code></td><td>{(asset.usedAs || []).join(', ')}</td><td>{(asset.retrievedAt || '').slice(0, 10) || '—'}</td>
          </tr>)}</tbody>
        </table></div>
      </>}
      <p className="cs-note">{data.data.note}</p>
    </>}

    {tab === 'method' && <>
      <ol className="cs-package-stages">{data.method.map(stage => <li key={stage.id}>
        <div className="cs-package-stage-head"><strong>{stage.title}</strong><code>{stage.command}</code></div>
        <p>{stage.purpose}</p>
        <details><summary>{stage.produces.length} artefact{stage.produces.length === 1 ? '' : 's'} · underlying command</summary>
          <pre>{stage.runs}</pre>
          <div className="cs-table-wrap"><table>
            <thead><tr><th>Produces</th><th>Size</th><th>SHA-256</th></tr></thead>
            <tbody>{stage.produces.map(output => <tr key={output.path}>
              <td><code>{output.path}</code></td><td>{kb(output.bytes)}</td><td><code>{short(output.sha256)}</code></td>
            </tr>)}</tbody>
          </table></div>
        </details>
      </li>)}</ol>
      <p className="cs-note">Stages run in this order. The package build fails if any command here is not defined in the repository or any artefact is absent, so this list cannot describe a procedure that no longer exists.</p>
    </>}

    {tab === 'results' && <>
      <div className="cs-table-wrap"><table>
        <thead><tr><th>Result</th><th>Value</th><th>Split</th><th>Read from</th></tr></thead>
        <tbody>{data.results.map(row => <tr key={row.label}>
          <td>{row.label}</td>
          <td><strong>{number(row.value)}</strong>{row.unit ? <span> {row.unit}</span> : null}</td>
          <td>{row.split}</td>
          <td><code>{row.source.split('/').pop()} → {row.pointer}</code></td>
        </tr>)}</tbody>
      </table></div>
      <div className="cs-science-warning"><strong>Reading these together</strong>
        <p>The chronological rows are the stricter test: every scored year follows every calibration year. The stratified rows come from a split that places wet and dry years on both sides, and are not comparable with the chronological ones. Both are shown because the seasonal volume behaves differently under each.</p>
      </div>
      {data.limitations?.length > 0 && <><h3>Stated limitations</h3>
        <ul className="cs-package-limits">{data.limitations.map(limit => <li key={limit}>{limit}</li>)}</ul></>}
    </>}

    {tab === 'verification' && <>
      <div className={`cs-package-verdict ${rerun.reproduced ? 'cs-package-pass' : 'cs-package-fail'}`}>
        {rerun.reproduced ? <Check size={18} /> : <X size={18} />}
        <div>
          <strong>{rerun.reproduced
            ? 'Rebuilding the study reproduces the published document exactly.'
            : `Rebuilding the study produced ${rerun.substantiveDifferenceCount} differences.`}</strong>
          <span>{rerun.stage} rebuilt into a temporary directory and compared with <code>{rerun.compared.split('/').pop()}</code> field by field
            {rerun.checkedAt ? ` on ${rerun.checkedAt.slice(0, 10)}` : ''}. {rerun.provenanceDifferenceCount} provenance hash{rerun.provenanceDifferenceCount === 1 ? '' : 'es'} refreshed. Run it yourself with <code>{rerun.command}</code>.</span>
        </div>
      </div>
      {rerun.substantiveDifferences?.length > 0 && <div className="cs-table-wrap"><table>
        <thead><tr><th>Field</th><th>Published</th><th>Rebuilt</th></tr></thead>
        <tbody>{rerun.substantiveDifferences.map(row => <tr key={row.path}>
          <td><code>{row.path}</code></td><td>{String(row.published)}</td><td>{String(row.rebuilt)}</td>
        </tr>)}</tbody>
      </table></div>}
      <h3>Independent recomputation of the published scores</h3>
      <div className="cs-table-wrap"><table>
        <thead><tr><th>Check</th><th>Published</th><th>Recomputed</th><th>Difference</th><th>Within {verification.checks[0]?.tolerance}</th></tr></thead>
        <tbody>{verification.checks.map(check => <tr key={check.label}>
          <td>{check.label}</td><td>{number(check.published)}</td><td>{number(check.recomputed)}</td>
          <td>{check.absoluteDifference}</td>
          <td>{check.withinTolerance ? <><Check size={12} /> yes</> : <><X size={12} /> no</>}</td>
        </tr>)}</tbody>
      </table></div>
      <p className="cs-note">{verification.method}</p>
    </>}

    {tab === 'tests' && <>
      {data.tests.map(suite => <details key={suite.path} className="cs-package-suite">
        <summary><strong>{suite.path.split('/').pop()}</strong> · {suite.caseCount} checks · <code>{suite.command}</code></summary>
        <p>{suite.purpose}</p>
        <ul>{suite.cases.map(test => <li key={test.name}>
          <code>{test.name}</code>{test.asserts ? <span> — {test.asserts}</span> : null}
        </li>)}</ul>
      </details>)}
      <p className="cs-note">{counts.testCases} checks across {counts.testSuites} suites. Names and descriptions are read out of the test files when this package is built, so a deleted or renamed check cannot linger here.</p>
    </>}

    {tab === 'transferability' && <>
      <div className="cs-science-warning"><strong>What this study has and has not shown</strong><p>{transferability.statement}</p></div>
      <div className="cs-table-wrap"><table>
        <thead><tr><th>Domain</th><th>Period</th><th>Status</th><th>Evidence or requirement</th></tr></thead>
        <tbody>
          {transferability.tested.map(row => <tr key={row.domain}>
            <td><strong>{row.domain}</strong><br /><small>{row.extent}</small></td>
            <td>{row.period}</td>
            <td><span className="cs-status"><Check size={12} /> {row.status}</span></td>
            <td>{row.note}</td>
          </tr>)}
          {transferability.untested.map(row => <tr key={row.domain}>
            <td><strong>{row.domain}</strong></td>
            <td>{row.period}</td>
            <td><span className="cs-status"><CircleDashed size={12} /> {row.status}</span></td>
            <td>{row.requirement}</td>
          </tr>)}
        </tbody>
      </table></div>
      {transferability.gates?.length > 0 && <details><summary>Evidence gates recorded by the study protocols</summary>
        <ul className="cs-package-limits">{transferability.gates.map(gate => <li key={gate}>{gate}</li>)}</ul>
      </details>}
    </>}

    {tab === 'downloads' && (data.downloads ? <>
      <p className="cs-note">Flat CSV, one row per observation. Missing values are empty rather than <code>nan</code>, so a column of numbers imports as numbers. Column meanings and units are in <code>data_dictionary.csv</code>.</p>
      <div className="cs-table-wrap"><table>
        <thead><tr><th>Table</th><th>Rows</th><th>Size</th><th></th></tr></thead>
        <tbody>{data.downloads.tables.map(table => <tr key={table.file}>
          <td><code>{table.file}</code></td>
          <td>{table.rows.toLocaleString('en')}</td>
          <td>{kb(table.bytes)}</td>
          <td><a href={`${data.downloads.directory}${table.file}`} download>Download</a></td>
        </tr>)}</tbody>
      </table></div>
      <dl className="cs-package-convention">
        {Object.entries(data.downloads.convention).map(([key, value]) => <div key={key}>
          <dt>{key.replace(/([A-Z])/g, ' $1').toLowerCase()}</dt><dd>{value}</dd>
        </div>)}
      </dl>
      <pre>{R_SNIPPET}</pre>
      <div className="cs-download-links"><a href={`${data.downloads.directory}README.md`} download>Bundle README <Download size={14}/></a></div>
    </> : <p className="cs-note">The tidy tables have not been built yet. Run <code>npm run cases:tidy</code>.</p>)}

    <div className="cs-download-links">
      <a href={BASE + 'reproducibility-package.json'} download>The whole package · JSON <Download size={14} /></a>
      <a href={BASE + 'reproduction-check.json'} download>Rebuild comparison · JSON <Download size={14} /></a>
      <a href={BASE + 'chirchik.manifest.json'} download>Input hashes and QC policy · JSON <Download size={14} /></a>
    </div>
  </section>;
}
