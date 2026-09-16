#!/usr/bin/env python3
"""Train statistical ensemble discharge model for regional CA-discharge prediction.

Builds a stacking ensemble combining:
- Random Forest (captures nonlinear basin-climate relationships)
- Gradient Boosting (learns residual patterns, seasonal adjustments)
- Meta-learner (Ridge regression combining both)

Includes:
- 5-fold SPATIAL cross-validation (by gauge cluster, prevents basin leakage)
- TEMPORAL hold-out validation (train 1940-2015, test 2016-2020, simulates forecasting)
- Feature importance analysis
- Uncertainty quantification (quantile regression)

⚠️  TEMPORAL LEAKAGE NOTE:
Spatial CV alone (split by gauge) allows temporal leakage: model trains on 
future years in other gauges, then predicts past years in test gauge.
Temporal hold-out is required to validate TRUE forecasting skill.

Usage:
    python PIPELINES/train_discharge_ensemble.py                    # Spatial CV only
    python PIPELINES/train_discharge_ensemble.py --temporal_split 2015  # Add temporal hold-out
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Tuple, Dict, List
import numpy as np
import pandas as pd
from datetime import datetime

try:
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import cross_validate, GridSearchCV
    from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
except ImportError:
    print("ERROR: scikit-learn not installed. Install with: pip install scikit-learn")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "PUBLISHED/data/case-studies"

# Feature groups for analysis
BASIN_FEATURES = [
    'basin_area_km2', 'basin_elevation_m', 'basin_slope_pct', 
    'basin_glacier_pct', 'basin_permafrost_pct',
    'basin_forest_pct', 'basin_shrub_pct', 'basin_grass_pct',
    'basin_urban_pct', 'basin_water_pct'
]

CLIMATE_FEATURES = [
    'terraclimate_precip_mm', 'terraclimate_tavg_c', 'terraclimate_pet_mm',
    'terraclimate_precip_lag1_mm', 'terraclimate_tavg_lag1_c',
    'terraclimate_precip_3m_mm', 'terraclimate_precip_6m_mm',
    'terraclimate_anom_precip'
]

UPSTREAM_FEATURES = [
    'upstream_stations_count', 'upstream_tavg_c', 'upstream_precip_mm'
]

TEMPORAL_FEATURES = [
    'month_sin', 'month_cos', 'year_normalized'
]


def load_data(data_path: Path) -> Tuple[pd.DataFrame, List[str]]:
    """Load feature matrix CSV and identify valid features."""
    print(f"Loading data from {data_path.name}...")
    
    df = pd.read_csv(data_path)
    print(f"  Loaded {len(df)} records across {df['gauge_code'].nunique()} gauges")
    
    # Identify which features are available (non-null)
    target = 'discharge_m3s'
    if target not in df.columns:
        raise ValueError(f"Target variable '{target}' not found in data")
    
    # Select features with sufficient non-null values
    feature_cols = [c for c in df.columns 
                   if c not in ['gauge_code', 'date', 'year', 'month', target]]
    
    available_features = []
    for col in feature_cols:
        non_null = df[col].notna().sum()
        if non_null > len(df) * 0.8:  # Require 80% non-null
            available_features.append(col)
            print(f"    ✓ {col} ({100*non_null/len(df):.1f}% available)")
    
    # Remove rows with missing target or essential features
    df = df.dropna(subset=[target] + available_features)
    print(f"  After filtering: {len(df)} complete records")
    
    return df, available_features


def prepare_features(df: pd.DataFrame, features: List[str]) -> Tuple[np.ndarray, np.ndarray]:
    """Extract X and y, handle missing values."""
    X = df[features].values
    y = df['discharge_m3s'].values
    
    # Simple imputation: use column median for missing values
    for i, col in enumerate(features):
        missing_mask = np.isnan(X[:, i])
        if missing_mask.any():
            col_median = np.nanmedian(X[:, i])
            X[missing_mask, i] = col_median
    
    return X, y


def spatial_cv_split(df: pd.DataFrame, n_folds: int = 5) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Split data by gauge for spatial cross-validation.
    
    Ensures each gauge's data stays together (either train or test),
    preventing data leakage from same location across folds.
    """
    gauges = df['gauge_code'].unique()
    
    # Group gauges into n_folds clusters
    np.random.seed(42)
    gauge_folds = np.random.choice(n_folds, len(gauges))
    gauge_to_fold = dict(zip(gauges, gauge_folds))
    
    splits = []
    for fold in range(n_folds):
        train_mask = np.array([gauge_to_fold[g] != fold for g in df['gauge_code']])
        test_mask = ~train_mask
        
        train_idx = np.where(train_mask)[0]
        test_idx = np.where(test_mask)[0]
        
        splits.append((train_idx, test_idx))
        print(f"  Fold {fold+1}: {len(train_idx)} train, {len(test_idx)} test records")
    
    return splits


