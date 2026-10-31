"""FlairGuard AI: Comprehensive ML Benchmark across Ridge, Random Forest, HistGB, and LightGBM.

Evaluation Protocol:
1. Group-disjoint validation split (80 train engines / 20 validation engines).
2. Model comparison and selection conducted STRICTLY on held-out validation engines.
3. Final evaluation conducted on official NASA test set (100 engines, last cycle) once for reporting.
4. Metrics recorded: MAE, RMSE, and NASA PHM08 asymmetric score.
5. Exports results to JSON, CSV, and summary visualization plots.
"""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flairguard.data import load_subset, add_train_rul, last_cycle_of_each_engine
from flairguard.features import add_causal_features
from flairguard.metrics import regression_metrics
from flairguard.models import get_model_candidates, SEED, RUL_CAP
from sklearn.model_selection import GroupShuffleSplit


def get_validation_snapshots(df: pd.DataFrame, count_per_engine: int = 3, seed: int = SEED) -> pd.DataFrame:
    """Simulate real-time operational snapshots from held-out engines."""
    rng = np.random.default_rng(seed)
    parts = []
    for _, group in df.groupby("engine_id", sort=True):
        allowed = group[(group.cycle >= 20) & group.true_rul.between(5, RUL_CAP)]
        if allowed.empty:
            allowed = group
        indices = rng.choice(
            allowed.index.to_numpy(),
            size=min(count_per_engine, len(allowed)),
            replace=False
        )
        parts.append(df.loc[indices])
    return pd.concat(parts, ignore_index=True)


