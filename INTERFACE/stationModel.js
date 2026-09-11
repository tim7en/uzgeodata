// Turning one station's published record into the two shapes a reader might want.
//
// CSV is built from the same file the JSON download serves, rather than published
// separately, so the two cannot drift into describing different numbers. What the
// conversion has to get right is the difference between a value that is absent and
// a value that is zero: a blank cell and a 0 mean opposite things in a temperature
// record, and a converter that writes 0 for "not recorded" would quietly invent
// twenty degrees of winter.

const QUOTE = /[",\n\r]/;

export function csvCell(value) {
  if (value === null || value === undefined) return '';
  const text = String(value);
  return QUOTE.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

/** One station's rows as CSV, with the header the file itself declares. */
export function toCsv(record) {
  if (!record || !Array.isArray(record.columns) || !Array.isArray(record.rows)) return '';
  const lines = [record.columns.map(csvCell).join(',')];
  for (const row of record.rows) lines.push(row.map(csvCell).join(','));
  return `${lines.join('\n')}\n`;
}

/** A filename that says which station and which archive, not just "download". */
export function downloadName(record, extension) {
  const name = String(record?.name || 'station').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'station';
  const archive = record?.archive ? `-${record.archive}` : '';
  return `${name}${archive}-monthly.${extension}`;
}

/** What the record covers, for a reader deciding whether to take it. */
export function recordSummary(record) {
  if (!record || !Array.isArray(record.rows) || !record.rows.length) return null;
  const years = record.rows.map(row => row[1]).filter(Number.isFinite);
  const variables = [...new Set(record.rows.map(row => row[0]))].sort();
  const values = record.rows.filter(row => row[3] !== null && row[3] !== undefined).length;
  return {
    rows: record.rows.length,
    values,
    missing: record.rows.length - values,
    firstYear: years.length ? Math.min(...years) : null,
    lastYear: years.length ? Math.max(...years) : null,
    variables,
  };
}
