"""Input validation and NASA C-MAPSS RUL ground truth management for FlairGuard AI."""
from pathlib import Path
import numpy as np
import pandas as pd

COLUMNS = (
    ["engine_id", "cycle"]
    + [f"setting_{i}" for i in range(1, 4)]
    + [f"sensor_{i}" for i in range(1, 22)]
)


def read_trajectories(path: str | Path) -> pd.DataFrame:
    """Read whitespace-delimited NASA C-MAPSS trajectory file and validate schema."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Missing NASA trajectory file: {path}")
    df = pd.read_csv(path, sep=r"\s+", header=None)
    if df.shape[1] != 26:
        raise ValueError(f"Expected 26 columns in {path.name}; got {df.shape[1]}")
    df.columns = COLUMNS
    if df.isna().any().any() or not np.isfinite(df.to_numpy(dtype=float)).all():
        raise ValueError(f"Non-finite/missing source values in {path.name}")
    for col in ("engine_id", "cycle"):
        if (df[col] != df[col].astype(int)).any():
            raise ValueError(f"{col} should contain integers")
        df[col] = df[col].astype(int)
    if (df["engine_id"] <= 0).any() or (df["cycle"] <= 0).any():
        raise ValueError("Engine IDs and cycle numbers must be positive")
    if df.duplicated(["engine_id", "cycle"]).any():
        raise ValueError("Duplicate (engine_id, cycle) rows")
    df = df.sort_values(["engine_id", "cycle"]).reset_index(drop=True)
    for engine_id, group in df.groupby("engine_id", sort=False):
        expected = np.arange(1, len(group) + 1)
        if not np.array_equal(group["cycle"].to_numpy(), expected):
            raise ValueError(f"Non-consecutive cycles in engine {engine_id}")
    return df


def read_test_end_rul(path: str | Path) -> np.ndarray:
    """Read official test-end ground truth RUL values."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Missing official test RUL file: {path}")
    values = pd.read_csv(path, sep=r"\s+", header=None).to_numpy()
    if values.ndim != 2 or values.shape[1] != 1:
        raise ValueError("Official test RUL should contain exactly one column")
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Official RUL values must be finite and non-negative")
    return values[:, 0].astype(float)


def load_subset(data_dir: str | Path, subset: str = "FD001") -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    """Load train, test, and official test RUL arrays for a chosen C-MAPSS subset."""
    if subset not in {"FD001", "FD002", "FD003", "FD004"}:
        raise ValueError("Subset must be FD001, FD002, FD003 or FD004")
    data_dir = Path(data_dir)
    train = read_trajectories(data_dir / f"train_{subset}.txt")
    test = read_trajectories(data_dir / f"test_{subset}.txt")
    test_rul = read_test_end_rul(data_dir / f"RUL_{subset}.txt")
    if len(test_rul) != test.engine_id.nunique():
        raise ValueError("Official test RUL count does not match the number of test engines")
    return train, test, test_rul


def add_train_rul(train: pd.DataFrame) -> pd.DataFrame:
    """Compute exact remaining useful life for run-to-failure training engines."""
    result = train.copy()
    end = result.groupby("engine_id")["cycle"].transform("max")
    result["true_rul"] = (end - result["cycle"]).astype(int)
    return result


def last_cycle_of_each_engine(test: pd.DataFrame, test_rul: np.ndarray) -> pd.DataFrame:
    """Apply official RUL labels ONLY to the last observed test cycle per engine.
    
    Prevents false intermediate labeling and respects NASA benchmark protocol.
    """
    last = test.groupby("engine_id", sort=True).tail(1).sort_values("engine_id").copy()
    if len(last) != len(test_rul):
        raise ValueError("RUL alignment failed")
    last["true_rul"] = test_rul
    return last

