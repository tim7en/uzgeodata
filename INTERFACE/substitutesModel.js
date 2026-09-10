// The substitutes tab answers one question per row: does this exact basin, in
// this exact run, have a published substitute for this attribute? The joining,
// filtering, matching and unit rules live here rather than inside the component,
// because these are the rules that stop a pilot value from being read as a
// regional one, and a missing value from being read as a zero.

// BasinATLAS carries each attribute either for the sub-basin itself or for
// everything upstream of it. The distinction survives into the substitutes,
// so both the filter and the row label ask the same question of it.
export function isUpstream(support) {
  return ['u', 'p'].includes(support);
}

export function substituteRows(definitions, basinData, filter = '', kind = 'all') {
  const term = filter.trim().toLowerCase();
  return definitions.attributes.filter(a => {
    const family = definitions.families[a.family];
    return (kind === 'all' || (kind === 'basin_accumulation' ? isUpstream(a.support) : !isUpstream(a.support)))
      && `${a.column} ${a.label} ${a.category} ${family.source.name}`.toLowerCase().includes(term);
  }).map(a => ({ ...a, ...basinData.values[a.column], familyData: definitions.families[a.family] }));
}

// A pilot value belongs to the basin it was computed for. Another level-12 id,
// or a coarser parent unit that happens to contain this one, has no substitute
// until its own run exists.
export function basinIsPublished(index, basin) {
  return Number(basin.basin_level) === index.basin_level
    && index.basin_ids.includes(String(basin.hybas_id));
}

// Index, definitions and values must describe the same frozen run and the same
// basin. A stale cached file is a wrong answer, not a slow one.
export function payloadMatchesBasin(index, definitions, values, basin) {
  return definitions.run_id === index.run_id && values.run_id === index.run_id
    && String(values.hybas_id) === String(basin.hybas_id)
    && values.basin_level === Number(basin.basin_level);
}

// Only for reading a substitute against the stored original. A valid zero is a
// measurement and converts like any other; a missing substitute stays missing.
export function storedUnitsValue(family, value) {
  return value != null && family.units.convertible ? value * family.units.factor : null;
}
