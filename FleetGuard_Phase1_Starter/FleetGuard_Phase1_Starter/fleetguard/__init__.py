"""FleetGuard compatibility module (aliases to flairguard)."""
from flairguard import *
from flairguard.data import COLUMNS, read_trajectories, read_test_end_rul, load_subset, add_train_rul, last_cycle_of_each_engine
from flairguard.features import add_causal_features
from flairguard.metrics import regression_metrics
