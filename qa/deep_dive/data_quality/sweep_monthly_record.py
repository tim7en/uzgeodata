"""Full-coverage quality sweep of the published monthly record.

Run from repository root: python qa/deep_dive/data_quality/sweep_monthly_record.py

Reads the fourteen catchment matrices the portal serves (every level-12 basin, every
month 2003-2026) and tests each value against physical bounds, the other variables of
the same product, the other product measuring the same thing, and its own history.
Writes sweep.json beside this script. It changes nothing.

Every test here is a screen, not a verdict: a flagged value is one a reader should be
told about or a builder should look at, and the report counts how many there are.
"""
import gzip
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
ATLAS = ROOT / "PUBLISHED/data/atlas"
OUT = Path(__file__).with_name("sweep.json")

# Physical bounds for a monthly basin mean. Wide on purpose: a value outside is impossible,
# not merely unusual.
BOUNDS = {
    "pre_mm_s": (0, 1500), "aet_mm_s": (0, 400), "pet_mm_s": (0, 450), "cwd_mm_s": (0, 450),
    "soil_mm_s": (0, 1000), "swe_mm_s": (0, 20000), "rtc_mm_s": (0, 1500), "run_mm_s": (0, 1500),
    "tmn_dc_s": (-60, 40), "tmx_dc_s": (-50, 55), "tmp_dc_s": (-55, 50), "vpd_kp_s": (0, 8),
    "pds_ix_s": (-12, 12), "snw_pc_s": (0, 100),
}


def load():
    index = json.loads((ATLAS / "catchments/index.json").read_text(encoding="utf-8"))
    n, months = len(index["ids"]), index["months"]
    data = {}
    for name, entry in index["series"].items():
        raw = np.frombuffer(gzip.decompress((ROOT / "PUBLISHED" / entry["url"].lstrip("/")).read_bytes()), np.uint8)
        planes = raw.reshape(4, n * months).astype(np.uint32)
        coded = (planes[0] | planes[1] << 8 | planes[2] << 16 | planes[3] << 24).view(np.int32)
        values = np.cumsum(coded.reshape(n, months).astype(np.int64), axis=1)
        values = (values + 2**31) % 2**32 - 2**31
        out = values / index["scale"]
        out[values == index["null_sentinel"]] = np.nan
        data[name] = out
    return index, data


def label(index, slot):
    return f"{index['years'][0] + slot // 12}-{slot % 12 + 1:02}"


def coverage(index, data):
    report = {}
    for name, m in data.items():
        has = np.isfinite(m)
        per_month = has.mean(axis=0)
        filled = np.flatnonzero(per_month > 0)
        last = int(filled[-1]) if filled.size else None
        span = slice(0, last + 1) if last is not None else slice(0, 0)
        gaps = [label(index, s) for s in range(last + 1 if last is not None else 0) if per_month[s] < 0.99]
        prov = index["series"][name]["provenance"][0]
        report[name] = {
            "source_release": prov.get("source_release"),
            "declared_through": prov.get("extracted_through"),
            "last_month_with_values": label(index, last) if last is not None else None,
            "basins_with_value_in_last_month_pct": round(float(per_month[last]) * 100, 2) if last is not None else 0,
            "missing_pct_up_to_last_month": round(float((~has[:, span]).mean()) * 100, 3),
            "months_below_99pct_coverage": len(gaps),
            "first_such_months": gaps[:12],
            "basins_never_valued": int((~has.any(axis=1)).sum()),
            "declared_matches_data": prov.get("extracted_through") in (None, label(index, last)) if last is not None else None,
        }
    return report


def bounds(data):
    report = {}
    for name, (low, high) in BOUNDS.items():
        m = data[name]
        finite = np.isfinite(m)
        below, above = finite & (m < low), finite & (m > high)
        report[name] = {"bounds": [low, high], "values": int(finite.sum()),
                        "below": int(below.sum()), "above": int(above.sum()),
                        "min": float(np.nanmin(m)), "max": float(np.nanmax(m))}
    return report