def plot_results(results_df: pd.DataFrame, test_predictions: dict, test_actual: np.ndarray, output_dir: Path):
    """Generate high-quality diagnostic and comparison charts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Bar Chart: Model Metrics Comparison
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    metrics = [
        ("test_mae", "MAE (cycles) - Lower is better", "#2b5c8f"),
        ("test_rmse", "RMSE (cycles) - Lower is better", "#d95f02"),
        ("test_phm08", "NASA PHM08 Score - Lower is better", "#7570b3"),
    ]
    
    for ax, (col, title, color) in zip(axes, metrics):
        bars = ax.bar(results_df["model"], results_df[col], color=color, alpha=0.85, edgecolor="black")
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_ylabel("Value", fontsize=11)
        ax.grid(axis="y", linestyle="--", alpha=0.6)
        ax.tick_params(axis="x", rotation=15)
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f"{height:.2f}",
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3), textcoords="offset points",
                        ha="center", va="bottom", fontsize=10, fontweight="bold")
            
    plt.suptitle("FlairGuard AI: Model Benchmark Comparison on NASA C-MAPSS FD001 (Test Set)", fontsize=14, fontweight="bold")
    plt.tight_layout()
    chart_path = output_dir / "benchmark_metrics_comparison.png"
    plt.savefig(chart_path, dpi=300)
    plt.close()
    
    # 2. Scatter & Line Plot: Predicted vs True RUL for Best Model vs Ridge
    fig, ax = plt.subplots(figsize=(12, 6))
    engine_indices = np.arange(1, len(test_actual) + 1)
    
    # Sort by actual RUL for clean visualization
    sort_idx = np.argsort(test_actual)
    sorted_actual = test_actual[sort_idx]
    
    ax.plot(range(len(sorted_actual)), sorted_actual, "k-", linewidth=2.5, label="Actual NASA RUL (Ground Truth)")
    
    colors = {"LightGBM": "#1f77b4", "HistGradientBoosting": "#ff7f0e", "Random Forest": "#2ca02c", "Ridge": "#d62728"}
    for name, preds in test_predictions.items():
        sorted_preds = preds[sort_idx]
        ax.plot(range(len(sorted_actual)), sorted_preds, "--", alpha=0.75, linewidth=1.8, label=f"Predicted ({name})", color=colors.get(name))
        
    ax.set_title("FlairGuard AI: Engine-by-Engine Test RUL Predictions (Sorted by True Life)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Test Engines (Ranked from Lowest to Highest True RUL)", fontsize=11)
    ax.set_ylabel("Remaining Useful Life (Cycles)", fontsize=11)
    ax.axhline(RUL_CAP, color="gray", linestyle=":", label=f"Training Target Cap ({RUL_CAP} cycles)")
    ax.legend(loc="upper left", framealpha=0.9)
    ax.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plot_path = output_dir / "test_rul_trajectories_comparison.png"
    plt.savefig(plot_path, dpi=300)
    plt.close()


def run_benchmark(data_dir: Path, subset: str = "FD001", output_dir: Path = None) -> dict:
    if output_dir is None:
        output_dir = ROOT / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"============================================================")
    print(f"  FlairGuard AI - Phase 2 Model Benchmarking ({subset})")
    print(f"============================================================")
    
    # 1. Load Data
    train_raw, test_raw, official_rul = load_subset(data_dir, subset)
    print(f"Loaded {subset}: {len(train_raw):,} train rows ({train_raw.engine_id.nunique()} engines), "
          f"{len(test_raw):,} test rows ({test_raw.engine_id.nunique()} engines).")
    
    # 2. Add Causal Rolling Features
    train_df, features = add_causal_features(add_train_rul(train_raw))
    test_df, _ = add_causal_features(test_raw)
    print(f"Engineered {len(features)} causal features (no lookahead leakage).")
    
    # 3. Disjoint Train/Validation Split by Engine ID
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED)
    fit_idx, valid_idx = next(splitter.split(train_df, groups=train_df.engine_id))
    fit_set = train_df.iloc[fit_idx]
    heldout = train_df.iloc[valid_idx]
    
    assert set(fit_set.engine_id).isdisjoint(set(heldout.engine_id)), "Engine ID leakage detected!"
    print(f"Disjoint Engine Split: {fit_set.engine_id.nunique()} train engines, {heldout.engine_id.nunique()} validation engines.")
    
    val_snapshots = get_validation_snapshots(heldout, count_per_engine=3, seed=SEED)
    print(f"Constructed {len(val_snapshots)} validation snapshots from held-out engines.")
    
    # Target clipping (piecewise linear target)
    y_fit = np.clip(fit_set.true_rul, 0, RUL_CAP)
    y_full_train = np.clip(train_df.true_rul, 0, RUL_CAP)
    
    # Last cycle of each test engine with ground truth
    last_test_rows = last_cycle_of_each_engine(test_df, official_rul)
    y_test_ground_truth = last_test_rows.true_rul.to_numpy()
    
    models = get_model_candidates(seed=SEED)
    benchmark_records = []
    test_predictions_dict = {}
    
    print("\n--- Running Model Evaluation ---")
    for name, model in models.items():
        print(f"\nEvaluating: {name}")
        
        # Phase A: Train on 80% engines, evaluate on 20% validation engines
        model.fit(fit_set[features], y_fit)
        val_pred = np.clip(model.predict(val_snapshots[features]), 0, RUL_CAP)
        val_metrics = regression_metrics(val_snapshots.true_rul, val_pred)
        print(f"  [Validation] MAE: {val_metrics['mae_cycles']} | RMSE: {val_metrics['rmse_cycles']} | PHM08: {val_metrics['phm08_score']}")
        
        # Phase B: Train on 100% training engines, single evaluation on official NASA test set
        # Retrain fresh instance
        final_model_instance = get_model_candidates(seed=SEED)[name]
        final_model_instance.fit(train_df[features], y_full_train)
        test_pred = np.clip(final_model_instance.predict(last_test_rows[features]), 0, RUL_CAP)
        test_metrics = regression_metrics(y_test_ground_truth, test_pred)
        test_predictions_dict[name] = test_pred
        print(f"  [Official Test] MAE: {test_metrics['mae_cycles']} | RMSE: {test_metrics['rmse_cycles']} | PHM08: {test_metrics['phm08_score']}")
        
        benchmark_records.append({
            "model": name,
            "subset": subset,
            "val_mae": val_metrics["mae_cycles"],
            "val_rmse": val_metrics["rmse_cycles"],
            "val_phm08": val_metrics["phm08_score"],
            "test_mae": test_metrics["mae_cycles"],
            "test_rmse": test_metrics["rmse_cycles"],
            "test_phm08": test_metrics["phm08_score"],
            "features_count": len(features),
            "rul_cap": RUL_CAP,
            "random_seed": SEED,
        })
        
    results_df = pd.DataFrame(benchmark_records)
    
    # Save CSV and JSON
    csv_path = output_dir / "benchmark_results.csv"
    json_path = output_dir / "benchmark_results.json"
    results_df.to_csv(csv_path, index=False)
    
    summary_dict = {
        "metadata": {
            "project": "FlairGuard AI",
            "subset": subset,
            "n_train_engines": int(train_df.engine_id.nunique()),
            "n_test_engines": int(test_df.engine_id.nunique()),
            "features_count": len(features),
            "rul_cap": RUL_CAP,
            "random_seed": SEED,
        },
        "results": benchmark_records
    }
    with open(json_path, "w") as f:
        json.dump(summary_dict, f, indent=2)
        
    # Generate diagnostic plots
    plot_results(results_df, test_predictions_dict, y_test_ground_truth, output_dir)
    print(f"\nArtifacts exported successfully to: {output_dir}")
    print(f"  - CSV: {csv_path.name}")
    print(f"  - JSON: {json_path.name}")
    print(f"  - Plots: benchmark_metrics_comparison.png, test_rul_trajectories_comparison.png")
    
    print("\n--- FINAL BENCHMARK RESULTS TABLE ---")
    display_df = results_df[["model", "test_mae", "test_rmse", "test_phm08"]].rename(
        columns={"test_mae": f"{subset} MAE", "test_rmse": f"{subset} RMSE", "test_phm08": "NASA Score"}
    )
    print(display_df.to_string(index=False))
    return summary_dict


def main():
    parser = argparse.ArgumentParser(description="FlairGuard Model Benchmark Runner")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "raw", help="Path to CMAPSS data")
    parser.add_argument("--subset", default="FD001", choices=["FD001", "FD002", "FD003", "FD004"])
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results", help="Directory to save benchmark results")
    args = parser.parse_args()
    
    run_benchmark(data_dir=args.data_dir, subset=args.subset, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
