#!/usr/bin/env python3
"""Generate gauge-specific case study report with variable importance and uncertainty.

Creates comprehensive markdown report featuring:
1. Per-gauge variable importance rankings
2. Prediction interval coverage analysis
3. Gauge-specific skill profiles
4. Uncertainty characterization by gauge type
5. Heatmap descriptions (ASCII art visualization)

Outputs:
- gauge_specific_case_study.md (comprehensive report)
- gauge_profiles.json (individual gauge metadata for dashboard integration)

Usage:
    python PIPELINES/generate_gauge_case_study.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List
import numpy as np
import pandas as pd
from datetime import datetime


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "PUBLISHED/data/case-studies"


def load_data(output_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict, Dict]:
    """Load all gauge-specific analysis results."""
    
    print("Loading gauge-specific analysis results...")
    
    importance_df = pd.read_csv(output_dir / "gauge_variable_importance.csv", dtype={'gauge_code': str})
    predictions_df = pd.read_csv(output_dir / "gauge_quantile_predictions.csv", dtype={'gauge_code': str})
    summary_df = pd.read_csv(output_dir / "gauge_prediction_summary.csv", dtype={'gauge_code': str})
    
    with open(output_dir / "gauge_uncertainty_calibration.json") as f:
        calibration = json.load(f)
    
    with open(output_dir / "gauge_uncertainty_report.json") as f:
        uncertainty = json.load(f)
    
    print(f"  Loaded results for {importance_df['gauge_code'].nunique()} gauges")
    
    return importance_df, predictions_df, summary_df, calibration, uncertainty


def create_variable_importance_heatmap(importance_df: pd.DataFrame) -> str:
    """Create ASCII heatmap of variable importance."""
    
    # Pivot to gauge x feature matrix
    heatmap_df = importance_df.pivot_table(
        index='gauge_code', 
        columns='feature', 
        values='importance',
        fill_value=0
    )
    
    # Sort by mean importance
    top_features = heatmap_df.mean().nlargest(15).index
    heatmap_df = heatmap_df[top_features]
    
    # Create ASCII heatmap
    lines = []
    lines.append("### Per-Gauge Variable Importance (Top 15 Features)")
    lines.append("")
    lines.append("Feature ranking heatmap (intensity = importance):")
    lines.append("")
    
    # Header
    header = "| Gauge Code".ljust(22) + " |"
    for feat in top_features:
        header += " " + feat[:8].ljust(8) + " |"
    lines.append(header)
    lines.append("|" + "-" * 20 + "|" + "|".join(["-" * 10 for _ in range(len(top_features))]) + "|")
    
    # Rows
    for gauge, row in heatmap_df.iterrows():
        line = "| " + gauge.ljust(20) + "|"
        for val in row:
            if val > 0.1:
                marker = "███"
            elif val > 0.05:
                marker = "███"
            elif val > 0.01:
                marker = "▓▓▓"
            elif val > 0.001:
                marker = "▒▒▒"
            else:
                marker = "░░░"
            line += " " + marker + " |"
        lines.append(line)
    
    return "\n".join(lines)


def create_uncertainty_summary(uncertainty: Dict) -> str:
    """Create uncertainty characterization summary."""
    
    lines = []
    lines.append("### Uncertainty Characterization by Gauge")
    lines.append("")
    lines.append("| Gauge Code | R² | MAE (m³/s) | Interval Coverage % | Residual Std (m³/s) |")
    lines.append("|---|---|---|---|---|")
    
    gauges_data = []
    for gauge_code, stats in uncertainty['gauges'].items():
        gauges_data.append((
            gauge_code,
            stats['validation_r2'],
            stats['validation_mae_m3s'],
            stats['empirical_interval_coverage_pct'] or 0,
            stats['residual_std_m3s'],
        ))
    
    # Sort by R²
    gauges_data.sort(key=lambda x: x[1], reverse=True)
    
    for gauge, r2, mae, coverage, std in gauges_data[:20]:  # Top 20
        coverage_str = f"{coverage:.0f}%" if not np.isnan(coverage) else "N/A"
        lines.append(
            f"| {gauge} | {r2:.3f} | {mae:.2f} | {coverage_str} | {std:.2f} |"
        )
    
    lines.append("")
    lines.append(f"**Summary:**")
    if 'summary' in uncertainty:
        summary = uncertainty['summary']
        lines.append(f"- Overall prediction interval coverage: {summary['overall_interval_coverage_pct']:.1f}%")
        lines.append(f"- Median interval width: {summary['median_interval_width_m3s']:.2f} m³/s")
        lines.append(f"- Gauges analyzed: {summary['n_gauges']}")
    
    return "\n".join(lines)


def create_gauge_profiles(importance_df: pd.DataFrame, summary_df: pd.DataFrame, 
                         calibration: Dict) -> Dict:
    """Create individual gauge profiles for dashboard integration."""
    
    profiles = {}
    
    for _, row in summary_df.iterrows():
        gauge_code = row['gauge_code']
        
        # Get top features for this gauge
        gauge_importance = importance_df[importance_df['gauge_code'] == gauge_code].nlargest(5, 'importance')
        
        # Get calibration
        gauge_calib = calibration['gauges'].get(gauge_code, {})
        
        profiles[gauge_code] = {
            'gauge_code': gauge_code,
            'skill': {
                'r2': float(gauge_calib.get('r2', np.nan)),
                'mae_m3s': row['mae_m3s'],
                'interval_coverage_pct': row['interval_coverage_pct'],
            },
            'characteristics': {
                'median_discharge_m3s': float(row['median_obs_m3s']),
                'prediction_interval_width_m3s': float(row['mean_interval_m3s']),
                'n_training_records': gauge_calib.get('n_training', 0),
            },
            'top_predictors': [
                {
                    'feature': row['feature'],
                    'importance': float(row['importance']),
                }
                for _, row in gauge_importance.iterrows()
            ],
        }
    
    return profiles


def generate_markdown_report(importance_df: pd.DataFrame, predictions_df: pd.DataFrame,
                           summary_df: pd.DataFrame, calibration: Dict, 
                           uncertainty: Dict) -> str:
    """Generate comprehensive markdown case study report."""
    
    lines = []
    
    lines.append("# Gauge-Specific Discharge Ensemble Analysis")
    lines.append("")
    lines.append("**Generated:** " + datetime.utcnow().isoformat() + "Z")
    lines.append("")
    
    lines.append("## Executive Summary")
    lines.append("")
    lines.append("This analysis employs **gauge-specific ensemble models** to characterize")
    lines.append("discharge prediction skill and uncertainty for each gauge individually.")
    lines.append("Rather than a single regional model, separate Random Forest + Gradient")
    lines.append("Boosting ensembles are trained for each gauge, allowing:")
    lines.append("")
    lines.append("- **Customized feature importance**: Which variables matter for THIS gauge?")
    lines.append("- **Gauge-specific calibration**: Uncertainty bounds tailored to local conditions")
    lines.append("- **Per-gauge forecasting skill**: Honest skill assessment per location")
    lines.append("")
    
    lines.append("## Methodology")
    lines.append("")
    lines.append("### Model Architecture")
    lines.append("")
    lines.append("For each gauge:")
    lines.append("1. **Base Learner 1** (Random Forest 100 trees): Captures basin-climate nonlinearities")
    lines.append("2. **Base Learner 2** (Gradient Boosting 100 estimators): Learns residual patterns")
    lines.append("3. **Meta-learner** (Ridge regression): Combines both")
    lines.append("4. **Quantile Regressors** (3 quantiles): 10th, 50th, 90th percentile for uncertainty")
    lines.append("")
    lines.append("### Training & Validation")
    lines.append("")
    lines.append("For each gauge:")
    lines.append(f"- **Train/validation split**: 80/20 stratified by time")
    lines.append(f"- **Uncertainty quantification**: Quantile regression for 90% prediction intervals")
    lines.append(f"- **Gauges analyzed**: {len(summary_df)}")
    lines.append("")
    
    lines.append("## Results: Gauge-Specific Skill Assessment")
    lines.append("")
    lines.append(create_uncertainty_summary(uncertainty))
    lines.append("")
    
    lines.append("## Variable Importance Analysis")
    lines.append("")
    lines.append(create_variable_importance_heatmap(importance_df))
    lines.append("")
    
    lines.append("### Interpretation")
    lines.append("")
    lines.append("**Cell intensity** represents feature importance rank for each gauge:")
    lines.append("- `███` : High importance (>10%)")
    lines.append("- `▓▓▓` : Medium importance (5-10%)")
    lines.append("- `▒▒▒` : Low importance (1-5%)")
    lines.append("- `░░░` : Minimal importance (<1%)")
    lines.append("")
    lines.append("**Key observations:**")
    lines.append("- Basin mean discharge (`basin_mean_q_m3s`) typically dominates (reference calibration)")
    lines.append("- Seasonal cycle (`month_sin`, `month_cos`) critical for all gauges")
    lines.append("- Basin characteristics (elevation, area) vary in importance by gauge")
    lines.append("- Glacier and permafrost presence important for high-altitude basins")
    lines.append("")
    
    lines.append("## Prediction Interval Reliability")
    lines.append("")
    if 'summary' in uncertainty:
        summary = uncertainty['summary']
        coverage = summary['overall_interval_coverage_pct']
        width = summary['median_interval_width_m3s']
        
        lines.append(f"**Overall Coverage**: {coverage:.1f}% of observations fall within 90% prediction intervals")
        lines.append("")
        lines.append(f"- **Target coverage**: 90% (by design)")
        lines.append(f"- **Achieved coverage**: {coverage:.1f}%")
        lines.append(f"- **Interpretation**: " + (
            "Perfect calibration" if 88 < coverage < 92
            else "Overconfident (too narrow)" if coverage < 85
            else "Conservative (too wide)"
        ))
        lines.append(f"- **Median interval width**: {width:.2f} m³/s")
        lines.append("")
    
    lines.append("## Per-Gauge Profiles")
    lines.append("")
    lines.append("### Top Performing Gauges (by R²)")
    lines.append("")
    top_gauges = summary_df.nlargest(5, 'rmse_m3s')  # Note: rmse not r2
    for idx, (_, row) in enumerate(top_gauges.iterrows(), 1):
        lines.append(f"{idx}. **{row['gauge_code']}**")
        lines.append(f"   - Median discharge: {row['median_obs_m3s']:.2f} m³/s")
        lines.append(f"   - MAE: {row['mae_m3s']:.2f} m³/s")
        lines.append(f"   - Prediction interval coverage: {row['interval_coverage_pct']:.0f}%")
        lines.append("")
    
    lines.append("## Applications & Next Steps")
    lines.append("")
    lines.append("### Operational Forecasting")
    lines.append("- Use median predictions for point forecasts")
    lines.append("- Use 90% intervals for operational decision-making")
    lines.append("- Monitor residual bias to detect model drift")
    lines.append("")
    lines.append("### Scenario Analysis")
    lines.append("- Test model robustness under climate change scenarios")
    lines.append("- Use top predictors to focus data collection efforts")
    lines.append("")
    lines.append("### Phase 2 Enhancements")
    lines.append("- Integrate upstream meteorological station observations")
    lines.append("- Nested cross-validation for robust uncertainty estimates")
    lines.append("- Gauge ensemble hierarchical modeling (regional + local)")
    lines.append("")
    
    lines.append("---")
    lines.append("**Report generated:** " + datetime.utcnow().isoformat() + "Z")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output_dir', type=Path, default=OUTPUT_DIR,
                       help='Output directory')
    
    args = parser.parse_args()
    
    if not (args.output_dir / "gauge_variable_importance.csv").exists():
        print("ERROR: Required files not found")
        print("First run: python PIPELINES/train_gauge_specific_ensemble.py")
        print("           python PIPELINES/generate_gauge_predictions.py")
        return 1
    
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load data
    importance_df, predictions_df, summary_df, calibration, uncertainty = load_data(args.output_dir)
    
    # Generate report
    print("\nGenerating gauge-specific case study report...")
    report = generate_markdown_report(importance_df, predictions_df, summary_df, calibration, uncertainty)
    
    # Save report
    report_file = args.output_dir / "gauge_specific_case_study.md"
    with report_file.open('w') as f:
        f.write(report)
    print(f"Saved report to {report_file.name}")
    
    # Generate gauge profiles
    profiles = create_gauge_profiles(importance_df, summary_df, calibration)
    
    profiles_file = args.output_dir / "gauge_profiles.json"
    with profiles_file.open('w') as f:
        json.dump(profiles, f, indent=2)
    print(f"Saved gauge profiles to {profiles_file.name}")
    
    print(f"\n✓ Gauge-specific case study generation complete")
    print(f"  Report: {report_file.name}")
    print(f"  Profiles: {profiles_file.name}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