def consistency(index, data):
    """Relations that must hold inside one product, and agreements expected across two."""
    out = {}
    tmn, tmx, tmp = data["tmn_dc_s"], data["tmx_dc_s"], data["tmp_dc_s"]
    both = np.isfinite(tmn) & np.isfinite(tmx)
    out["tmin_above_tmax"] = int((both & (tmn > tmx + 1e-6)).sum())
    mid = (tmn + tmx) / 2
    diff = tmp - mid
    ok = np.isfinite(diff)
    basin_bias = np.nanmean(np.where(ok, diff, np.nan), axis=1)
    out["era5_tmean_minus_terraclimate_midrange_c"] = {
        "pairs": int(ok.sum()), "mean": float(np.nanmean(diff)), "p05": float(np.nanpercentile(diff, 5)),
        "p95": float(np.nanpercentile(diff, 95)),
        "basins_mean_bias_beyond_3c": int((np.abs(basin_bias) > 3).sum()),
        "note": "ERA5-Land 2 m mean against the TerraClimate (tmin+tmax)/2 of the same basin-month: two products; "
                "a basin with a large steady offset shows a product or elevation-support difference, not an error."}
    aet, pet = data["aet_mm_s"], data["pet_mm_s"]
    out["aet_exceeds_pet_mm_gt_0_5"] = int((np.isfinite(aet) & np.isfinite(pet) & (aet > pet + 0.5)).sum())
    # Water-year totals: evapotranspiration against precipitation over the complete TerraClimate years.
    years = (2025 - index["years"][0] + 1)
    def annual(m):
        return m[:, :years * 12].reshape(m.shape[0], years, 12).sum(axis=2)
    ppt_a, aet_a = annual(data["pre_mm_s"]), annual(aet)
    ratio = aet_a.mean(axis=1) / np.maximum(ppt_a.mean(axis=1), 1e-6)
    out["aet_over_ppt_long_term"] = {"basins_ratio_above_1_05": int((ratio > 1.05).sum()),
                                     "max_ratio": float(np.nanmax(ratio)),
                                     "note": "TerraClimate's water balance cannot evaporate more than falls over 23 years "
                                             "unless water is added (irrigation, lakes); a ratio above 1 marks such basins."}
    # Two runoff products for one quantity.
    q_tc, q_era = annual(data["rtc_mm_s"]), data["run_mm_s"]
    era_years = np.isfinite(q_era[:, :years * 12]).reshape(q_era.shape[0], years, 12).all(axis=2)
    q_era_a = np.where(era_years, np.nan_to_num(q_era[:, :years * 12]).reshape(q_era.shape[0], years, 12).sum(axis=2), np.nan)
    tc_mean, era_mean = np.nanmean(q_tc, axis=1), np.nanmean(q_era_a, axis=1)
    valid = np.isfinite(tc_mean) & np.isfinite(era_mean) & (tc_mean + era_mean > 5)
    log_ratio = np.log10((era_mean[valid] + 1) / (tc_mean[valid] + 1))
    out["runoff_era5_vs_terraclimate_annual"] = {
        "basins": int(valid.sum()), "median_ratio": float(10 ** np.median(log_ratio)),
        "basins_differing_more_than_2x": int((np.abs(log_ratio) > np.log10(2)).sum()),
        "regional_mean_mm_per_year": {"terraclimate_q": float(np.nanmean(tc_mean)), "era5_land_ro": float(np.nanmean(era_mean))},
        "note": "Both are runoff generation in the basin, not river flow; they come from different land models."}
    era_over_ppt = era_mean / np.maximum(ppt_a.mean(axis=1), 1e-6)
    out["era5_runoff_exceeds_precipitation"] = {"basins_ratio_above_1": int((era_over_ppt > 1).sum()),
                                                "note": "ERA5-Land runoff against TerraClimate precipitation - different products; "
                                                        "above 1 is possible with glacier melt in ERA5-Land but worth showing."}
    snow, swe = data["snw_pc_s"], data["swe_mm_s"]
    winter = np.zeros(snow.shape[1], bool)
    for slot in range(snow.shape[1]):
        winter[slot] = (slot % 12) + 1 in (12, 1, 2)
    both = np.isfinite(snow) & np.isfinite(swe) & winter[None, :]
    out["snow_cover_vs_swe_winter"] = {
        "pairs": int(both.sum()),
        "no_cover_but_swe_over_50mm": int((both & (snow < 1) & (swe > 50)).sum()),
        "full_cover_but_swe_zero": int((both & (snow > 95) & (swe < 0.5)).sum())}
    return out