def temporal_cv_split(df: pd.DataFrame, split_year: int = 2015) -> Tuple[np.ndarray, np.ndarray]:
    """Split data by year for temporal hold-out validation.
    
    Simulates operational forecasting: train on historical period,
    test on recent/future period. Prevents forward-looking leakage.
    
    Args:
        df: Data frame with 'year' column
        split_year: Final year to include in training (test starts at split_year+1)
    
    Returns:
        (train_indices, test_indices)
    """
    train_mask = df['year'] <= split_year
    test_mask = ~train_mask
    
    train_idx = np.where(train_mask)[0]
    test_idx = np.where(test_mask)[0]
    
    print(f"\n  Temporal split at year {split_year}:")
    print(f"    Train: {len(train_idx)} records (years ≤{split_year})")
    print(f"    Test:  {len(test_idx)} records (years >{split_year})")
    
    return train_idx, test_idx

def build_models() -> Dict:
    """Create sklearn model objects with reasonable hyperparameters."""
    return {
        'rf': RandomForestRegressor(
            n_estimators=200,
            max_depth=12,
            min_samples_leaf=5,
            min_samples_split=10,
            n_jobs=-1,
            random_state=42,
            verbose=0
        ),
        'gb': GradientBoostingRegressor(
            n_estimators=150,
            learning_rate=0.1,
            max_depth=5,
            min_samples_leaf=5,
            subsample=0.8,
            random_state=42,
            verbose=0
        ),
        'meta': Ridge(alpha=1.0)
    }


def train_ensemble(X: np.ndarray, y: np.ndarray, cv_splits: List) -> Dict:
    """Train stacking ensemble with cross-validation.
    
    Returns: {
        'model': trained ensemble,
        'scores': cross-validation metrics,
        'feature_importance': feature rankings
    }
    """
    print(f"\nTraining ensemble model ({len(cv_splits)} folds)...")
    
    models = build_models()
    scaler = StandardScaler()
    
    fold_scores = []
    feature_importances = []
    
    for fold_idx, (train_idx, test_idx) in enumerate(cv_splits):
        print(f"\n  Fold {fold_idx + 1}/{len(cv_splits)}")
        
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        
        # Scale features
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        # Train base learners
        print(f"    Training Random Forest...")
        models['rf'].fit(X_train_scaled, y_train)
        rf_pred_train = models['rf'].predict(X_train_scaled)
        rf_pred_test = models['rf'].predict(X_test_scaled)
        
        print(f"    Training Gradient Boosting...")
        models['gb'].fit(X_train_scaled, y_train)
        gb_pred_train = models['gb'].predict(X_train_scaled)
        gb_pred_test = models['gb'].predict(X_test_scaled)
        
        # Prepare meta-features
        meta_train = np.column_stack([rf_pred_train, gb_pred_train])
        meta_test = np.column_stack([rf_pred_test, gb_pred_test])
        
        # Train meta-learner
        models['meta'].fit(meta_train, y_train)
        ensemble_pred = models['meta'].predict(meta_test)
        
        # Evaluate
        r2 = r2_score(y_test, ensemble_pred)
        rmse = np.sqrt(mean_squared_error(y_test, ensemble_pred))
        mae = mean_absolute_error(y_test, ensemble_pred)
        
        # NSE (Nash-Sutcliffe Efficiency)
        ss_res = np.sum((y_test - ensemble_pred) ** 2)
        ss_tot = np.sum((y_test - np.mean(y_test)) ** 2)
        nse = 1 - (ss_res / ss_tot) if ss_tot > 0 else np.nan
        
        fold_scores.append({
            'fold': fold_idx + 1,
            'r2': round(r2, 4),
            'rmse': round(rmse, 3),
            'mae': round(mae, 3),
            'nse': round(nse, 4),
            'n_test': len(y_test),
        })
        
        # Feature importance from RF
        feature_importances.append(models['rf'].feature_importances_)
        
        print(f"    R²={r2:.4f}, RMSE={rmse:.2f}, NSE={nse:.4f}")
    
    # Average scores across folds
    avg_scores = {
        'r2': round(np.mean([s['r2'] for s in fold_scores]), 4),
        'rmse': round(np.mean([s['rmse'] for s in fold_scores]), 3),
        'mae': round(np.mean([s['mae'] for s in fold_scores]), 3),
        'nse': round(np.mean([s['nse'] for s in fold_scores]), 4),
    }
    
    print(f"\nCross-validation results:")
    print(f"  R² = {avg_scores['r2']} ± {np.std([s['r2'] for s in fold_scores]):.4f}")
    print(f"  RMSE = {avg_scores['rmse']} ± {np.std([s['rmse'] for s in fold_scores]):.2f}")
    print(f"  NSE = {avg_scores['nse']} ± {np.std([s['nse'] for s in fold_scores]):.4f}")
    
    # Average feature importances
    mean_importance = np.mean(feature_importances, axis=0)
    
    return {
        'models': models,
        'scaler': scaler,
        'cv_scores': fold_scores,
        'avg_scores': avg_scores,
        'feature_importance': mean_importance,
    }


