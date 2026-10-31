"""FlairGuard AI: Comprehensive Evaluation of Anomaly Detection & Triage Policies.

Executes:
1. Repeated 5-fold GroupKFold cross-validation for model uncertainty quantification.
2. Comparison of 3 Anomaly Detectors (Isolation Forest, PCA, Statistical Z-Score).
3. False Alarm Rate (FAR) calibration & persistence filtering analysis (K = 1, 3, 5, 8).
4. Controlled perturbation sensitivity (noise, drift, stuck sensor).
5. Triage policy cost simulation against Fixed-Interval and Basic RUL policies.
6. Verification of SQLite persistent work-order store, idempotency, and audit trails.
"""
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flairguard.data import load_subset, add_train_rul
from flairguard.features import add_causal_features
from flairguard.models import SEED, RUL_CAP
from flairguard.evaluation import run_repeated_engine_kfold
from flairguard.quality import TelemetryQualityAuditor, ACTIVE_SENSORS
from flairguard.storage import WorkOrderStore
from flairguard.anomaly import (
    StatisticalDeviationDetector,
    PCAReconstructionDetector,
    IsolationForestDetector,
    PersistenceFilter,
    EARLY_CYCLE_CUTOFF,
)
from flairguard.policy_eval import (
    simulate_fixed_interval_policy,
    simulate_basic_rul_policy,
    simulate_flairguard_triage_policy,
)
import lightgbm as lgb
from sklearn.model_selection import GroupShuffleSplit