def history(index, data):
    """Stuck values, isolated spikes and regional step changes."""
    out = {}
    for name, m in data.items():
        # Stuck: 24 or more consecutive identical non-zero months in one basin.
        same = np.isfinite(m[:, 1:]) & (np.abs(np.diff(m, axis=1)) < 1e-9) & (np.abs(m[:, 1:]) > 1e-6)
        longest = np.zeros(m.shape[0], int)
        run = np.zeros(m.shape[0], int)
        for col in range(same.shape[1]):
            run = np.where(same[:, col], run + 1, 0)
            longest = np.maximum(longest, run)
        # Spikes: robust z-score against the same calendar month in the same basin.
        z_hits = 0
        worst = None
        for month in range(12):
            block = m[:, month::12]
            med = np.nanmedian(block, axis=1, keepdims=True)
            mad = np.nanmedian(np.abs(block - med), axis=1, keepdims=True)
            scale = np.maximum(1.4826 * mad, 0.05 * np.abs(med) + 1e-3)
            z = np.abs(block - med) / scale
            hits = np.isfinite(z) & (z > 10)
            z_hits += int(hits.sum())
            if hits.any():
                b, y = np.unravel_index(np.nanargmax(np.where(hits, z, -1)), z.shape)
                cand = (float(z[b, y]), str(index["ids"][b]), label(index, y * 12 + month), float(block[b, y]), float(med[b, 0]))
                if worst is None or cand[0] > worst[0]:
                    worst = cand
        # Regional annual mean and the largest year-on-year jump relative to its spread.
        years = m.shape[1] // 12
        annual = np.array([np.nanmean(m[:, y * 12:(y + 1) * 12]) if np.isfinite(m[:, y * 12:(y + 1) * 12]).any() else np.nan
                           for y in range(years)])
        steps = np.diff(annual)
        sd = np.nanstd(annual)
        k = int(np.nanargmax(np.abs(steps))) if np.isfinite(steps).any() else None
        out[name] = {
            "basins_with_24_month_constant_run": int((longest >= 24).sum()),
            "spikes_z_above_10": z_hits,
            "worst_spike": None if worst is None else {"z": round(worst[0], 1), "basin": worst[1], "month": worst[2],
                                                        "value": worst[3], "basin_median_same_month": worst[4]},
            "regional_annual_mean": [None if not np.isfinite(a) else round(float(a), 4) for a in annual],
            "largest_year_step": None if k is None else {"from": index["years"][0] + k, "to": index["years"][0] + k + 1,
                                                         "step": float(steps[k]), "in_sd": float(abs(steps[k]) / sd) if sd else None},
        }
    return out


def main():
    index, data = load()
    result = {"basins": len(index["ids"]), "months": index["months"], "years": index["years"],
              "coverage": coverage(index, data), "bounds": bounds(data),
              "consistency": consistency(index, data), "history": history(index, data)}
    OUT.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("coverage", "bounds", "consistency")}, indent=1))
    print(json.dumps({k: {x: v[x] for x in ("basins_with_24_month_constant_run", "spikes_z_above_10", "worst_spike", "largest_year_step")}
                      for k, v in result["history"].items()}, indent=1))


if __name__ == "__main__":
    main()
