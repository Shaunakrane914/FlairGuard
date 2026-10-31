import numpy as np
import pandas as pd
import pytest
from fleetguard.data import COLUMNS, add_train_rul, last_cycle_of_each_engine
from fleetguard.features import add_causal_features
from fleetguard.metrics import regression_metrics


def fixture_rows():
    rows=[]
    for engine, count in [(1,4), (2,5)]:
        for cycle in range(1, count+1):
            row=dict(zip(COLUMNS, [engine,cycle,0,0,0]+[cycle*2+i for i in range(21)]))
            rows.append(row)
    return pd.DataFrame(rows)


def test_train_rul_for_run_to_failure_engines():
    df=add_train_rul(fixture_rows())
    assert df[df.engine_id==1].true_rul.tolist()==[3,2,1,0]
    assert df[df.engine_id==2].true_rul.tolist()==[4,3,2,1,0]


def test_official_test_rul_only_last_rows():
    end=last_cycle_of_each_engine(fixture_rows(), np.array([13,25]))
    assert len(end)==2
    assert end.sort_values("engine_id").true_rul.tolist()==[13,25]
    assert end.sort_values("engine_id").cycle.tolist()==[4,5]


def test_features_are_causal():
    original=fixture_rows()
    feature_a, cols=add_causal_features(original)
    changed=original.copy()
    changed.loc[(changed.engine_id==1)&(changed.cycle==4),"sensor_1"] = 9999
    feature_b, _=add_causal_features(changed)
    before_a=feature_a.loc[(feature_a.engine_id==1)&(feature_a.cycle==3), cols].iloc[0]
    before_b=feature_b.loc[(feature_b.engine_id==1)&(feature_b.cycle==3), cols].iloc[0]
    pd.testing.assert_series_equal(before_a,before_b)


def test_metrics_truth():
    metrics=regression_metrics([10,20],[12,18])
    assert metrics["mae_cycles"]==2
    assert metrics["rmse_cycles"]==2
