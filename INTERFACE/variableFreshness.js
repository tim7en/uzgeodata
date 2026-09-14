export const LAYERS = { 1: 'Reference', 2: 'Observations', 3: 'Analytical products', 4: 'Models' };
const DAY = 86400000;

export function freshness(row, now = Date.now()) {
  if (row.status === 'missing') return { score: 0, state: 'missing', label: 'Missing', age: null };
  const date = Date.parse(row.last_updated);
  const age = Number.isFinite(date) && date <= now ? (now - date) / DAY : null;
  if (row.status === 'reference') return { score: null, state: 'reference', label: 'Fixed reference', age };
  if (row.status === 'archival') return { score: null, state: 'reference', label: 'Historical record', age };
  if (row.status === 'on_demand') return { score: null, state: 'reference', label: 'On demand', age: null };
  if (age === null || !(row.interval_days > 0)) return { score: null, state: 'unknown', label: 'Date / policy unknown', age };
  const score = Math.round(Math.max(0, Math.min(100, 100 * (1 - age / row.interval_days))));
  return { score, age, state: score >= 60 ? 'fresh' : score >= 25 ? 'aging' : 'overdue',
    label: score >= 60 ? 'Recently updated' : score >= 25 ? 'Aging' : 'Update due' };
}

export function coverageAge(row, now = Date.now()) {
  if (!row.coverage_to || !row.interval_days || row.status === 'reference' || row.status === 'archival') return null;
  const value = row.coverage_to;
  let end;
  if (/^\d{4}$/.test(value)) end = Date.UTC(Number(value), 12, 1);
  else if (/^\d{4}-\d{2}$/.test(value)) end = Date.UTC(Number(value.slice(0, 4)), Number(value.slice(5)), 1);
  else end = Date.parse(value) + DAY;
  if (!Number.isFinite(end) || now < end) return null;
  const days = Math.floor((now - end) / DAY);
  return { days, behind: days > row.interval_days, label: `${days} days since coverage ended` };
}

export function visibleRows(rows, { query = '', layer = 'all', status = 'all', collection = 'all' } = {}, now = Date.now()) {
  const needle = query.toLowerCase().trim();
  return rows.filter(row => (layer === 'all' || String(row.layer) === layer)
    && (collection === 'all' || row.collection === collection)
    && (!needle || [row.id, row.label, row.collection, row.source].join(' ').toLowerCase().includes(needle))
    && (status === 'all' || (status === 'attention'
      ? ['missing', 'unknown', 'overdue'].includes(freshness(row, now).state) || coverageAge(row, now)?.behind
      : freshness(row, now).state === status)));
}

export function latestJob(jobs, id) { return jobs?.find(job => job.group_id === id); }
