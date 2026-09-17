#!/usr/bin/env python3
"""Generate gauge-specific predictions with uncertainty quantification.

Uses trained gauge-specific ensembles to generate:
1. Point predictions (median)
2. Prediction intervals (90% confidence bands)
3. Quantile predictions (10th/50th/90th percentile)
4. Per-gauge uncertainty statistics

Outputs:
- gauge_quantile_predictions.csv (predictions with 90% intervals for all records)
- gauge_prediction_summary.csv (aggregated statistics by gauge)
- gauge_uncertainty_report.json (per-gauge uncertainty characterization)

Usage:
    python PIPELINES/generate_gauge_predictions.py
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
from datetime import datetime

try:
    from sklearn.preprocessing import StandardScaler
except ImportError:
    print("ERROR: scikit-learn not installed")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "PUBLISHED/data/case-studies"


def load_models_and_data(models_path: Path, data_path: Path) -> Tuple[Dict, pd.DataFrame]:
    """Load gauge-specific models and feature data."""
    
    print(f"Loading models from {models_path.name}...")
    with models_path.open('rb') as f:
        gauge_models = pickle.load(f)
    
    print(f"Loading data from {data_path.name}...")
    df = pd.read_csv(data_path, dtype={'gauge_code': str})
    
    print(f"  Loaded models for {len(gauge_models)} gauges")
    print(f"  Data: {len(df)} records")
    
    return gauge_models, df


def generate_gauge_predictions(gauge_code: str, gauge_df: pd.DataFrame,
                              model_bundle: Dict) -> pd.DataFrame:
    """Generate predictions with quantiles for a single gauge."""
    
    validation_dates = set(model_bundle.get('validation_dates', []))
    if validation_dates and 'date' in gauge_df.columns:
        gauge_df = gauge_df[gauge_df['date'].astype(str).isin(validation_dates)].copy()

    features = model_bundle['features']
    X = gauge_df[features].values
    
    # Handle NaN
    valid_idx = ~np.isnan(X).any(axis=1)
    X_valid = X[valid_idx]
    idx_valid = np.where(valid_idx)[0]
    
    if len(X_valid) == 0:
        return pd.DataFrame()  # No valid data
    
    # Scale
    scaler = model_bundle['scaler']
    X_scaled = scaler.transform(X_valid)
    
    # Models
    models = model_bundle['models']
    
    # Point prediction (stacking ensemble)
    rf_pred = models['rf'].predict(X_scaled)
    gb_pred = models['gb'].predict(X_scaled)
    meta_features = np.column_stack([rf_pred, gb_pred])
    y_pred_median = models['meta'].predict(meta_features)
    
    # Quantile predictions for uncertainty bounds
    y_pred_lower = models['qr_lower'].predict(X_scaled)
    y_pred_upper = models['qr_upper'].predict(X_scaled)
    
    # Clip to physical bounds (discharge >= 0)
    y_pred_lower = np.maximum(y_pred_lower, 0)
    y_pred_median = np.maximum(y_pred_median, 0)
    y_pred_upper = np.maximum(y_pred_upper, 0)
    
    # Ensure ordering: lower <= median <= upper
    for i in range(len(y_pred_lower)):
        y_pred_lower[i] = min(y_pred_lower[i], y_pred_median[i])
        y_pred_upper[i] = max(y_pred_upper[i], y_pred_median[i])
    
    # Build result dataframe
    result = gauge_df.iloc[idx_valid].copy()
    result['discharge_observed_m3s'] = gauge_df.iloc[idx_valid]['discharge_m3s'].values
    result['discharge_pred_median_m3s'] = y_pred_median
    result['discharge_pred_p10_m3s'] = y_pred_lower
    result['discharge_pred_p90_m3s'] = y_pred_upper
    result['prediction_interval_m3s'] = y_pred_upper - y_pred_lower
    
    # Error metrics
    observed = gauge_df.iloc[idx_valid]['discharge_m3s'].values
    result['error_m3s'] = observed - y_pred_median
    result['error_pct'] = 100.0 * result['error_m3s'] / (observed + 1e-6)
    result['in_interval'] = (observed >= y_pred_lower) & (observed <= y_pred_upper)
    
    return result


def aggregate_gauge_statistics(predictions_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate prediction statistics by gauge."""
    
    stats = []
    
    for gauge_code in predictions_df['gauge_code'].unique():
        gauge_preds = predictions_df[predictions_df['gauge_code'] == gauge_code]
        
        stats.append({
            'gauge_code': gauge_code,
            'n_predictions': len(gauge_preds),
            'median_pred_m3s': gauge_preds['discharge_pred_median_m3s'].median(),
            'median_obs_m3s': gauge_preds['discharge_observed_m3s'].median(),
            'rmse_m3s': np.sqrt((gauge_preds['error_m3s']**2).mean()),
            'mae_m3s': gauge_preds['error_m3s'].abs().mean(),
            'median_abs_error_pct': gauge_preds['error_pct'].abs().median(),
            'mean_interval_m3s': gauge_preds['prediction_interval_m3s'].mean(),
            'interval_coverage_pct': 100.0 * gauge_preds['in_interval'].mean(),
        })
    
    return pd.DataFrame(stats)


