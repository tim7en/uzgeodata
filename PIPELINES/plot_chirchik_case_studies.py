"""Export the held-observation case-study figure as PNG and vector PDF."""
import hashlib
import json
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

from build_chirchik_case_studies import OUT


def main():
    source = OUT / "chirchik.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titlelocation": "left", "axes.titleweight": "bold"})
    fig, axes = plt.subplots(3, 1, figsize=(11.7, 9.5), layout="constrained")
    for ax, variable, label, color in zip(axes[:2], ["precipitation_total", "air_temperature_mean"],
                                        ["Precipitation (mm/month)", "Air temperature (°C)"], ["#167e9b", "#b56627"]):
        rows = [r for r in data["station_series"] if r["station"] == "Pskem" and r["variable"] == variable]
        dates = [datetime.strptime(r["period"], "%Y-%m") for r in rows]
        values = [np.nan if r["value"] is None else r["value"] for r in rows]
        ax.plot(dates, values, color=color, linewidth=1.2)
        ax.set_ylabel(label)
        ax.set_title(f"{'a' if variable == 'precipitation_total' else 'b'}. Pskem observed {'monthly totals' if variable == 'precipitation_total' else 'monthly means; three 2014 gaps retained'}")
    rows = data["discharge_monthly"]
    dates = [datetime.strptime(r["period"], "%Y-%m") for r in rows]
    axes[2].plot(dates, [r["screened_mean"] if r["eligible"] else np.nan for r in rows], color="#167e9b", linewidth=1.2, label="Screened observations")
    axes[2].plot(dates, [r["benchmark"] if r["benchmark"] is not None else np.nan for r in rows], color="#b56627", linewidth=1.3, linestyle="--", label="Seasonal benchmark (trained 2001–2010)")
    axes[2].axvspan(datetime(2011, 1, 1), datetime(2018, 1, 1), color="#dbe9ee", alpha=.6, zorder=-1)
    axes[2].set_ylabel("Discharge (m³/s)")
    b = data["benchmark"]["scores"]
    axes[2].set_title(f"c. Pskem–Mullala: held-out 2011–2017 | NSE {b['nse']:.3f}, KGE {b['kge']:.3f}, RMSE {b['rmse']:.1f} m³/s")
    axes[2].legend(loc="upper left", frameon=False, ncol=2, fontsize=8)
    for ax in axes:
        ax.grid(axis="y", alpha=.2)
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.margins(x=.01)
    fig.suptitle("Chirchik case studies · the Pskem observation base", fontsize=15, fontweight="bold")
    fig.supxlabel("Source: delivered station workbooks. Screening: 3 flagged values and 1 impossible date excluded; monthly daily coverage ≥90%.\nProduct validation is pending historical station-cell extraction. Shading marks held-out discharge years.", fontsize=8)
    for extension in ["png", "pdf"]:
        destination = OUT / f"pskem-observation-evidence.{extension}"
        temporary = destination.with_name(f"pskem-observation-evidence.tmp.{extension}")
        fig.savefig(temporary, dpi=200)
        temporary.replace(destination)
    plt.close(fig)
    (OUT / "pskem-observation-evidence.manifest.json").write_text(json.dumps({"input": source.name,
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "script": "PIPELINES/plot_chirchik_case_studies.py",
        "outputs": ["pskem-observation-evidence.png", "pskem-observation-evidence.pdf"]}, indent=2) + "\n", encoding="utf-8")
    print("Exported Pskem observation evidence: PNG + PDF")


if __name__ == "__main__":
    main()
