"""Input validation and correct C-MAPSS RUL labels (FleetGuard compatibility alias)."""
from flairguard.data import (
    COLUMNS,
    read_trajectories,
    read_test_end_rul,
    load_subset,
    add_train_rul,
    last_cycle_of_each_engine,
)

__all__ = [
    "COLUMNS",
    "read_trajectories",
    "read_test_end_rul",
    "load_subset",
    "add_train_rul",
    "last_cycle_of_each_engine",
]
