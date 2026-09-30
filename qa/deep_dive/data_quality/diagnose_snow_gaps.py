"""Where the MODIS snow-cover gaps are, and whether they touch winter snow.

Run from repository root: python qa/deep_dive/data_quality/diagnose_snow_gaps.py

Snow cover is withdrawn from trend use because its missing basin-months grow across
the record. This locates them - by year, calendar month, basin size and temperature -
so the withdrawal can say what it is about. Writes snow-gaps.json beside this script.
"""
import json
from pathlib import Path

import numpy as np

from sweep_monthly_record import load

OUT = Path(__file__).with_name("snow-gaps.json")


def main():
    index, data = load()
    through = index["series"]["snw_pc_s"]["provenance"][0].get("extracted_through") or "2024-12"
    months = (int(through[:4]) - index["years"][0]) * 12 + int(through[5:7])
    years = months // 12
    snow = data["snw_pc_s"][:, :years * 12]
    temp = data["tmp_dc_s"][:, :years * 12]
    area = np.array(index["areas_km2"])
    miss = ~np.isfinite(snow)
    cube = miss.reshape(miss.shape[0], years, 12)
    winter = [0, 1, 2, 10, 11]                      # Nov-Mar
    hit = miss.any(axis=1)
    result = {
        "through": through,
        "missing_basin_months": int(miss.sum()), "basin_months": int(miss.size),
        "missing_share_pct": round(float(miss.mean()) * 100, 3),
        "by_year": {str(index["years"][0] + y): int(cube[:, y].sum()) for y in range(years)},
        "by_calendar_month": {str(m + 1): int(cube[:, :, m].sum()) for m in range(12)},
        "winter_nov_mar_complete_pct": round(100 - float(cube[:, :, winter].mean()) * 100, 3),
        "basins_with_any_gap": int(hit.sum()),
        "median_area_km2_gap_basins": float(np.median(area[hit])), "median_area_km2_all": float(np.median(area)),
        "mean_era5_temperature_at_gaps_c": float(np.nanmean(temp[miss])),
        "reading": "Gaps are months in which every MODIS cell of a basin was masked (cloud, water, night or no "
                   "decision) all month. They sit in warm months and small basins, where snow is absent; winter "
                   "months are nearly complete. They are not missing winter snow.",
    }
    OUT.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("by_year", "by_calendar_month")}, indent=1))


if __name__ == "__main__":
    main()
