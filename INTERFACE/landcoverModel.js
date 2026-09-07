export function annual(record, year) {
  return record?.years?.[String(year)] || null;
}

export function totalArea(record, year) {
  const values = annual(record, year);
  return values ? Object.values(values).reduce((sum, value) => sum + Number(value || 0), 0) : null;
}

export function classArea(record, year, code) {
  const values = annual(record, year);
  return values ? Number(values[String(code)] || 0) : null;
}

export function classShare(record, year, code) {
  const total = totalArea(record, year);
  const area = classArea(record, year, code);
  return total && area !== null ? area / total * 100 : null;
}

export function shareChange(record, year, code, years) {
  const position = years.indexOf(Number(year));
  if (position < 1) return null;
  const current = classShare(record, year, code);
  const previous = classShare(record, years[position - 1], code);
  return current === null || previous === null ? null : current - previous;
}

export function dominantClass(record, year) {
  const values = annual(record, year);
  if (!values) return null;
  const winner = Object.entries(values).reduce(
    (best, [code, value]) => Number(value) > best.value ? { code: Number(code), value: Number(value) } : best,
    { code: null, value: -Infinity },
  );
  return winner.code;
}

export function metricValue(record, year, code, mode, years) {
  if (mode === 'area') return classArea(record, year, code);
  if (mode === 'change') return shareChange(record, year, code, years);
  if (mode === 'dominant') return dominantClass(record, year);
  return classShare(record, year, code);
}

export function distribution(records, year, code, mode, years, bins = 6) {
  const values = records.map(record => metricValue(record, year, code, mode, years))
    .filter(value => value !== null && Number.isFinite(value));
  if (!values.length || mode === 'dominant') return { values, bins: [], max: 0 };
  const maxAbs = mode === 'change'
    ? Math.max(...values.map(Math.abs), 0.01)
    : Math.max(...values, 0.01);
  const low = mode === 'change' ? -maxAbs : 0;
  const high = maxAbs;
  const width = (high - low) / bins;
  const counts = Array.from({ length: bins }, () => 0);
  values.forEach(value => {
    const index = Math.min(bins - 1, Math.max(0, Math.floor((value - low) / width)));
    counts[index] += 1;
  });
  return {
    values,
    bins: counts.map((count, index) => ({
      from: low + index * width,
      to: low + (index + 1) * width,
      count,
    })),
    max: Math.max(...counts),
  };
}

export function selectedTimeline(record, years, code) {
  return years.map(year => ({
    year,
    area: classArea(record, year, code),
    share: classShare(record, year, code),
  }));
}

