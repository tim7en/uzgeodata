"""Figures for the daily Pskem model: hydrograph, monthly skill and seasonal shape.

The figure atlas predates the daily model, so the study showed skill scores with
nothing to look at. These three plots are the ones that let a reader check the
claims rather than take them: whether the hydrograph follows, whether the monthly
means sit on the line, and where in the year the model still misses.

Validation years are drawn apart from calibration years everywhere, because a fit
to years the model was trained on proves nothing.

    python PIPELINES/build_pskem_model_figures.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import hashlib
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
STUDY = ROOT / "PUBLISHED/data/case-studies"
SERIES = STUDY / "pskem-daily-model.csv"
SUMMARY = STUDY / "pskem-daily-model.json"
MANIFEST = STUDY / "pskem-daily-model-figures.manifest.json"
INK = "#12211f"
OBSERVED = "#1f4d5c"
SIMULATED = "#e07a3c"
CALIBRATION = "#7fa8b5"


def style(axis):
    axis.spines[["top", "right"]].set_visible(False)
    axis.tick_params(labelsize=8, colors=INK)
    for spine in axis.spines.values():
        spine.set_color("#c8d3d1")
    axis.grid(axis="y", color="#e4ebea", linewidth=.7)
    axis.set_axisbelow(True)


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    if not SERIES.exists():
        raise SystemExit(f"Missing {SERIES.relative_to(ROOT)}; run npm run casestudy:dailymodel first")

    with SERIES.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    dates = [row["date"] for row in rows]
    observed = np.array([float(row["observed_mm"]) for row in rows])
    simulated = np.array([float(row["simulated_mm"]) for row in rows])
    snow = np.array([float(row["snow_water_equivalent_mm"]) for row in rows])
    period = np.array([row["period"] for row in rows])
    written = []

    # 1. The hydrograph over the validation years, with the snowpack underneath.
    mask = period == "validation"
    index = np.array(dates, dtype='datetime64[D]')
    figure, (top, bottom) = plt.subplots(
        2, 1, figsize=(11, 6), height_ratios=[3, 1], sharex=True, dpi=140)
    top.plot(index, np.where(mask, observed, np.nan), color=OBSERVED, linewidth=1.1, label="Observed")
    top.plot(index, np.where(mask, simulated, np.nan), color=SIMULATED, linewidth=1.0, alpha=.9, label="Modelled")
    top.set_ylabel("Runoff, mm/day", fontsize=9, color=INK)
    validation = summary["skill"]["validation"]
    top.set_title(
        f"Pskem historical runoff, held-out years  ·  NSE {validation['nse']:+.2f}, "
        f"KGE {validation['kge']:+.2f}, bias {validation['pbias']:+.0f}%",
        fontsize=11, color=INK, loc="left")
    top.legend(frameon=False, fontsize=8.5)
    style(top)
    bottom.fill_between(index, np.where(mask, snow, np.nan), color=CALIBRATION, alpha=.55, linewidth=0)
    bottom.set_ylabel("Modelled SWE, mm", fontsize=9, color=INK)
    style(bottom)
    ticks = [index[i] for i in np.where(mask)[0] if dates[i].endswith("-01-01")]
    bottom.set_xticks(ticks)
    bottom.set_xticklabels([str(date)[:4] for date in ticks])
    bottom.set_xlim(index[mask][0], index[mask][-1])
    figure.tight_layout()
    path = STUDY / "pskem-daily-hydrograph.png"
    figure.savefig(path, facecolor="white")
    plt.close(figure)
    written.append(path)

    # 2. Monthly means against the 1:1 line, the unit the project publishes.
    monthly = defaultdict(lambda: {"o": [], "s": [], "period": None})
    for row, obs, sim in zip(rows, observed, simulated):
        if row["period"] not in {'calibration', 'validation'} or not (np.isfinite(obs) and np.isfinite(sim)):
            continue
        key = row["date"][:7]
        monthly[key]["o"].append(obs)
        monthly[key]["s"].append(sim)
        monthly[key]["period"] = row["period"]
    keys = sorted(k for k in monthly if len(monthly[k]['o']) >= 20)
    figure, axis = plt.subplots(figsize=(5.6, 5.6), dpi=140)
    for label, colour in (("calibration", CALIBRATION), ("validation", SIMULATED)):
        xs = [np.mean(monthly[k]["o"]) for k in keys if monthly[k]["period"] == label]
        ys = [np.mean(monthly[k]["s"]) for k in keys if monthly[k]["period"] == label]
        axis.scatter(xs, ys, s=26, color=colour, alpha=.85, linewidth=0,
                     label=f"{label} ({len(xs)} months)")
    limit = max(max(np.mean(monthly[k]['o']), np.mean(monthly[k]['s'])) for k in keys) * 1.05
    axis.plot([0, limit], [0, limit], color=INK, linewidth=.9, linestyle="--")
    axis.set_xlabel("Observed monthly mean, mm/day", fontsize=9, color=INK)
    axis.set_ylabel("Modelled monthly mean, mm/day", fontsize=9, color=INK)
    monthly_scores = summary["monthlySkill"]["validation"]
    axis.set_title(f"Monthly means  ·  held-out NSE {monthly_scores['nse']:+.2f}",
                   fontsize=11, color=INK, loc="left")
    axis.legend(frameon=False, fontsize=8.5)
    style(axis)
    figure.tight_layout()
    path = STUDY / "pskem-monthly-skill.png"
    figure.savefig(path, facecolor="white")
    plt.close(figure)
    written.append(path)

    # 3. Where in the year the model still misses, after elevation banding.
    by_month = defaultdict(lambda: {"o": [], "s": []})
    for key in keys:
        if monthly[key]["period"] != "validation":
            continue
        month = int(key[5:7])
        by_month[month]["o"].append(np.mean(monthly[key]["o"]))
        by_month[month]["s"].append(np.mean(monthly[key]["s"]))
    months = sorted(by_month)
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    width = .38
    positions = np.arange(len(months))
    figure, axis = plt.subplots(figsize=(9, 4.2), dpi=140)
    axis.bar(positions - width/2, [np.mean(by_month[m]["o"]) for m in months], width,
             color=OBSERVED, label="Observed")
    axis.bar(positions + width/2, [np.mean(by_month[m]["s"]) for m in months], width,
             color=SIMULATED, label="Modelled")
    axis.set_xticks(positions)
    axis.set_xticklabels([names[m-1] for m in months])
    axis.set_ylabel("Runoff, mm/day", fontsize=9, color=INK)
    axis.set_title("Seasonal shape in held-out years · observed and simulated runoff", fontsize=11, color=INK, loc="left")
    axis.legend(frameon=False, fontsize=8.5)
    style(axis)
    figure.tight_layout()
    path = STUDY / "pskem-seasonal-shape.png"
    figure.savefig(path, facecolor="white")
    plt.close(figure)
    written.append(path)

    payload = {
        "version": "1.0",
        "generatedAt": summary["generatedAt"],
        "inputs": [str(SERIES.relative_to(ROOT)).replace("\\", "/"),
                   str(SUMMARY.relative_to(ROOT)).replace("\\", "/")],
        "outputs": [str(path.relative_to(ROOT)).replace("\\", "/") for path in written],
        "inputHashes": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in [SERIES, SUMMARY]},
        "note": "Calibration and validation years are drawn apart in every figure.",
    }
    temporary = MANIFEST.with_suffix(MANIFEST.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, MANIFEST)
    for path in written:
        print(f"  {path.name}  {path.stat().st_size/1000:.0f} kB")


if __name__ == "__main__":
    main()
