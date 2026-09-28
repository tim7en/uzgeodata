"""ECMWF SEAS5 seasonal forecasts for the Amu Darya and Syr Darya, read against TerraClimate.

python PIPELINES/seasonal_forecast_seas5.py download [--init 2026-09] [--hindcast-months all]
python PIPELINES/seasonal_forecast_seas5.py build [--init 2026-09]

What it answers. The atlas reports where a basin stands now; SEAS5 is what says
anything about the months ahead. Six months of 51-member monthly means from the
Copernicus Climate Data Store (seasonal-monthly-single-levels, ECMWF system 51),
with the 25-member hindcasts of 1993-2016 that every statement about skill rests on.

How it is read.
  * Both are reduced to the 7,445 level-12 basins by fractional overlap of the 1 degree
    grid, then area-averaged to the 438 level-7 basins, the four runoff-formation and
    lowland zones and the two river systems. Level 7 is the finest unit reported: at
    1 degree dozens of level-12 basins share one cell, and a forecast per level-12
    basin would be a claim of detail the model does not have.
  * Every forecast is placed in TerraClimate v1.1's terms by quantile mapping: a member's
    percentile within the pooled hindcast (24 years x 25 members) is mapped to the same
    percentile of TerraClimate over the same years. That removes SEAS5's systematic bias
    in these mountains without inventing a relationship the hindcast does not show.
  * Skill is measured against TerraClimate v1.1 over 1993-2016, leaving each year out of
    the thresholds it is judged by: correlation of the ensemble-mean anomaly, the ranked
    probability skill score against climatology, and the ROC area for a below-normal
    season. Where the forecast has no skill the output says so, and a reader is shown
    climatology rather than a forecast that only looks informative.

Nothing here is a runoff or discharge forecast: it is precipitation and temperature,
and in these basins next summer's river is made mostly of this winter's snow.
"""
from __future__ import annotations

import argparse
import calendar
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATASET = "seasonal-monthly-single-levels"
SYSTEM = "51"
CENTRE = "ecmwf"
HINDCAST = (1993, 2016)
LEADS = (1, 2, 3, 4, 5, 6)
# North, west, south, east with a cell of margin around the basins' extent.
AREA = [49, 57, 33, 80]
VARIABLES = {"total_precipitation": "ppt", "2m_temperature": "tmean"}
CACHE = ROOT / "WORKSPACE/derived/seas5"
TC_HISTORY = ROOT / "PUBLISHED/data/atlas/climate-continuation/terraclimate-v1.1-history"
FRAME = ROOT / "GEODATA/transboundary_basins_v2/hydroatlas-level12-full-basins.geojson"
OUT = ROOT / "PUBLISHED/data/atlas/seasonal-forecast"
# SPI -1: the share of a normal distribution below one standard deviation.
DRY_QUANTILE = 0.1587
# Useful skill: RPSS above zero and an anomaly correlation significant at 5% for n=24.
R_SIGNIFICANT = 0.404


# --------------------------------------------------------------------------- scoring

def midrank_percentile(values, sample):
    """Share of `sample` below each value, ties counted half, in (0, 1)."""
    sample = np.sort(np.asarray(sample, dtype=float))
    values = np.asarray(values, dtype=float)
    below = np.searchsorted(sample, values, side="left")
    equal = np.searchsorted(sample, values, side="right") - below
    return (below + 0.5 * equal + 0.5) / (len(sample) + 1)


def quantile_map(values, hindcast_pool, observed):
    """Each value's percentile in the hindcast, read off the observed distribution."""
    return np.quantile(np.asarray(observed, dtype=float), midrank_percentile(values, hindcast_pool))


def tercile_probabilities(members, pool):
    """Below, near and above normal, as shares of members against the pool's terciles."""
    low, high = np.quantile(pool, [1 / 3, 2 / 3])
    members = np.asarray(members, dtype=float)
    below = float(np.mean(members < low))
    above = float(np.mean(members > high))
    return below, 1 - below - above, above


