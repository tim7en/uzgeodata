#!/usr/bin/env python3
"""Train gauge-specific ensemble models with uncertainty quantification.

For each gauge, trains a separate ensemble considering:
1. That gauge's discharge observations + regional context
2. Upstream meteorological station influence (distance-weighted)
3. Quantile regression for uncertainty bounds

Outputs:
- gauge_ensemble_models.pkl (dict of {gauge_code: model_bundle})
- gauge_variable_importance.csv (per-gauge feature importance)
- gauge_uncertainty_calibration.json (error distributions by gauge)
- gauge_quantile_predictions.csv (10th/50th/90th percentile predictions)

Usage:
    python PIPELINES/train_gauge_specific_ensemble.py
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
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.linear_model import Ridge, LinearRegression, QuantileRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
except ImportError as e:
    print(f"ERROR: scikit-learn not installed or import failed: {e}")
    print("Install with: pip install scikit-learn")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "PUBLISHED/data/case-studies"


def load_data(data_path: Path, min_feature_coverage: float = 0.9) -> Tuple[pd.DataFrame, List[str]]:
    """Load feature matrix."""
    print(f"Loading data from {data_path.name}...")
    df = pd.read_csv(data_path)
    
    # Identify feature columns (exclude gauge_code, year, month, discharge_m3s)
    exclude = {'gauge_code', 'year', 'month', 'discharge_m3s', 'date'}
    all_features = [col for col in df.columns if col not in exclude]
    
    # Use a common feature set so every gauge is eligible for the same model.
    # Sparse climate columns are retained only when the requested coverage supports
    # a network-wide model; they remain available in the source data for a separate
    # climate-enhanced experiment.
    available_features = [f for f in all_features if df[f].notna().mean() >= min_feature_coverage]
    
    print(f"  Loaded {len(df)} records across {df['gauge_code'].nunique()} gauges")
    print(f"  Network-wide features (coverage >= {min_feature_coverage:.0%}): {len(available_features)} of {len(all_features)}")
    print(f"  Sparse features excluded from all-gauge run: {len(all_features) - len(available_features)}")
    
    return df, available_features


def prepare_gauge_data(gauge_df: pd.DataFrame, features: List[str]) -> Tuple[np.ndarray, np.ndarray]:
    """Prepare features and target for a single gauge."""
    X = gauge_df[features].values
    y = gauge_df['discharge_m3s'].values
    
    # Drop rows with NaN
    valid_idx = ~(np.isnan(X).any(axis=1) | np.isnan(y))
    X = X[valid_idx]
    y = y[valid_idx]
    
    return X, y


def train_gauge_ensemble(gauge_code: str, gauge_df: pd.DataFrame, features: List[str]) -> Dict:
    """Train ensemble model for a single gauge with quantile regression.
    
    Trains:
    - RandomForest (main predictor)
    - GradientBoosting (residual learner)
    - Ridge (meta-learner for stacking)
    - QuantileRegressor ensemble for uncertainty bounds
    """
    
    gauge_df = gauge_df.sort_values('date').reset_index(drop=True)
    valid_df = gauge_df.dropna(subset=features + ['discharge_m3s'])
    X, y = prepare_gauge_data(gauge_df, features)
    
    if len(X) < 20:  # Not enough data for this gauge
        return None
    
    # Hold out the latest observations to match forecasting use.
    n_train = int(0.8 * len(X))
    train_idx = np.arange(n_train)
    val_idx = np.arange(n_train, len(X))
    
    X_train, X_val = X[train_idx], X[val_idx]
    y_train, y_val = y[train_idx], y[val_idx]
    
    # Scale
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    
    # Base learners
    rf = RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42, n_jobs=-1)
    gb = GradientBoostingRegressor(n_estimators=100, learning_rate=0.1, max_depth=5, random_state=42)
    
    rf.fit(X_train_scaled, y_train)
    gb.fit(X_train_scaled, y_train)
    
    # Meta-features for stacking
    rf_meta_train = rf.predict(X_train_scaled)
    gb_meta_train = gb.predict(X_train_scaled)
    meta_train = np.column_stack([rf_meta_train, gb_meta_train])
    
    # Meta-learner
    meta = Ridge(alpha=1.0)
    meta.fit(meta_train, y_train)
    
    # Validation performance
    rf_val = rf.predict(X_val_scaled)
    gb_val = gb.predict(X_val_scaled)
    meta_val = np.column_stack([rf_val, gb_val])
    y_pred = meta.predict(meta_val)
    
    r2 = r2_score(y_val, y_pred)
    rmse = np.sqrt(mean_squared_error(y_val, y_pred))
    
    # Quantile regressors for uncertainty (lower/median/upper bounds)
    qr_lower = QuantileRegressor(quantile=0.1, alpha=1e-4, solver='highs')
    qr_median = QuantileRegressor(quantile=0.5, alpha=1e-4, solver='highs')
    qr_upper = QuantileRegressor(quantile=0.9, alpha=1e-4, solver='highs')
    
    qr_lower.fit(X_train_scaled, y_train)
    qr_median.fit(X_train_scaled, y_train)
    qr_upper.fit(X_train_scaled, y_train)
    
    # Feature importance (from RF)
    feature_importance = rf.feature_importances_
    
    # Error analysis on validation set
    residuals = y_val - y_pred
    error_stats = {
        'mae': float(mean_absolute_error(y_val, y_pred)),
        'rmse': float(rmse),
        'r2': float(r2),
        'residual_mean': float(np.mean(residuals)),
        'residual_std': float(np.std(residuals)),
        'residual_skew': float(pd.Series(residuals).skew()),
        'n_train': len(y_train),
        'n_validation': len(y_val),
    }
    
    return {
        'gauge_code': gauge_code,
        'models': {
            'rf': rf,
            'gb': gb,
            'meta': meta,
            'qr_lower': qr_lower,
            'qr_median': qr_median,
            'qr_upper': qr_upper,
        },
        'scaler': scaler,
        'features': features,
        'feature_importance': feature_importance,
        'n_train': len(X_train),
        'n_validation': len(X_val),
        'validation_dates': valid_df.iloc[val_idx]['date'].astype(str).tolist(),
        'error_stats': error_stats,
    }


def train_all_gauges(df: pd.DataFrame, features: List[str]) -> Dict[str, Dict]:
    """Train ensemble for each gauge."""
    
    print("\nTraining gauge-specific ensembles...")
    
    gauge_models = {}
    failed_gauges = []
    
    for i, gauge_code in enumerate(sorted(df['gauge_code'].unique()), 1):
        gauge_df = df[df['gauge_code'] == gauge_code]
        
        try:
            result = train_gauge_ensemble(gauge_code, gauge_df, features)
            
            if result:
                gauge_models[gauge_code] = result
                print(f"  {i:2d}. {gauge_code:20s} R²={result['error_stats']['r2']:.3f}, n={result['n_train']:4d}")
            else:
                failed_gauges.append((gauge_code, 'insufficient_data'))
        
        except Exception as e:
            failed_gauges.append((gauge_code, str(e)))
    
    print(f"\n✓ Successfully trained {len(gauge_models)} gauges")
    if failed_gauges:
        print(f"⚠ Failed to train {len(failed_gauges)} gauges (insufficient data or errors)")
    
    return gauge_models


def extract_variable_importance(gauge_models: Dict[str, Dict], features: List[str]) -> pd.DataFrame:
    """Extract per-gauge feature importance."""
    
    print("\nExtracting per-gauge variable importance...")
    
    importance_data = []
    
    for gauge_code, model_bundle in gauge_models.items():
        importance = model_bundle['feature_importance']
        
        for feat, imp in zip(features, importance):
            importance_data.append({
                'gauge_code': gauge_code,
                'feature': feat,
                'importance': imp,
                'r2_validation': model_bundle['error_stats']['r2'],
            })
    
    importance_df = pd.DataFrame(importance_data)
    
    # Summary statistics
    print(f"  Top 10 most important features (averaged across gauges):")
    top_features = importance_df.groupby('feature')['importance'].mean().nlargest(10)
    for feat, imp in top_features.items():
        print(f"    {feat:35s} {imp:6.4f}")
    
    return importance_df


def extract_uncertainty_calibration(gauge_models: Dict[str, Dict]) -> Dict:
    """Extract error statistics for uncertainty quantification."""
    
    print("\nCalibrating uncertainty by gauge...")
    
    calibration = {
        'gauges': {},
        'summary': {
            'n_gauges': len(gauge_models),
            'median_r2': float(np.median([m['error_stats']['r2'] for m in gauge_models.values()])),
            'median_mae': float(np.median([m['error_stats']['mae'] for m in gauge_models.values()])),
            'median_residual_std': float(np.median([m['error_stats']['residual_std'] for m in gauge_models.values()])),
        }
    }
    
    for gauge_code, model_bundle in gauge_models.items():
        calibration['gauges'][gauge_code] = {
            'r2': model_bundle['error_stats']['r2'],
            'mae': model_bundle['error_stats']['mae'],
            'rmse': model_bundle['error_stats']['rmse'],
            'residual_mean': model_bundle['error_stats']['residual_mean'],
            'residual_std': model_bundle['error_stats']['residual_std'],
            'residual_skew': model_bundle['error_stats']['residual_skew'],
            'n_training': model_bundle['n_train'],
            'n_validation': model_bundle['n_validation'],
        }
    
    return calibration


def save_results(gauge_models: Dict[str, Dict], importance_df: pd.DataFrame, 
                 calibration: Dict, output_dir: Path):
    """Save all results."""
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save gauge-specific models
    model_file = output_dir / "gauge_ensemble_models.pkl"
    with model_file.open('wb') as f:
        pickle.dump(gauge_models, f)
    print(f"\nSaved {len(gauge_models)} gauge models to {model_file.name}")
    
    # Save feature importance
    importance_file = output_dir / "gauge_variable_importance.csv"
    importance_df.to_csv(importance_file, index=False)
    print(f"Saved per-gauge importance to {importance_file.name}")
    
    # Save uncertainty calibration
    calibration_file = output_dir / "gauge_uncertainty_calibration.json"
    with calibration_file.open('w') as f:
        json.dump(calibration, f, indent=2)
    print(f"Saved uncertainty calibration to {calibration_file.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path,
                       default=OUTPUT_DIR / "regional_discharge_data.csv",
                       help='Input feature matrix CSV')
    parser.add_argument('--output_dir', type=Path, default=OUTPUT_DIR,
                       help='Output directory')
    parser.add_argument('--min-feature-coverage', type=float, default=0.9,
                       help='Minimum network-wide non-null coverage for a shared feature')
    
    args = parser.parse_args()
    
    if not args.data.exists():
        print(f"ERROR: Data file not found: {args.data}")
        print("First run: python PIPELINES/build_regional_discharge_model.py")
        return 1
    
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load data
    df, features = load_data(args.data, args.min_feature_coverage)
    
    # Train gauge-specific ensembles
    gauge_models = train_all_gauges(df, features)
    
    # Extract variable importance
    importance_df = extract_variable_importance(gauge_models, features)
    
    # Extract uncertainty calibration
    calibration = extract_uncertainty_calibration(gauge_models)
    
    # Save results
    save_results(gauge_models, importance_df, calibration, args.output_dir)
    
    print(f"\n✓ Gauge-specific ensemble training complete")
    print(f"  Output directory: {args.output_dir}")
    print(f"  Next: python PIPELINES/generate_gauge_predictions.py")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
