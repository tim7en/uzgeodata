"""Build held-out dry-spell error tables and basin-context maps.

The analysis is deliberately limited to validation predictions. It joins those
predictions to the corrected antecedent labels, reports errors by gauge, season,
and dry-spell state, and draws a BasinATLAS context map without inventing
coordinates for gauges whose spatial crosswalk is not verified.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "PUBLISHED/data/case-studies"
HYDRO = ROOT / "PUBLISHED/data/hydroclimate"
PREDICTIONS = STUDY / "gauge_quantile_predictions.csv"
FEATURES = STUDY / "antecedent_discharge_features.csv"
BASIN_LOOKUP = STUDY / "gauge_basin_lookup.csv"
BASINS = HYDRO / "basins-level10.geojson"
STATIONS = ROOT / "PUBLISHED/data/research/ca-discharge-stations.geojson"
CATCHMENT = STUDY / "pskem-candidate-catchment.geojson"
REACH_AUDIT = STUDY / "gauge-reach-audit.json"
OUT_CSV = STUDY / "dry_spell_error_analysis.csv"
OUT_MONTHLY = STUDY / "dry_spell_monthly_error.csv"
OUT_REPORT = STUDY / "dry_spell_error_report.md"
OUT_ERROR_FIGURE = STUDY / "dry_spell_error_atlas.png"
OUT_MAP = STUDY / "dry_spell_basin_context_map.png"
OUT_ERROR_MAP = STUDY / "dry_spell_gauge_error_map.png"
OUT_NETWORK_MAP = STUDY / "gauge_network_inventory_map.png"
OUT_MANIFEST = STUDY / "dry_spell_error_analysis.manifest.json"


def load_joined() -> pd.DataFrame:
    predictions = pd.read_csv(PREDICTIONS, dtype={'gauge_code': str})
    features = pd.read_csv(FEATURES, dtype={'gauge_code': str}, usecols=[
        "gauge_code", "date", "dry_spell", "dry_spell_severity",
        "dry_spell_discharge", "stress_accumulation_index", "discharge_q25",
    ])
    # generate_gauge_predictions.py passes through the full input feature matrix
    # (predictions was trained on antecedent_discharge_features.csv, so it
    # already carries these same label columns); drop them here so the merge
    # doesn't silently suffix both copies as dry_spell_x/dry_spell_y.
    predictions = predictions.drop(columns=[c for c in features.columns
                                             if c in predictions.columns and c not in ("gauge_code", "date")])
    joined = predictions.merge(features, on=["gauge_code", "date"], how="left", validate="one_to_one")
    if joined[["dry_spell", "dry_spell_severity"]].isna().any().any():
        raise ValueError("Validation predictions could not be matched to dry-spell labels")

    # CA-discharge spans Central Asia, not just the Aral Sea drainage: Harirud
    # and Murghab flow toward Turkmenistan/Iran, and Balkh/Shirintagab/Chu/Talas
    # are separate endorheic basins. Reporting them under a "Syr Darya & Amu
    # Darya" study overstates basin coverage, so they are dropped here rather
    # than left in the headline gauge count.
    basins = pd.read_csv(BASIN_LOOKUP, dtype={'gauge_code': str})[["gauge_code", "BASIN", "COUNTRY", "aral_drainage"]]
    before = joined.gauge_code.nunique()
    joined = joined.merge(basins, on="gauge_code", how="left", validate="many_to_one")
    if joined["aral_drainage"].isna().any():
        missing = sorted(joined.loc[joined["aral_drainage"].isna(), "gauge_code"].unique())
        raise ValueError(f"No basin classification for gauges: {missing}")
    joined = joined[joined["aral_drainage"]].drop(columns=["aral_drainage"]).reset_index(drop=True)
    print(f"Basin scope: kept {joined.gauge_code.nunique()} of {before} gauges "
          f"within Syr Darya / Amu Darya (Aral Sea) drainage")

    joined["signed_error_m3s"] = joined["discharge_pred_median_m3s"] - joined["discharge_observed_m3s"]
    joined["absolute_error_m3s"] = joined["signed_error_m3s"].abs()
    joined["squared_error_m3s2"] = joined["signed_error_m3s"] ** 2
    joined["absolute_error_pct"] = 100 * joined["absolute_error_m3s"] / (joined["discharge_observed_m3s"].abs() + 1e-6)
    joined["year"] = pd.to_datetime(joined["date"]).dt.year
    joined["month"] = pd.to_datetime(joined["date"]).dt.month
    joined["season"] = joined["month"].map({1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring", 6: "summer", 7: "summer", 8: "summer", 9: "fall", 10: "fall", 11: "fall", 12: "winter"})
    joined["dry_spell_state"] = np.where(joined["dry_spell"].eq(1), "dry_spell", "normal")
    joined["predicted_low_flow"] = joined["discharge_pred_median_m3s"] < joined["discharge_q25"]
    joined["dry_spell_proxy_hit"] = joined["predicted_low_flow"] & joined["dry_spell"].eq(1)
    return joined


def summarize(joined: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    def metrics(group: pd.DataFrame) -> pd.Series:
        return pd.Series({
            "n": len(group),
            "bias_pred_minus_obs_m3s": group.signed_error_m3s.mean(),
            "mae_m3s": group.absolute_error_m3s.mean(),
            "rmse_m3s": np.sqrt(group.squared_error_m3s2.mean()),
            "median_absolute_error_pct": group.absolute_error_pct.median(),
            "interval_coverage_pct": 100 * group.in_interval.mean(),
            "dry_spell_months": int(group.dry_spell.sum()),
            "predicted_low_flow_rate_pct": 100 * group.predicted_low_flow.mean(),
            "dry_spell_proxy_hits": int(group.dry_spell_proxy_hit.sum()),
        })

    summary = joined.groupby("gauge_code", sort=True).apply(metrics, include_groups=False).reset_index()
    summary["dry_spell_mae_m3s"] = joined[joined.dry_spell.eq(1)].groupby("gauge_code").absolute_error_m3s.mean().reindex(summary.gauge_code).to_numpy()
    summary["normal_mae_m3s"] = joined[joined.dry_spell.eq(0)].groupby("gauge_code").absolute_error_m3s.mean().reindex(summary.gauge_code).to_numpy()
    monthly = joined.groupby(["gauge_code", "month"], sort=True).apply(metrics, include_groups=False).reset_index()
    return summary, monthly


def save_tables(joined: pd.DataFrame, summary: pd.DataFrame, monthly: pd.DataFrame) -> None:
    columns = ["gauge_code", "date", "year", "month", "season", "dry_spell_state", "dry_spell_severity",
               "discharge_observed_m3s", "discharge_pred_median_m3s", "discharge_pred_p10_m3s",
               "discharge_pred_p90_m3s", "signed_error_m3s", "absolute_error_m3s", "absolute_error_pct",
               "in_interval", "stress_accumulation_index", "dry_spell_discharge", "predicted_low_flow"]
    joined[columns].to_csv(OUT_CSV, index=False)
    monthly.to_csv(OUT_MONTHLY, index=False)


def plot_error_atlas(joined: pd.DataFrame, summary: pd.DataFrame) -> None:
    # Two panels only, at a larger size: a 2x2 grid of per-gauge or
    # per-basin detail (even aggregated to 14 basins) still reads as clutter.
    # Everything not shown here (monthly bias timing, residual shape) is one
    # sentence in the surrounding text instead of a fifth thing to decode.
    n_gauges = summary.gauge_code.nunique()
    basins = sorted(joined["BASIN"].unique(), key=lambda b: -joined[joined.BASIN.eq(b)].shape[0])
    state_colors = {"normal": "#5d8f99", "dry_spell": "#c96b4b"}
    state_labels = {"normal": "Normal", "dry_spell": "Dry spell"}

    figure, axes = plt.subplots(1, 2, figsize=(13, 5.5), dpi=160)
    figure.patch.set_facecolor("white")

    axis = axes[0]
    for state in ("normal", "dry_spell"):
        data = joined[joined.dry_spell_state.eq(state)]
        axis.scatter(data.discharge_observed_m3s, data.discharge_pred_median_m3s, s=16, alpha=.5,
                     color=state_colors[state], label=state_labels[state])
    limit = max(joined.discharge_observed_m3s.max(), joined.discharge_pred_median_m3s.max()) * 1.05
    axis.plot([0, limit], [0, limit], "--", color="#333333", linewidth=1)
    axis.set(xlabel="Observed discharge (m3/s)", ylabel="Predicted discharge (m3/s)",
             title=f"Held-out predictions ({n_gauges} gauges)")
    axis.legend(fontsize=10, frameon=False)

    axis = axes[1]
    state = joined.groupby(["BASIN", "dry_spell_state"], sort=False).absolute_error_m3s.mean().unstack(fill_value=np.nan).reindex(basins)
    x = np.arange(len(basins))
    width = .36
    axis.bar(x - width / 2, state.get("normal", pd.Series(index=basins)).fillna(0), width, label="Normal", color=state_colors["normal"])
    axis.bar(x + width / 2, state.get("dry_spell", pd.Series(index=basins)).fillna(0), width, label="Dry spell", color=state_colors["dry_spell"])
    axis.set(xticks=x, xticklabels=basins, ylabel="MAE (m3/s)", title="Error by dry-spell state, per basin")
    axis.tick_params(axis="x", labelrotation=45, labelsize=9)
    axis.legend(fontsize=10, frameon=False)

    for axis in axes.flat:
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", alpha=.2)
        axis.tick_params(labelsize=10)
    figure.suptitle("Dry-spell model error, Syr Darya & Amu Darya gauges only", fontsize=14, x=.04, ha="left")
    figure.tight_layout()
    figure.savefig(OUT_ERROR_FIGURE, facecolor="white")
    plt.close(figure)


def plot_basin_context_map() -> None:
    try:
        import geopandas as gpd
    except ImportError as error:
        raise RuntimeError("geopandas is required to create the basin context map") from error

    basins = gpd.read_file(BASINS)
    catchment = gpd.read_file(CATCHMENT)
    figure, axis = plt.subplots(figsize=(10, 8), dpi=160)
    basins.boundary.plot(ax=axis, color="#9bb5b1", linewidth=.18, alpha=.7)
    catchment.plot(ax=axis, color="#d76c4a", edgecolor="#7e3024", linewidth=.6, alpha=.35)
    if REACH_AUDIT.exists():
        audit = json.loads(REACH_AUDIT.read_text())
        axis.scatter(audit["longitude"], audit["latitude"], marker="*", s=85, color="#a42b47", edgecolor="white", linewidth=.8, zorder=4, label="Pskem gauge coordinate")
    axis.set_title("BasinATLAS context for dry-spell analysis\nPskem candidate catchment highlighted; not a gauge-error interpolation map", loc="left", fontsize=13)
    axis.set_xlabel("Longitude")
    axis.set_ylabel("Latitude")
    axis.legend(frameon=True, fontsize=8, loc="lower left")
    axis.grid(alpha=.2)
    figure.tight_layout()
    figure.savefig(OUT_MAP, facecolor="white")
    plt.close(figure)


def plot_gauge_error_map(summary: pd.DataFrame) -> None:
    try:
        import geopandas as gpd
    except ImportError as error:
        raise RuntimeError("geopandas is required to create the gauge error map") from error

    stations = gpd.read_file(STATIONS)
    duplicate_codes = int(stations.code.duplicated().sum())
    stations = stations.drop_duplicates("code", keep="first")
    stations = stations.merge(summary[["gauge_code", "rmse_m3s", "dry_spell_months", "interval_coverage_pct"]],
                              left_on="code", right_on="gauge_code", how="left", validate="one_to_one")
    figure, axis = plt.subplots(figsize=(10, 8), dpi=160)
    basins = gpd.read_file(BASINS)
    basins.boundary.plot(ax=axis, color="#c2d1ce", linewidth=.16, alpha=.65)
    mapped = stations.dropna(subset=["rmse_m3s"])
    mapped.plot(ax=axis, column="rmse_m3s", cmap="magma", markersize=22 + 5 * mapped["dry_spell_months"],
                legend=True, legend_kwds={"label": "Held-out RMSE (m3/s)", "shrink": .75}, edgecolor="white", linewidth=.35)
    axis.set_title(f"Syr Darya & Amu Darya held-out error map ({len(mapped)} gauges)\n"
                   f"Color = RMSE; marker size = observed dry-spell months ({duplicate_codes} exact duplicate station rows removed)",
                   loc="left", fontsize=13)
    axis.set_xlabel("Longitude")
    axis.set_ylabel("Latitude")
    axis.grid(alpha=.2)
    figure.tight_layout()
    figure.savefig(OUT_ERROR_MAP, facecolor="white")
    plt.close(figure)


def plot_network_inventory_map(summary: pd.DataFrame) -> None:
    """Show the full gauge registry separately from the modelling subset."""
    import geopandas as gpd

    stations = gpd.read_file(STATIONS).drop_duplicates("code", keep="first")
    modelled = set(summary.gauge_code)
    with_series = stations[stations["has_ts"].fillna(False).astype(bool)]
    without_series = stations[~stations["has_ts"].fillna(False).astype(bool)]
    modelled_stations = stations[stations.code.isin(modelled)]
    figure, axis = plt.subplots(figsize=(10, 8), dpi=160)
    basins = gpd.read_file(BASINS)
    basins.boundary.plot(ax=axis, color="#d4dfdc", linewidth=.14, alpha=.55)
    without_series.plot(ax=axis, color="#b8c1c0", markersize=8, alpha=.65, label=f"Registry only ({len(without_series)})")
    with_series.plot(ax=axis, color="#4d8390", markersize=13, alpha=.75, label=f"With discharge series ({len(with_series)})")
    modelled_stations.plot(ax=axis, color="#c65336", edgecolor="white", linewidth=.35, markersize=30, label=f"Modelled here ({len(modelled_stations)})")
    axis.set_title("CA-discharge gauge network coverage\nAll unique gauge locations versus the Syr Darya / Amu Darya modelling subset",
                   loc="left", fontsize=13)
    axis.set_xlabel("Longitude")
    axis.set_ylabel("Latitude")
    axis.legend(frameon=True, fontsize=8, loc="lower left")
    axis.grid(alpha=.2)
    figure.tight_layout()
    figure.savefig(OUT_NETWORK_MAP, facecolor="white")
    plt.close(figure)


def write_report(joined: pd.DataFrame, summary: pd.DataFrame, excluded: pd.DataFrame) -> None:
    worst = summary.sort_values("rmse_m3s", ascending=False).iloc[0]
    dry = joined[joined.dry_spell.eq(1)]
    dry_mae = dry.absolute_error_m3s.mean() if len(dry) else float("nan")
    normal_mae = joined[joined.dry_spell.eq(0)].absolute_error_m3s.mean()
    excluded_by_basin = excluded.groupby("BASIN").gauge_code.nunique().sort_values(ascending=False)
    lines = [
        "# Dry-Spell Held-Out Error Analysis",
        "",
        "**Scope:** Corrected chronological validation predictions, Syr Darya / Amu Darya (Aral Sea drainage) gauges only.",
        "",
        f"The analysis contains **{len(joined):,} held-out records** across **{joined.gauge_code.nunique()} gauges**. Overall p10-p90 interval coverage is **{100 * joined.in_interval.mean():.1f}%**. This is below nominal 90% and should not be described as calibrated uncertainty.",
        "",
        f"**{int(excluded_by_basin.sum())} CA-discharge gauges with usable discharge history were excluded** because their basin "
        f"does not drain to the Aral Sea: " +
        ", ".join(f"{basin} ({n})" for basin, n in excluded_by_basin.items()) +
        ". Harirud and Murghab flow toward Turkmenistan/Iran; Balkh, Shirintagab, Chu and Talas are separate "
        "endorheic basins. They are real, modellable gauges (see `gauge_ensemble_models.pkl`), just not part of this basin's study.",
        "",
        "## Findings",
        "",
        f"- Mean absolute error during observed dry-spell months: **{dry_mae:.3f} m3/s**.",
        f"- Mean absolute error during normal months: **{normal_mae:.3f} m3/s**.",
        f"- Largest held-out RMSE: **{worst.gauge_code} ({worst.rmse_m3s:.3f} m3/s)**.",
        f"- Dry-spell months in the held-out sample: **{int(joined.dry_spell.sum())}** of {len(joined)} records.",
        "- The low-flow threshold proxy marks a predicted dry month when predicted median discharge is below the gauge Q25. It is a diagnostic, not a validated dry-spell classifier, because the published dry-spell label also contains precipitation and AET conditions.",
        "",
        "## Gauge summary",
        "",
        "| Gauge | N | Bias (m3/s) | MAE | RMSE | Interval coverage | Dry months | Dry-state MAE | Normal MAE |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary.itertuples():
        lines.append(f"| {row.gauge_code} | {int(row.n)} | {row.bias_pred_minus_obs_m3s:.3f} | {row.mae_m3s:.3f} | {row.rmse_m3s:.3f} | {row.interval_coverage_pct:.1f}% | {int(row.dry_spell_months)} | {row.dry_spell_mae_m3s:.3f} | {row.normal_mae_m3s:.3f} |")
    lines += [
        "",
        "## Figures",
        "",
        "![Held-out error atlas](dry_spell_error_atlas.png)",
        "",
        "![BasinATLAS context map](dry_spell_basin_context_map.png)",
        "",
        "![All-gauge held-out error map](dry_spell_gauge_error_map.png)",
        "",
        "![Gauge network inventory map](gauge_network_inventory_map.png)",
        "",
        "The BasinATLAS map is intentionally contextual. A complete verified gauge-to-basin coordinate crosswalk is not available for all gauges, so no unsupported spatial interpolation of model error is shown. The highlighted Pskem candidate catchment retains the existing reach-assignment warning.",
        "",
        "## Interpretation limits",
        "",
        "- Error magnitude is in cubic metres per second and is not comparable across gauges without flow normalization.",
        "- Dry-spell error comparisons are sensitive to the rare-event count and should be paired with event-level recall and precision.",
        "- The current analysis diagnoses continuous discharge error; it does not establish 1-, 2-, or 3-month dry-spell forecast skill.",
        "- Basin attributes can stratify error and explain regime differences, but they do not replace time-varying climate forcing or validated routing.",
    ]
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    joined = load_joined()
    summary, monthly = summarize(joined)
    save_tables(joined, summary, monthly)

    basins = pd.read_csv(BASIN_LOOKUP, dtype={'gauge_code': str})
    modelled_codes = set(pd.read_csv(PREDICTIONS, dtype={'gauge_code': str}, usecols=["gauge_code"]).gauge_code.unique())
    excluded = basins[basins.gauge_code.isin(modelled_codes) & ~basins.aral_drainage]

    plot_error_atlas(joined, summary)
    plot_basin_context_map()
    plot_gauge_error_map(summary)
    plot_network_inventory_map(summary)
    write_report(joined, summary, excluded)
    manifest = {
        "inputs": [str(path.relative_to(ROOT)) for path in [PREDICTIONS, FEATURES, BASIN_LOOKUP, BASINS, STATIONS, CATCHMENT, REACH_AUDIT]],
        "outputs": [str(path.relative_to(ROOT)) for path in [OUT_CSV, OUT_MONTHLY, OUT_REPORT, OUT_ERROR_FIGURE, OUT_MAP, OUT_ERROR_MAP, OUT_NETWORK_MAP]],
        "input_hashes": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in [PREDICTIONS, FEATURES, BASIN_LOOKUP, BASINS, STATIONS, CATCHMENT, REACH_AUDIT]},
        "n_validation_records": len(joined),
        "n_gauges": int(joined.gauge_code.nunique()),
        "overall_interval_coverage_pct": float(100 * joined.in_interval.mean()),
        "map_scope": "BasinATLAS level 10 context and provisional Pskem candidate catchment; no unsupported gauge interpolation",
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"records": len(joined), "gauges": int(joined.gauge_code.nunique()), "coverage_pct": manifest["overall_interval_coverage_pct"], "outputs": manifest["outputs"]}, indent=2))


if __name__ == "__main__":
    main()