def category(value, sample):
    low, high = np.quantile(sample, [1 / 3, 2 / 3])
    return 0 if value < low else 2 if value > high else 1


def rps(probabilities, observed_category):
    cumulative = np.cumsum(probabilities)
    outcome = np.cumsum([1.0 if i == observed_category else 0.0 for i in range(3)])
    return float(np.sum((cumulative - outcome) ** 2))


def roc_area(probabilities, events):
    """Mann-Whitney form: chance a year with the event got a higher probability than one without."""
    probabilities, events = np.asarray(probabilities), np.asarray(events, dtype=bool)
    positive, negative = probabilities[events], probabilities[~events]
    if not len(positive) or not len(negative):
        return None
    greater = (positive[:, None] > negative[None, :]).sum()
    ties = (positive[:, None] == negative[None, :]).sum()
    return float((greater + 0.5 * ties) / (len(positive) * len(negative)))


def skill(hindcast, observed):
    """Hindcast (years x members) against observations (years), each year left out of its thresholds.

    Returns the anomaly correlation, RPSS against climatology, ROC area for the lower
    tercile, the hindcast's mean bias against the observations, and whether the
    forecast is worth showing over climatology.
    """
    hindcast = np.asarray(hindcast, dtype=float)
    observed = np.asarray(observed, dtype=float)
    years = len(observed)
    ensemble_mean = hindcast.mean(axis=1)
    correlation = float(np.corrcoef(ensemble_mean, observed)[0, 1]) if np.std(ensemble_mean) > 0 and np.std(observed) > 0 else 0.0
    forecast_rps, climate_rps, below_probability, below_event = [], [], [], []
    for year in range(years):
        keep = np.arange(years) != year
        probabilities = tercile_probabilities(hindcast[year], hindcast[keep].ravel())
        observed_category = category(observed[year], observed[keep])
        forecast_rps.append(rps(probabilities, observed_category))
        climate_rps.append(rps((1 / 3, 1 / 3, 1 / 3), observed_category))
        below_probability.append(probabilities[0])
        below_event.append(observed_category == 0)
    rpss = 1 - float(np.mean(forecast_rps)) / float(np.mean(climate_rps))
    roc = roc_area(below_probability, below_event)
    return {"years": years, "correlation": round(correlation, 3), "rpss": round(rpss, 3),
            "roc_below": None if roc is None else round(roc, 3),
            "hindcast_mean": float(hindcast.mean()), "observed_mean": float(observed.mean()),
            "useful": bool(rpss > 0 and correlation >= R_SIGNIFICANT)}


def forecast_statement(members, hindcast, observed, extensive):
    """The forecast in TerraClimate terms, with its probabilities.

    `members` is the current ensemble, `hindcast` the years x members hindcast for the
    same window and `observed` TerraClimate over the same years.
    """
    pool = np.asarray(hindcast, dtype=float).ravel()
    mapped = quantile_map(members, pool, observed)
    below, near, above = tercile_probabilities(members, pool)
    dry = float(np.mean(midrank_percentile(members, pool) <= DRY_QUANTILE))
    normal = float(np.mean(observed))
    median = float(np.median(mapped))
    return {
        "median": round(median, 2), "p10": round(float(np.quantile(mapped, 0.1)), 2),
        "p90": round(float(np.quantile(mapped, 0.9)), 2), "normal": round(normal, 2),
        "anomaly": round(median - normal, 2),
        "anomaly_percent": round((median - normal) / normal * 100, 1) if extensive and normal > 1 else None,
        "probabilities": {"below": round(below, 3), "near": round(near, 3), "above": round(above, 3)},
        "dry_probability": round(dry, 3),
    }


# --------------------------------------------------------------------------- windows

