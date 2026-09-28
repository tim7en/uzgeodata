// Reading the published SEAS5 forecast for one basin.

const SYSTEMS = { amu_darya: 'Amu Darya', syr_darya: 'Syr Darya' };

let cached = null;
export function readForecast(url) {
  if (!cached) {
    cached = fetch(url).then(response => {
      if (!response.ok || !(response.headers.get('content-type') || '').includes('json')) throw Error('No forecast');
      return response.json();
    });
    cached.catch(() => { cached = null; });
  }
  return cached;
}

/**
 * The forecast units a basin belongs to, finest first.
 *
 * A level-12 basin reads its level-7 basin, found by the first seven digits of its
 * Pfafstetter code, and its runoff-formation or lowland zone. The forecast is not
 * made per level-12 basin: at one degree dozens of them share a model cell.
 */
export function forecastUnits(forecast, basin) {
  const units = [];
  const pfaf = String(basin?.pfaf_id ?? '');
  if (pfaf.length >= 7 && forecast.units[`l7:${pfaf.slice(0, 7)}`]) {
    units.push({ key: `l7:${pfaf.slice(0, 7)}`, label: `Level-7 basin ${pfaf.slice(0, 7)}` });
  }
  const system = basin?.system_id;
  if (SYSTEMS[system]) {
    const headwater = Number(basin.in_headwater_formation) === 1 || basin.in_headwater_formation === true;
    const zone = `zone:${system}:${headwater ? 'headwater' : 'lowland'}`;
    if (forecast.units[zone]) {
      units.push({ key: zone, label: `${SYSTEMS[system]} ${headwater ? 'runoff-formation zone (headwaters)' : 'lowlands'}` });
    }
  }
  return units;
}
