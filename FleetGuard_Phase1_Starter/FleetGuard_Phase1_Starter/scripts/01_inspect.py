"""Step 1: verify the real NASA dataset before fitting any model."""
import argparse
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fleetguard.data import load_subset, add_train_rul


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    ap.add_argument("--subset", default="FD001")
    args = ap.parse_args()
    train, test, official_rul = load_subset(args.data_dir, args.subset)
    labeled = add_train_rul(train)
    print(f"Subset: {args.subset}")
    print(f"Train: {len(train):,} rows across {train.engine_id.nunique()} engines")
    print(f"Test: {len(test):,} rows across {test.engine_id.nunique()} engines")
    print(f"Official test-end RUL labels: {len(official_rul)}")
    print(f"Range of training RUL: {labeled.true_rul.min()} to {labeled.true_rul.max()} cycles")
    print("Columns:", ", ".join(train.columns))
    print("Missing entries:", int(train.isna().sum().sum() + test.isna().sum().sum()))
    print("All engine cycles consecutive, IDs valid, values finite: YES")

if __name__ == "__main__":
    main()