def windows(init_month):
    """The periods a forecast from this month is read over, by lead (1 = the start month).

    The start month itself is mostly past when the forecast is read, so windows begin
    at lead 2. The accumulation season runs to lead 6: from an autumn start that is
    the winter whose snow becomes next summer's river.
    """
    def label(leads):
        months = [calendar.month_abbr[(init_month + lead - 2) % 12 + 1] for lead in leads]
        return f"{months[0]}–{months[-1]}"
    result = [{"id": "next3", "leads": [2, 3, 4], "label": label([2, 3, 4])},
              {"id": "season5", "leads": [2, 3, 4, 5, 6], "label": label([2, 3, 4, 5, 6])}]
    result += [{"id": f"lead{lead}", "leads": [lead], "label": label([lead])} for lead in (2, 3, 4, 5, 6)]
    return result


def target_month(year, init_month, lead):
    index = year * 12 + init_month - 1 + lead - 1
    return index // 12, index % 12 + 1


def aggregate(values, extensive):
    return values.sum(axis=-1) if extensive else values.mean(axis=-1)


# --------------------------------------------------------------------------- units

def units():
    """Level-12 basins, and the level-7 basins, zones and systems they are averaged into."""
    import geopandas as gpd
    frame = gpd.read_file(FRAME)[["HYBAS_ID", "PFAF_ID", "SUB_AREA", "system_id", "in_headwater_formation", "geometry"]]
    frame["basin_id"] = frame.HYBAS_ID.astype("int64").astype(str)
    frame = frame.sort_values("basin_id").reset_index(drop=True)
    # Level-7 units are keyed by their Pfafstetter code, the first seven digits of
    # every level-12 code inside them, so any basin finds its unit from its own id.
    groups = {}
    for index, row in frame.iterrows():
        area = float(row.SUB_AREA)
        members = [f"l7:{str(int(row.PFAF_ID))[:7]}",
                   f"zone:{row.system_id}:{'headwater' if row.in_headwater_formation else 'lowland'}",
                   f"system:{row.system_id}"]
        for unit in members:
            groups.setdefault(unit, []).append((index, area))
    return frame, groups


def unit_matrix(groups, n_basins):
    """A units x basins matrix of area weights summing to one per unit."""
    names = sorted(groups)
    matrix = np.zeros((len(names), n_basins))
    for row, name in enumerate(names):
        indices, areas = zip(*groups[name])
        matrix[row, list(indices)] = np.asarray(areas) / sum(areas)
    return names, matrix


# --------------------------------------------------------------------------- data

def cds_client():
    """A CDS client from CDSAPI_URL/CDSAPI_KEY, the project's .env (url, key), or ~/.cdsapirc."""
    import os
    import cdsapi
    from dotenv import dotenv_values
    local = dotenv_values(ROOT / ".env")
    url = os.environ.get("CDSAPI_URL") or local.get("CDSAPI_URL") or local.get("url")
    key = os.environ.get("CDSAPI_KEY") or local.get("CDSAPI_KEY") or local.get("key")
    if url and key and "cds.climate.copernicus.eu" in url:
        return cdsapi.Client(url=url, key=key, quiet=True)
    return cdsapi.Client(quiet=True)


def download(kind, init_month, years, client=None):
    """One CDS request: every year and lead of one start month. Cached by content."""
    import cdsapi
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{kind}-m{init_month:02d}-{years[0]}-{years[-1]}.nc"
    if path.exists() and path.stat().st_size > 0:
        return path
    request = {
        "originating_centre": CENTRE, "system": SYSTEM,
        "variable": sorted(VARIABLES), "product_type": ["monthly_mean"],
        "year": [str(year) for year in years], "month": [f"{init_month:02d}"],
        "leadtime_month": [str(lead) for lead in LEADS],
        "data_format": "netcdf", "area": AREA,
    }
    import time
    import requests
    # The CDS limits how many requests one user may have queued per dataset and
    # rejects the rest; that is a reason to wait, not to fail the monthly run.
    for attempt in range(8):
        try:
            (client or cds_client()).retrieve(DATASET, request).download(str(path))
            break
        except requests.HTTPError as error:
            if "temporarily limited" not in str(error) or attempt == 7:
                raise
            time.sleep(120)
    return path