def characterize_uncertainty(gauge_models: Dict, predictions_df: pd.DataFrame) -> Dict:
    """Characterize uncertainty by gauge."""
    
    print("\nCharacterizing per-gauge uncertainty...")
    
    uncertainty = {
        'gauges': {},
        'generated': datetime.utcnow().isoformat() + 'Z',
    }
    
    for gauge_code, model_bundle in gauge_models.items():
        error_stats = model_bundle['error_stats']
        
        gauge_preds = predictions_df[predictions_df['gauge_code'] == gauge_code]
        
        if len(gauge_preds) > 0:
            interval_coverage = 100.0 * gauge_preds['in_interval'].mean()
        else:
            interval_coverage = np.nan
        
        uncertainty['gauges'][gauge_code] = {
            'validation_r2': error_stats['r2'],
            'validation_mae_m3s': error_stats['mae'],
            'validation_rmse_m3s': error_stats['rmse'],
            'residual_std_m3s': error_stats['residual_std'],
            'residual_bias_m3s': error_stats['residual_mean'],
            'residual_skewness': error_stats['residual_skew'],
            'training_records': error_stats.get('n_train', 0),
            'validation_records': error_stats.get('n_validation', 0),
            'empirical_interval_coverage_pct': interval_coverage,
            'interpretation': (
                'For forecasting: expect 90% of future observations to fall within '
                '[p10, p90] prediction interval. Coverage% shows how well this holds '
                'on validation data. Residual_std indicates typical prediction error.'
            )
        }
    
    # Add summary
    all_intervals = predictions_df['in_interval'].dropna()
    if len(all_intervals) > 0:
        uncertainty['summary'] = {
            'n_gauges': len(gauge_models),
            'n_predictions': len(predictions_df),
            'overall_interval_coverage_pct': 100.0 * all_intervals.mean(),
            'median_interval_width_m3s': predictions_df['prediction_interval_m3s'].median(),
        }
    
    return uncertainty


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', type=Path,
                       default=OUTPUT_DIR / "gauge_ensemble_models.pkl",
                       help='Trained gauge-specific models')
    parser.add_argument('--data', type=Path,
                       default=OUTPUT_DIR / "regional_discharge_data.csv",
                       help='Feature matrix CSV')
    parser.add_argument('--output_dir', type=Path, default=OUTPUT_DIR,
                       help='Output directory')
    
    args = parser.parse_args()
    
    if not args.models.exists():
        print(f"ERROR: Models file not found: {args.models}")
        print("First run: python PIPELINES/train_gauge_specific_ensemble.py")
        return 1
    
    if not args.data.exists():
        print(f"ERROR: Data file not found: {args.data}")
        return 1
    
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load data
    gauge_models, df = load_models_and_data(args.models, args.data)
    
    # Generate predictions for each gauge
    print("\nGenerating gauge-specific quantile predictions...")
    
    all_predictions = []
    for i, (gauge_code, model_bundle) in enumerate(gauge_models.items(), 1):
        gauge_df = df[df['gauge_code'] == gauge_code]
        
        gauge_preds = generate_gauge_predictions(gauge_code, gauge_df, model_bundle)
        
        if len(gauge_preds) > 0:
            all_predictions.append(gauge_preds)
            print(f"  {i:2d}. {gauge_code:20s} {len(gauge_preds):5d} predictions")
    
    # Combine all predictions
    predictions_df = pd.concat(all_predictions, ignore_index=True)
    
    # Save predictions: only the prediction/error columns, not the full input
    # feature matrix generate_gauge_predictions() copied through per gauge —
    # that carried ~85 feature columns into every row for no downstream
    # consumer, multiplying this file's size by roughly the feature count.
    pred_file = args.output_dir / "gauge_quantile_predictions.csv"
    output_columns = [
        "gauge_code", "date", "discharge_observed_m3s", "discharge_pred_median_m3s",
        "discharge_pred_p10_m3s", "discharge_pred_p90_m3s", "prediction_interval_m3s",
        "error_m3s", "error_pct", "in_interval",
    ]
    predictions_df[output_columns].to_csv(pred_file, index=False)
    print(f"\nSaved {len(predictions_df)} predictions to {pred_file.name}")
    
    # Aggregate statistics
    summary_df = aggregate_gauge_statistics(predictions_df)
    
    summary_file = args.output_dir / "gauge_prediction_summary.csv"
    summary_df.to_csv(summary_file, index=False)
    print(f"Saved summary statistics to {summary_file.name}")
    
    # Uncertainty characterization
    uncertainty = characterize_uncertainty(gauge_models, predictions_df)
    
    uncertainty_file = args.output_dir / "gauge_uncertainty_report.json"
    with uncertainty_file.open('w') as f:
        json.dump(uncertainty, f, indent=2)
    print(f"Saved uncertainty report to {uncertainty_file.name}")
    
    print(f"\n✓ Prediction generation complete")
    print(f"  Median interval coverage: {uncertainty['summary']['overall_interval_coverage_pct']:.1f}%")
    print(f"  Median prediction interval width: {uncertainty['summary']['median_interval_width_m3s']:.2f} m³/s")
    print(f"  Next: python PIPELINES/generate_gauge_case_study.py")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
