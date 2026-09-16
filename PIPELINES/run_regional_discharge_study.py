#!/usr/bin/env python3
"""Master orchestration script for regional CA-discharge case study.

Runs complete workflow:
1. Assemble features from CA-discharge, climate, and station data
2. Train statistical ensemble model (with optional temporal hold-out validation)
3. Analyze predictions and generate case study report

⚠️  TEMPORAL LEAKAGE:
  By default, uses spatial CV which can have temporal leakage.
  Add --temporal_split 2015 to validate TRUE forecasting skill (no leakage).
  See: CASE_STUDIES/TEMPORAL_LEAKAGE_GUIDE.md

Usage:
    python PIPELINES/run_regional_discharge_study.py                          # Spatial CV only
    python PIPELINES/run_regional_discharge_study.py --temporal_split 2015    # + Forecasting validation
    python PIPELINES/run_regional_discharge_study.py --stages build,train     # Build & train only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]


def run_stage(stage_name: str, script: str, args: List[str] = None):
    """Run a pipeline stage as subprocess."""
    print(f"\n{'='*70}")
    print(f"STAGE: {stage_name.upper()}")
    print(f"{'='*70}")
    
    cmd = [sys.executable, str(ROOT / "PIPELINES" / script)]
    if args:
        cmd.extend(args)
    
    result = subprocess.run(cmd, cwd=ROOT)
    
    if result.returncode != 0:
        print(f"\n❌ Stage '{stage_name}' failed with exit code {result.returncode}")
        return False
    
    print(f"✓ Stage '{stage_name}' completed successfully")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stages', default='build,train,analyze',
                       help='Comma-separated stages to run: build,train,analyze')
    parser.add_argument('--min_years', type=int, default=10,
                       help='Minimum years of discharge data per gauge')
    parser.add_argument('--folds', type=int, default=5,
                       help='Cross-validation folds')
    parser.add_argument('--temporal_split', type=int, default=None,
                       help='Year to split for temporal hold-out (trains ≤year, tests >year). Validates forecasting skill without temporal leakage.')
    parser.add_argument('--output_dir', type=Path, default=ROOT / "PUBLISHED/data/case-studies",
                       help='Output directory')
    
    args = parser.parse_args()
    
    stages = [s.strip() for s in args.stages.split(',')]
    stages = [s for s in stages if s]  # Remove empty strings
    
    temporal_note = f" (with temporal hold-out at {args.temporal_split})" if args.temporal_split else ""
    
    print(f"""
╔═══════════════════════════════════════════════════════════════════════════╗
║     Regional CA-Discharge Monthly Modeling Case Study                     ║
║     Data Fusion: Basin Characteristics + Climate + Station Network       ║
╚═══════════════════════════════════════════════════════════════════════════╝

Configuration:
  Stages:       {', '.join(stages)}{temporal_note}
  Min years:    {args.min_years}
  CV folds:     {args.folds}
  Output dir:   {args.output_dir}

Expected runtime: ~4-6 hours total
  - Build features:    2-3 hours
  - Train model:       1-2 hours{' (+ temporal)' if args.temporal_split else ''}
  - Analyze:           30 minutes

⚠️  TEMPORAL LEAKAGE NOTE:
  Spatial CV alone can have temporal leakage (trains on future years in other gauges).
  Use --temporal_split 2015 to validate TRUE forecasting skill (no leakage).
  See: CASE_STUDIES/TEMPORAL_LEAKAGE_GUIDE.md
""")
    
    completed = []
    failed = False
    
    # Stage 1: Build feature matrix
    if 'build' in stages:
        success = run_stage(
            'Feature Assembly',
            'build_regional_discharge_model.py',
            ['--min_years', str(args.min_years), '--output_dir', str(args.output_dir)]
        )
        if success:
            completed.append('build')
        else:
            failed = True
    
    # Stage 2: Train ensemble
    if 'train' in stages and not failed:
        train_args = ['--folds', str(args.folds), '--output_dir', str(args.output_dir)]
        if args.temporal_split:
            train_args.extend(['--temporal_split', str(args.temporal_split)])
        
        success = run_stage(
            'Ensemble Training',
            'train_discharge_ensemble.py',
            train_args
        )
        if success:
            completed.append('train')
        else:
            failed = True
    
    # Stage 3: Analyze results
    if 'analyze' in stages and not failed:
        success = run_stage(
            'Results Analysis',
            'analyse_regional_discharge.py',
            ['--output_dir', str(args.output_dir)]
        )
        if success:
            completed.append('analyze')
        else:
            failed = True
    
    # Summary
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"Completed stages: {', '.join(completed)}")
    
    if failed:
        print(f"\n❌ Workflow stopped due to error")
        return 1
    
    if len(completed) == len(stages):
        print(f"\n✓ All stages completed successfully!")
        print(f"\nGenerated outputs:")
        print(f"  - {args.output_dir}/regional_discharge_data.csv")
        print(f"  - {args.output_dir}/discharge_ensemble_model.pkl")
        print(f"  - {args.output_dir}/discharge_feature_importance.csv")
        print(f"  - {args.output_dir}/regional_discharge_predictions.csv")
        print(f"  - {args.output_dir}/regional_discharge_gauge_skill.csv")
        print(f"  - {args.output_dir}/regional_discharge_case_study.md")
        print(f"\nNext steps:")
        print(f"  1. Review case study: {args.output_dir}/regional_discharge_case_study.md")
        print(f"  2. Validate predictions in Excel/Python with regional_discharge_predictions.csv")
        print(f"  3. Integrate gauge modal predictions into landing page")
        return 0
    else:
        print(f"\n⚠ Only {len(completed)} of {len(stages)} stages completed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