def read(path):
    """Values as {variable: array[year, member, lead, lat, lon]} in mm/month and deg C."""
    import xarray as xr
    dataset = xr.open_dataset(path)
    names = {"forecast_reference_time": "time", "forecastMonth": "lead", "number": "member",
             "latitude": "lat", "longitude": "lon"}
    dataset = dataset.rename({k: v for k, v in names.items() if k in dataset.dims or k in dataset.coords})
    times = [datetime.utcfromtimestamp(t.astype("datetime64[s]").astype(int)) for t in dataset["time"].values]
    out = {"years": [t.year for t in times], "init_month": times[0].month,
           "lat": dataset["lat"].values, "lon": dataset["lon"].values}
    for source, name in (("tprate", "ppt"), ("t2m", "tmean")):
        values = dataset[source].transpose("time", "member", "lead", "lat", "lon").values.astype(float)
        if name == "ppt":
            # A mean rate in metres per second, turned into the month's total in millimetres.
            for y, year in enumerate(out["years"]):
                for l, lead in enumerate(dataset["lead"].values):
                    target = target_month(year, out["init_month"], int(lead))
                    values[y, :, l] *= calendar.monthrange(*target)[1] * 86400 * 1000
        else:
            values -= 273.15
        out[name] = values
    return out


def grid_to_basins(field, lat, lon, frame):
    """Reduce [..., lat, lon] to [..., basins] by fractional overlap of the 1 degree cells."""
    from rasterio.transform import from_origin
    from PIPELINES.extract_regional_climate_grids import grid_weights
    step = float(abs(lat[1] - lat[0]))
    north, west = float(lat.max()) + step / 2, float(lon.min()) - step / 2
    ordered = field if lat[0] > lat[-1] else field[..., ::-1, :]
    transform = from_origin(west, north, step, step)
    basin_index, flat_cell, weight = grid_weights(frame, transform, len(lon), len(lat))
    flat = ordered.reshape(*ordered.shape[:-2], -1)
    sampled = flat[..., flat_cell] * weight
    # Weights sum to one within each basin, so a basin's value is the sum of its
    # cells' weighted values: a segment sum, vectorised over the leading axes.
    order = np.argsort(basin_index, kind="stable")
    bounds = np.searchsorted(basin_index[order], np.arange(len(frame) + 1))
    cumulative = np.concatenate([np.zeros((*sampled.shape[:-1], 1)), np.cumsum(sampled[..., order], axis=-1)], axis=-1)
    return cumulative[..., bounds[1:]] - cumulative[..., bounds[:-1]]


def terraclimate(frame, first, last):
    """TerraClimate v1.1 monthly ppt and tmean (midpoint of the extremes) per basin, [year, month, basin]."""
    import duckdb
    years = list(range(first, last + 1))
    files = [str(TC_HISTORY / f"year={year}.parquet") for year in years if (TC_HISTORY / f"year={year}.parquet").exists()]
    if len(files) != len(years):
        raise FileNotFoundError(f"TerraClimate v1.1 history must cover {first}-{last}")
    position = {basin: i for i, basin in enumerate(frame.basin_id)}
    result = {name: np.full((len(years), 12, len(frame)), np.nan) for name in ("ppt", "tmax", "tmin")}
    data = duckdb.sql(f"SELECT basin_id, year, month, variable, value FROM read_parquet({files}) "
                      "WHERE variable IN ('ppt','tmax','tmin')").fetchnumpy()
    for basin, year, month, variable, value in zip(data["basin_id"], data["year"], data["month"],
                                                   data["variable"], data["value"]):
        result[variable][year - first, month - 1, position[basin]] = value
    return {"ppt": result["ppt"], "tmean": (result["tmax"] + result["tmin"]) / 2, "years": years}


# --------------------------------------------------------------------------- build

EXTENSIVE = {"ppt": True, "tmean": False}