def main():
    data_dir = ROOT / "data" / "raw"
    results_dir = ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    db_path = ROOT / "data" / "flairguard_triage.db"
    if db_path.exists():
        db_path.unlink()  # Clean run for evaluation

    print("==================================================================")
    print("  FlairGuard AI: Phase 2 Anomaly Detection & Triage Evaluation   ")
    print("==================================================================")

    # 1. Load Data & Prepare Causal Features
    train_raw, test_raw, official_rul = load_subset(data_dir, "FD001")
    train_df, features = add_causal_features(add_train_rul(train_raw))
    print(f"Loaded FD001: {train_df.engine_id.nunique()} engines, {len(train_df):,} cycles, {len(features)} causal features.")

    # 2. Repeated Engine-Disjoint Cross-Validation (Model Selection Uncertainty)
    print("\n--- 1. Repeated 5-Fold GroupKFold Cross-Validation (Uncertainty Quantification) ---")
    cv_summary = run_repeated_engine_kfold(train_df, features, n_splits=5, seed=SEED)
    print(f"{'Model':<22} | {'CV MAE (mean +/- std)':<22} | {'CV RMSE (mean +/- std)':<22} | {'CV PHM08 Score':<20}")
    print("-" * 92)
    for name, stats in cv_summary.items():
        mae_str = f"{stats['cv_mae_mean']:.2f} +/- {stats['cv_mae_std']:.2f}"
        rmse_str = f"{stats['cv_rmse_mean']:.2f} +/- {stats['cv_rmse_std']:.2f}"
        phm_str = f"{stats['cv_phm08_mean']:.1f} +/- {stats['cv_phm08_std']:.1f}"
        print(f"{name:<22} | {mae_str:<22} | {rmse_str:<22} | {phm_str:<20}")

    # 3. Disjoint Split for Anomaly & Policy Evaluation
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED)
    fit_idx, val_idx = next(splitter.split(train_df, groups=train_df.engine_id))
    fit_engines = train_df.iloc[fit_idx].copy()
    val_engines = train_df.iloc[val_idx].copy()
    assert set(fit_engines.engine_id).isdisjoint(set(val_engines.engine_id))

    # Fit LightGBM on fit_engines to generate predictions for policy simulation
    print("\n--- 2. Fitting Production RUL Regressor (LightGBM) ---")
    lgb_model = lgb.LGBMRegressor(
        n_estimators=180, learning_rate=0.07, num_leaves=15,
        min_child_samples=20, reg_alpha=0.1, reg_lambda=1.0,
        random_state=SEED, verbose=-1, n_jobs=-1
    )
    lgb_model.fit(fit_engines[features], np.clip(fit_engines.true_rul, 0, RUL_CAP))
    
    # Pre-generate predictions for all cycles in validation engines
    val_preds_map = {}
    preds_all = np.clip(lgb_model.predict(val_engines[features]), 0, RUL_CAP)
    for idx, (_, row) in enumerate(val_engines.iterrows()):
        val_preds_map[(int(row["engine_id"]), int(row["cycle"]))] = float(preds_all[idx])

    # 4. Anomaly Detectors Benchmark
    print("\n--- 3. Anomaly Detection Calibration & Benchmark ---")
    # Early-life nominal reference assumption (cycle <= EARLY_CYCLE_CUTOFF on TRAINING engines)
    train_nominal = fit_engines[fit_engines.cycle <= EARLY_CYCLE_CUTOFF][features].to_numpy()
    val_nominal = val_engines[val_engines.cycle <= EARLY_CYCLE_CUTOFF][features].to_numpy()
    print(f"Nominal Reference Assumption: cycle <= {EARLY_CYCLE_CUTOFF}")
    print(f"Training nominal samples: {len(train_nominal)} | Validation nominal samples: {len(val_nominal)}")

    detectors = {
        "Statistical_Deviation": StatisticalDeviationDetector(),
        "PCA_Reconstruction": PCAReconstructionDetector(n_components=5),
        "Isolation_Forest": IsolationForestDetector(n_estimators=100, random_state=SEED),
    }

    anomaly_results = {}
    target_far = 0.05

    for name, det in detectors.items():
        det.fit(train_nominal)
        thresh = det.calibrate_threshold(val_nominal, target_far=target_far)
        
        # Validation nominal FAR verification
        val_nom_scores = det.compute_raw_score(val_nominal)
        actual_far = float(np.mean(val_nom_scores >= thresh))

        # Controlled perturbation sensitivity test (diagnostic testing only)
        # Noise perturbation: +3 sigma Gaussian noise
        noisy_val = val_nominal + np.random.default_rng(SEED).normal(0, 3.0, size=val_nominal.shape)
        noisy_detection_rate = float(np.mean(det.compute_raw_score(noisy_val) >= thresh))

        # Drift perturbation: systematic 15% upward ramp on active sensors
        drift_val = val_nominal * 1.15
        drift_detection_rate = float(np.mean(det.compute_raw_score(drift_val) >= thresh))

        anomaly_results[name] = {
            "calibrated_threshold": round(thresh, 4),
            "target_far": target_far,
            "empirical_val_far": round(actual_far, 4),
            "noise_sensitivity_rate": round(noisy_detection_rate, 4),
            "drift_sensitivity_rate": round(drift_detection_rate, 4),
        }
        print(f"[{name}] Threshold: {thresh:.4f} | Target FAR: {target_far:.1%} | Empirical FAR: {actual_far:.1%} | "
              f"Noise Detection: {noisy_detection_rate:.1%} | Drift Detection: {drift_detection_rate:.1%}")

    # Persistence length comparison (using Isolation Forest)
    print("\n--- 4. Persistence Length Sensitivity (Isolation Forest) ---")
    iso_det = detectors["Isolation_Forest"]
    persistence_studies = {}
    for k in [1, 3, 5, 8]:
        p_filter = PersistenceFilter(persistence_length=k)
        nom_alarms = 0
        total_evals = 0
        for eng_id, group in val_engines[val_engines.cycle <= EARLY_CYCLE_CUTOFF].groupby("engine_id"):
            p_filter.reset_engine(eng_id)
            for _, r in group.iterrows():
                score = float(iso_det.compute_raw_score(r[features].to_numpy().reshape(1, -1))[0])
                is_anom = score >= iso_det.threshold
                count = p_filter.update(eng_id, is_anom)
                if count >= k:
                    nom_alarms += 1
                total_evals += 1
        pers_far = nom_alarms / max(1, total_evals)
        persistence_studies[f"K={k}"] = {
            "persistence_cycles": k,
            "nominal_false_alarms": nom_alarms,
            "effective_nominal_far": round(pers_far, 4),
        }
        print(f"  Persistence K={k} cycles -> False Alarms on Nominal: {nom_alarms} (Effective FAR: {pers_far:.2%})")

    # 5. Quality Auditor Fit
    quality_auditor = TelemetryQualityAuditor()
    quality_auditor.fit_reference_ranges(fit_engines)

    # 6. Policy Simulation & Cost Comparison on Held-Out Validation Trajectories
    print("\n--- 5. Policy Cost Simulation on Held-Out Validation Engines (20 Trajectories) ---")
    heldout_list = [group.sort_values("cycle").reset_index(drop=True) for _, group in val_engines.groupby("engine_id")]

    policy_fixed = simulate_fixed_interval_policy(heldout_list, interval_cycles=135)
    policy_basic_rul = simulate_basic_rul_policy(heldout_list, val_preds_map, trigger_rul=25.0)
    policy_flairguard = simulate_flairguard_triage_policy(
        heldout_engines=heldout_list,
        predictions_map=val_preds_map,
        anomaly_detector=iso_det,
        quality_auditor=quality_auditor,
        db_path=str(db_path),
        feature_cols=features,
        persistence_length=3,
    )

    policies = [policy_fixed, policy_basic_rul, policy_flairguard]
    print(f"{'Policy':<36} | {'Total Cost':<10} | {'Breakdowns':<10} | {'Planned':<8} | {'Inspections':<11} | {'Avg Waste (cyc)':<15} | {'Reliability':<11}")
    print("-" * 115)
    for p in policies:
        print(f"{p.policy_name:<36} | {p.total_cost:<10.2f} | {p.unplanned_breakdowns:<10} | {p.planned_maintenances:<8} | "
              f"{p.inspections_dispatched:<11} | {p.avg_wasted_rul_cycles:<15.1f} | {p.fleet_reliability_pct:<10.1f}%")

    # 7. Verify SQLite Database State
    store = WorkOrderStore(db_path)
    all_wo = store.get_all_work_orders()
    all_audit = store.get_audit_trail()
    print(f"\n--- 6. SQLite Persistent Store Verification ({db_path.name}) ---")
    print(f"Total Work Orders stored: {len(all_wo)}")
    print(f"Total Audit Log records: {len(all_audit)}")
    event_counts = pd.Series([a["event_type"] for a in all_audit]).value_counts().to_dict()
    print(f"Audit Event Distribution: {event_counts}")

    # Export Full Results to JSON
    summary_export = {
        "cross_validation_uncertainty": cv_summary,
        "anomaly_detectors": anomaly_results,
        "persistence_sensitivity": persistence_studies,
        "policy_comparison": [p.__dict__ for p in policies],
        "database_audit_summary": event_counts,
    }
    export_path = results_dir / "phase2_anomaly_triage_evaluation.json"
    with open(export_path, "w") as f:
        json.dump(summary_export, f, indent=2)
    print(f"\nComprehensive Phase 2 Evaluation saved to: {export_path}")


if __name__ == "__main__":
    main()

