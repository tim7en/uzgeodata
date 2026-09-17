#!/usr/bin/env python3
"""Charts for the SWOT lake/reservoir monitoring case study.

Two figures. The basin now has 378 monitored lakes, so — same lesson as
the discharge case study's earlier per-gauge atlases — anything that
enumerates every one of them by name or colour is unreadable. The map
shows all lakes as small uniform points and lets the named water bodies
stand out by size/colour; the time series figure is a small-multiples
grid of only the named ones with a usable record, each on its own
y-axis, because their areas span three orders of magnitude.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CS = ROOT / "PUBLISHED/data/case-studies"
RES_DIR = CS / "reservoirs"
OUT_STATUS = RES_DIR / "reservoir_status.png"
OUT_TIMESERIES = RES_DIR / "reservoir_timeseries.png"

COLOR = "#5d8f99"
NAMED_COLOR = "#c96b4b"


def plot_status(summary: pd.DataFrame, inventory: pd.DataFrame) -> None:
    named = summary[summary.name.notna() & (summary.n_overpasses > 0)].copy()
    figure, axes = plt.subplots(1, 2, figsize=(13, 5.5), dpi=160)
    figure.patch.set_facecolor("white")

    axis = axes[0]
    axis.scatter(inventory.lon, inventory.lat, s=6, color=COLOR, alpha=.35, label=f"All {len(inventory)} lakes ≥ 1 km²")
    axis.scatter(named.lon, named.lat, s=(named.pld_ref_area_km2.clip(upper=2000)) / 12,
                 color=NAMED_COLOR, alpha=.85, edgecolor="white", linewidth=.8, zorder=3, label=f"{len(named)} named water bodies")
    for row in named.itertuples():
        axis.annotate(row.name, (row.lon, row.lat), textcoords="offset points",
                      xytext=(6, 6), fontsize=8)
    axis.set(xlabel="Longitude", ylabel="Latitude", title="Every SWOT-tracked lake in the basin")
    axis.legend(fontsize=8, frameon=False, loc="lower left")
    axis.set_aspect(1.3)

    axis = axes[1]
    order = named.sort_values("pld_ref_area_km2")
    y = range(len(order))
    ref = order.known_area_km2.fillna(order.pld_ref_area_km2)
    axis.barh(y, ref, color="#d7e4e1", label="Reference area (full pool / PLD)")
    axis.barh(y, order.latest_area_km2, color=COLOR, label="Latest SWOT-observed area")
    axis.set(yticks=list(y), yticklabels=order.name, xlabel="Area (km²)",
             title="Named water bodies: latest vs. reference area")
    axis.legend(fontsize=8, frameon=False, loc="lower right")

    for axis in axes.flat:
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(alpha=.2)
    figure.suptitle("SWOT lake monitoring: Syr Darya & Amu Darya drainage basin", fontsize=13, x=.04, ha="left")
    figure.tight_layout()
    figure.savefig(OUT_STATUS, facecolor="white")
    plt.close(figure)


def plot_timeseries(monthly: pd.DataFrame, summary: pd.DataFrame) -> None:
    named = summary[summary.name.notna() & (summary.n_overpasses > 0)].sort_values("pld_ref_area_km2", ascending=False)
    cols = 4
    rows = (len(named) + cols - 1) // cols
    figure, axes = plt.subplots(rows, cols, figsize=(15, 3.4 * rows), dpi=160, squeeze=False)
    figure.patch.set_facecolor("white")

    for i, row in enumerate(named.itertuples()):
        axis = axes[i // cols][i % cols]
        data = monthly[monthly.pld_id == row.pld_id].dropna(subset=["area_total"])
        axis.plot(data["time"], data["area_total"], color=COLOR, linewidth=1.2, marker="o", markersize=2.5)
        axis.set_title(row.name, fontsize=10, loc="left")
        axis.set_ylabel("km²", fontsize=8)
        axis.tick_params(axis="x", labelrotation=30, labelsize=7)
        axis.tick_params(axis="y", labelsize=7)
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(alpha=.2)

    for j in range(len(named), rows * cols):
        axes[j // cols][j % cols].axis("off")

    figure.suptitle("Monthly maximum observed area, 2023–present (each panel its own scale)",
                     fontsize=13, x=.03, ha="left")
    figure.tight_layout()
    figure.savefig(OUT_TIMESERIES, facecolor="white")
    plt.close(figure)


def main() -> None:
    summary = pd.read_csv(RES_DIR / "reservoir_summary.csv", dtype={"pld_id": str})
    monthly = pd.read_csv(RES_DIR / "reservoir_timeseries_monthly.csv", dtype={"pld_id": str}, parse_dates=["time"])
    inventory = pd.read_csv(RES_DIR / "lake_inventory.csv", dtype={"pld_id": str})
    plot_status(summary, inventory)
    plot_timeseries(monthly, summary)
    print(f"Wrote {OUT_STATUS.name} and {OUT_TIMESERIES.name}")


if __name__ == "__main__":
    main()