class Context:
    """Basins, units and the TerraClimate record every build reads, loaded once."""

    def __init__(self):
        self.frame, self.groups = units()
        self.names, self.weights = unit_matrix(self.groups, len(self.frame))
        # One year past the hindcast, for windows that run into the next calendar year.
        self.observed = terraclimate(self.frame, HINDCAST[0], HINDCAST[1] + 1)

    def to_units(self, field, lat, lon):
        return grid_to_basins(field, lat, lon, self.frame) @ self.weights.T

    def observed_window(self, name, init_month, window):
        """TerraClimate over one window for every hindcast year, [year, unit]."""
        rows = []
        for year in range(HINDCAST[0], HINDCAST[1] + 1):
            months = [target_month(year, init_month, lead) for lead in window["leads"]]
            rows.append(aggregate(np.stack([self.weights @ self.observed[name][ty - self.observed["years"][0], tm - 1]
                                            for ty, tm in months], axis=-1), EXTENSIVE[name]))
        return np.asarray(rows)


def hindcast_path(init_month):
    return CACHE / f"hindcast-m{init_month:02d}-{HINDCAST[0]}-{HINDCAST[1]}.nc"


def hindcast_units(context, init_month):
    """{variable: [year, member, lead, unit]} for one start month's hindcast."""
    hind = read(hindcast_path(init_month))
    if hind["years"] != list(range(HINDCAST[0], HINDCAST[1] + 1)):
        raise ValueError(f"Hindcast for month {init_month} covers {hind['years'][0]}-{hind['years'][-1]}")
    return {name: context.to_units(hind[name], hind["lat"], hind["lon"]) for name in EXTENSIVE}


def window_values(units_by_lead, window, extensive):
    """Aggregate the leads of one window: [..., lead, unit] -> [..., unit]."""
    leads = [lead - 1 for lead in window["leads"]]
    return aggregate(np.moveaxis(units_by_lead[..., leads, :], -2, -1), extensive)


def build(init, context=None):
    """The current forecast for every unit, with the skill of the same start month and window."""
    context = context or Context()
    init_year, init_month = (int(part) for part in init.split("-"))
    hind = hindcast_units(context, init_month)
    live = read(CACHE / f"forecast-m{init_month:02d}-{init_year}-{init_year}.nc")
    year = live["years"].index(init_year)
    output = {"init": init, "system": f"ECMWF SEAS5 (system {SYSTEM})",
              "generated_at": datetime.now(timezone.utc).isoformat(),
              "hindcast_years": list(HINDCAST), "units": {}, "windows": windows(init_month)}
    for name, extensive in EXTENSIVE.items():
        current_by_lead = context.to_units(live[name][year], live["lat"], live["lon"])  # member, lead, unit
        output["members"] = int(current_by_lead.shape[0])
        for window in output["windows"]:
            hindcast = window_values(hind[name], window, extensive)      # year, member, unit
            current = window_values(current_by_lead, window, extensive)  # member, unit
            observed = context.observed_window(name, init_month, window)  # year, unit
            for u, unit in enumerate(context.names):
                entry = output["units"].setdefault(unit, {"area_km2": round(sum(a for _, a in context.groups[unit]), 1)})
                entry.setdefault(name, {})[window["id"]] = {
                    "forecast": forecast_statement(current[:, u], hindcast[:, :, u], observed[:, u], extensive),
                    "skill": skill(hindcast[:, :, u], observed[:, u]),
                }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"forecast-{init}.json").write_text(json.dumps(output, separators=(",", ":")) + "\n")
    (OUT / "latest.json").write_text(json.dumps(compact(output), separators=(",", ":")) + "\n")
    return {"init": init, "units": len(output["units"]), "members": output["members"]}


READ_WINDOWS = ("next3", "season5")


def compact(output):
    """What a basin panel reads: the two windows it shows, without the working means.

    The full file keeps every lead; this is the one a phone downloads.
    """
    keep = {"years", "correlation", "rpss", "roc_below", "useful"}
    units = {unit: {"area_km2": entry["area_km2"], **{
        name: {window: {"forecast": entry[name][window]["forecast"],
                        "skill": {k: v for k, v in entry[name][window]["skill"].items() if k in keep}}
               for window in READ_WINDOWS} for name in EXTENSIVE}} for unit, entry in output["units"].items()}
    return {**output, "units": units, "windows": [w for w in output["windows"] if w["id"] in READ_WINDOWS]}


