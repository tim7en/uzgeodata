// The substitutes tab answers one question per row: does this exact basin have an
// independent estimate for this attribute, and on what evidence? The joining,
// filtering, matching and unit rules live here rather than inside the component,
// because these are the rules that stop a missing value being read as a zero, an
// estimate being read as a reproduction, and one basin's value being read as
// another's.
//
// Values arrive positionally: the catalogue names the 281 attributes once, and each
// basin file carries arrays aligned to that order. Repeating the names in every one
// of 7,445 files would cost gigabytes to say the same thing 7,445 times, so the
// alignment is load-bearing and is checked rather than assumed.

// BasinATLAS carries each attribute either for the sub-basin itself or for
// everything upstream of it. The distinction survives into the substitutes, so both
// the filter and the row label ask the same question of it.
export function isUpstream(support) {
  return ['u', 'p'].includes(support);
}

// Every level-12 basin in the two systems has a file. A coarser parent unit does
// not: it is a derived view of the basins below it, and an attribute averaged over
// children is a different measurement from one computed on the parent.
export function basinIsPublished(index, basin) {
  return Number(basin.basin_level) === 12 && Boolean(index.by_basin?.[String(basin.hybas_id)]);
}

// A stale cached file is a wrong answer, not a slow one: positional arrays joined
// against the wrong catalogue would put every value under the wrong name.
export function payloadMatchesBasin(catalogue, values, basin) {
  return String(values.basin_id) === String(basin.hybas_id)
    && Number(values.basin_level) === Number(basin.basin_level)
    && values.original?.length === catalogue.attributes.length
    && values.substitute?.length === catalogue.attributes.length;
}

// What the pair of numbers is allowed to be read as. Units that differ are not
// comparable by subtraction, and a difference computed across them would be a
// number with no meaning that looks exactly like one with meaning.
//
// Whether they differ is a reviewed judgement, not a string comparison: the family
// records whether its estimate can be expressed in the units the atlas stored and
// by what factor. "percent snow-covered days" and "percent cover" are both
// percentages and are still not the same quantity, which is why the decision is
// carried in the data rather than inferred from the label.
export function comparable(row) {
  return row.family?.units?.convertible === true && Number.isFinite(row.family.units.factor);
}

// The estimate expressed in the units the published value is stored in. A valid
// zero converts like any other measurement; a missing estimate stays missing.
export function inStoredUnits(row) {
  if (row.value == null || !comparable(row)) return null;
  return row.value * row.family.units.factor;
}

export function difference(row) {
  const converted = inStoredUnits(row);
  if (converted == null || row.original == null) return null;
  return converted - row.original;
}

// How much of the record stands behind a value. A January normal over twenty years
// and one over six are different measurements, and the second has to say so.
export function support(row) {
  const { valid, expected } = row;
  if (valid == null || !expected) return null;
  return { valid, expected, fraction: valid / expected, whole: valid === expected };
}

// The state a row is in, which is what the table colours. Kept here so the colour
// and the words can never disagree: both read this.
export function rowState(row) {
  if (row.value != null) return 'estimated';
  if (row.original != null) return 'original_only';
  return 'empty';
}

export function substituteRows(catalogue, values, filter = '', kind = 'all') {
  const term = filter.trim().toLowerCase();
  const rows = [];
  catalogue.attributes.forEach((column, index) => {
    const meta = catalogue.meta[column];
    if (!meta) return;
    if (kind !== 'all') {
      const upstream = isUpstream(meta.support);
      if (kind === 'basin_accumulation' ? !upstream : upstream) return;
    }
    const family = meta.family ? catalogue.families?.[meta.family] : null;
    const haystack = `${column} ${meta.label} ${meta.category} ${meta.original?.dataset || ''} `
      + `${meta.substitute?.source_release || ''} ${family?.source?.name || ''}`;
    if (term && !haystack.toLowerCase().includes(term)) return;
    const row = {
      column, meta, family,
      label: meta.label,
      category: meta.category,
      support: meta.support,
      original: values.original[index],
      value: values.substitute[index],
      valid: values.substitute_valid?.[index] ?? null,
      expected: values.substitute_expected?.[index] ?? null,
    };
    row.state = rowState(row);
    rows.push(row);
  });
  return rows;
}

// A count of what the reader is looking at, so the table can say it before they
// scroll. "132 of 281" is the honest headline for a basin, not "281 attributes".
export function rowTotals(rows) {
  return {
    rows: rows.length,
    estimated: rows.filter(row => row.state === 'estimated').length,
    originalOnly: rows.filter(row => row.state === 'original_only').length,
    empty: rows.filter(row => row.state === 'empty').length,
  };
}

// The categories present, for the filter chips, in the order the catalogue lists
// them rather than alphabetically: the atlas's own thematic order.
export function categoriesOf(catalogue) {
  const seen = [];
  for (const column of catalogue.attributes) {
    const category = catalogue.meta[column]?.category;
    if (category && !seen.includes(category)) seen.push(category);
  }
  return seen;
}

// Resolution in one line, native first, because that is what limits the value.
export function resolutionLabel(family) {
  if (!family?.resolution) return null;
  const { native_m: native, native_arcsec: arcsec, processing_arcsec: grid } = family.resolution;
  const source = native ? `${formatScale(native)} native` : arcsec ? `${arcsec}″ native` : null;
  return [source, grid ? `${grid}″ processing grid` : null].filter(Boolean).join(' · ') || null;
}

function formatScale(metres) {
  return metres >= 1000 ? `${(metres / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })} km`
    : `${Math.round(metres)} m`;
}

// The period a substitute covers, as a reader would say it. A climatology over
// 2003-2022 is not "2003-01-01 to 2023-01-01", which reads as a 2023 observation.
export function periodLabel(meta) {
  const period = meta.substitute?.period;
  if (!Array.isArray(period) || !period[0] || !period[1]) return null;
  const start = Number(String(period[0]).slice(0, 4));
  const end = Number(String(period[1]).slice(0, 4)) - 1;
  return start === end ? `${start}` : `${start}–${end}`;
}