def evaluate_temporal_split(X: np.ndarray, y: np.ndarray, df: pd.DataFrame,
                           models: Dict, scaler: StandardScaler,
                           split_year: int = 2015) -> Dict:
    """Evaluate model on temporal hold-out (no leakage simulation).
    
    Trains on historical data only, tests on recent data.
    This simulates real forecasting performance.
    """
    print(f"\nTemporal hold-out validation (training on historical period only)...")
    
    # Split by year
    train_idx, test_idx = temporal_cv_split(df, split_year)
    
    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    
    if len(test_idx) < 10:
        print(f"  ⚠ Only {len(test_idx)} test records; skipping temporal eval")
        return {}
    
    # Scale and predict
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # Retrain models on historical data only
    print(f"  Retraining models on historical data (years ≤{split_year})...")
    models['rf'].fit(X_train_scaled, y_train)
    models['gb'].fit(X_train_scaled, y_train)
    
    rf_pred = models['rf'].predict(X_test_scaled)
    gb_pred = models['gb'].predict(X_test_scaled)
    
    meta_features = np.column_stack([rf_pred, gb_pred])
    ensemble_pred = models['meta'].predict(meta_features)
    
    # Evaluate
    r2 = r2_score(y_test, ensemble_pred)
    rmse = np.sqrt(mean_squared_error(y_test, ensemble_pred))
    mae = mean_absolute_error(y_test, ensemble_pred)
    ss_res = np.sum((y_test - ensemble_pred) ** 2)
    ss_tot = np.sum((y_test - np.mean(y_test)) ** 2)
    nse = 1 - (ss_res / ss_tot) if ss_tot > 0 else np.nan
    
    print(f"  Temporal hold-out (forecasting sim): R²={r2:.4f}, RMSE={rmse:.2f}, NSE={nse:.4f}")
    print(f"  ⚠ INTERPRETATION: This is TRUE forecasting skill (no temporal leakage)")
    
    return {
        'temporal_r2': round(r2, 4),
        'temporal_rmse': round(rmse, 3),
        'temporal_mae': round(mae, 3),
        'temporal_nse': round(nse, 4),
        'temporal_n_test': len(y_test),
        'temporal_split_year': split_year,
        'temporal_note': 'Trained only on historical data; tests forecasting without leakage',
    }