def skill_table(context=None):
    """SEAS5 against TerraClimate for every start month the cache holds a hindcast for.

    Per unit, start month and window: correlation, RPSS, ROC area and whether the
    forecast beats climatology. Per zone and system, the hindcast's bias against
    TerraClimate for each calendar month at each lead: how much wetter or warmer the
    raw model is than the record it is corrected to.
    """
    context = context or Context()
    months = [m for m in range(1, 13) if hindcast_path(m).exists()]
    if not months:
        raise FileNotFoundError("No hindcasts in the cache; run the download first")
    table = {"generated_at": datetime.now(timezone.utc).isoformat(), "system": f"ECMWF SEAS5 (system {SYSTEM})",
             "reference": "TerraClimate v1.1, reduced to the same basins", "hindcast_years": list(HINDCAST),
             "start_months": months, "skill": {}, "bias": {}}
    regional = [i for i, unit in enumerate(context.names) if not unit.startswith("l7:")]
    for init_month in months:
        hind = hindcast_units(context, init_month)
        for name, extensive in EXTENSIVE.items():
            for window in windows(init_month):
                hindcast = window_values(hind[name], window, extensive)
                observed = context.observed_window(name, init_month, window)
                useful = total = 0
                for u, unit in enumerate(context.names):
                    # Level-7 basins are summarised as the share where the forecast
                    # beats climatology; the current month's per-basin scores travel
                    # with the forecast itself. Zones and systems keep every score.
                    if unit.startswith("l7:"):
                        if window["id"] in READ_WINDOWS:
                            total += 1
                            useful += skill(hindcast[:, :, u], observed[:, u])["useful"]
                        continue
                    cell = table["skill"].setdefault(unit, {}).setdefault(name, {}).setdefault(str(init_month), {})
                    cell[window["id"]] = skill(hindcast[:, :, u], observed[:, u])
                if total:
                    table.setdefault("level7_useful_share", {}).setdefault(name, {}) \
                        .setdefault(str(init_month), {})[window["id"]] = round(useful / total, 3)
            for lead in LEADS:
                single = {"id": f"lead{lead}", "leads": [lead]}
                hindcast = window_values(hind[name], single, extensive)
                observed = context.observed_window(name, init_month, single)
                target = (init_month + lead - 2) % 12 + 1
                for u in regional:
                    model, record = float(hindcast[:, :, u].mean()), float(observed[:, u].mean())
                    entry = {"model": round(model, 2), "terraclimate": round(record, 2)}
                    if extensive:
                        entry["ratio"] = round(model / record, 3) if record > 0 else None
                    else:
                        entry["difference"] = round(model - record, 2)
                    table["bias"].setdefault(context.names[u], {}).setdefault(name, {}) \
                        .setdefault(str(lead), {})[str(target)] = entry
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "skill.json").write_text(json.dumps(table, separators=(",", ":")) + "\n")
    return {"start_months": months, "units": len(context.names)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("download", "build", "skill"))
    parser.add_argument("--init", default=None, help="Start month YYYY-MM; defaults to the current month's")
    parser.add_argument("--all-hindcasts", action="store_true",
                        help="Download the hindcasts of all twelve start months, for the skill comparison")
    arguments = parser.parse_args()
    now = datetime.now(timezone.utc)
    init = arguments.init or f"{now.year:04d}-{now.month:02d}"
    year, month = (int(part) for part in init.split("-"))
    if arguments.command == "download":
        hindcast_years = list(range(HINDCAST[0], HINDCAST[1] + 1))
        for start in (range(1, 13) if arguments.all_hindcasts else [month]):
            print(download("hindcast", start, hindcast_years), flush=True)
        print(download("forecast", month, [year]), flush=True)
    elif arguments.command == "build":
        print(json.dumps(build(init), indent=2), flush=True)
    else:
        print(json.dumps(skill_table(), indent=2), flush=True)


if __name__ == "__main__":
    main()