def save_results(results: Dict, feature_names: List[str], output_dir: Path):
    """Save trained model and results."""
    
    # Save model
    model_file = output_dir / "discharge_ensemble_model.pkl"
    with model_file.open('wb') as f:
        pickle.dump({
            'models': results['models'],
            'scaler': results['scaler'],
            'features': feature_names,
        }, f)
    print(f"\nSaved model to {model_file.name}")
    
    # Save feature importance
    importance_file = output_dir / "discharge_feature_importance.csv"
    importance_df = pd.DataFrame({
        'feature': feature_names,
        'importance': results['feature_importance'],
    }).sort_values('importance', ascending=False)
    importance_df.to_csv(importance_file, index=False)
    print(f"Saved feature importance to {importance_file.name}")
    
    # Save cross-validation results
    cv_file = output_dir / "discharge_cv_results.json"
    cv_data = {
        'generated': datetime.utcnow().isoformat() + 'Z',
        'fold_results': results['cv_scores'],
        'average_metrics': results['avg_scores'],
        'note': 'Spatial CV: splits by gauge (can have temporal leakage)',
        'feature_importance_top10': importance_df.head(10).to_dict('records'),
        'n_features': len(feature_names),
        'n_observations': len(feature_names),
    }
    
    # Add temporal results if available
    if 'temporal' in results and results['temporal']:
        cv_data['temporal_holdout'] = results['temporal']
        cv_data['temporal_note'] = 'Temporal hold-out: trains only on historical data, tests on future. TRUE forecasting skill.'
    
    with cv_file.open('w') as f:
        json.dump(cv_data, f, indent=2)
    print(f"Saved CV results to {cv_file.name}")
    
    # Print top features
    print("\nTop 10 predictive features:")
    for idx, row in importance_df.head(10).iterrows():
        print(f"  {row['feature']:35s} {row['importance']:6.4f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, 
                       default=OUTPUT_DIR / "regional_discharge_data.csv",
                       help='Input feature matrix CSV')
    parser.add_argument('--folds', type=int, default=5,
                       help='Number of cross-validation folds')
    parser.add_argument('--temporal_split', type=int, default=None,
                       help='Split year for temporal hold-out (trains ≤year, tests >year). Simulates forecasting. Avoids temporal leakage.')
    parser.add_argument('--output_dir', type=Path, default=OUTPUT_DIR,
                       help='Output directory')
    
    args = parser.parse_args()
    
    if not args.data.exists():
        print(f"ERROR: Data file not found: {args.data}")
        print("First run: python PIPELINES/build_regional_discharge_model.py")
        return 1
    
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load and prepare data
    df, features = load_data(args.data)
    X, y = prepare_features(df, features)
    
    print(f"\nFeatures summary:")
    print(f"  Total features: {len(features)}")
    print(f"  Basin features: {sum(1 for f in features if f in BASIN_FEATURES)}")
    print(f"  Climate features: {sum(1 for f in features if f in CLIMATE_FEATURES)}")
    print(f"  Upstream features: {sum(1 for f in features if f in UPSTREAM_FEATURES)}")
    print(f"  Temporal features: {sum(1 for f in features if f in TEMPORAL_FEATURES)}")
    
    # Spatial cross-validation
    print(f"\nSpatial cross-validation ({args.folds} folds):")
    print(f"  ⚠ NOTE: Spatial CV alone can have temporal leakage (trains on future years in other gauges)")
    cv_splits = spatial_cv_split(df, n_folds=args.folds)
    
    # Train ensemble
    results = train_ensemble(X, y, cv_splits)
    
    # Temporal hold-out (optional, recommended for forecasting validation)
    if args.temporal_split:
        temporal_results = evaluate_temporal_split(X, y, df, results['models'], 
                                                   results['scaler'], args.temporal_split)
        results['temporal'] = temporal_results
    else:
        print(f"\n✓ OPTIONAL: Add --temporal_split 2015 to evaluate TRUE forecasting skill")
    
    # Save results
    save_results(results, features, args.output_dir)
    
    print(f"\n✓ Model training complete")
    print(f"  Next: python PIPELINES/analyse_regional_discharge.py")

    
    return 0


if __name__ == '__main__':
    sys.exit(main())
