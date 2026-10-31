"""Read-only forensic probes; all outputs belong to this new review directory."""
from pathlib import Path
import hashlib
import importlib.metadata as metadata
import json
import sqlite3
import sys
import tempfile
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[2]
PROJECT = WORKSPACE / 'FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter'
sys.path.insert(0, str(PROJECT))
sys.dont_write_bytecode = True
from flairguard.data import load_subset, add_train_rul
from flairguard.features import add_causal_features
from flairguard.quality import TelemetryQualityAuditor, ACTIVE_SENSORS, QualityAssessment
from flairguard.storage import WorkOrderStore
from flairguard.triage import RiskAwareTriageAgent
from flairguard.anomaly import StatisticalDeviationDetector, PCAReconstructionDetector, IsolationForestDetector
from flairguard.metrics import regression_metrics

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

inventory = []
for p in WORKSPACE.rglob('*'):
    if p.is_file() and 'docs' != p.relative_to(WORKSPACE).parts[0]:
        inventory.append({'path':str(p.relative_to(WORKSPACE)), 'bytes':p.stat().st_size,
                          'sha256':sha(p), 'mtime_ns':p.stat().st_mtime_ns})
(HERE/'original_file_inventory.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')

report = {'project': str(PROJECT), 'python':sys.version,
          'packages':{p:metadata.version(p) for p in ['numpy','pandas','scikit-learn','lightgbm','pytest','scipy','matplotlib','fastapi']},
          'subsets':{}, 'duplicate_data_hashes':{}, 'database':{}, 'diagnostic_probes':{}}
for subset in ['FD001','FD002','FD003','FD004']:
    train,test,rul = load_subset(PROJECT/'data/raw',subset)
    report['subsets'][subset] = {
        'train_rows':len(train), 'test_rows':len(test), 'train_engines':train.engine_id.nunique(),
        'test_engines':test.engine_id.nunique(), 'test_rul_min':float(rul.min()), 'test_rul_max':float(rul.max()),
        'test_rul_above_125':int((rul>125).sum()),
        'train_life_min':int(train.groupby('engine_id').cycle.max().min()),
        'train_life_max':int(train.groupby('engine_id').cycle.max().max()),
        'constant_train_columns':list(train.columns[train.nunique()==1]),
        'consecutive_test_engine_ids':bool(np.array_equal(np.sort(test.engine_id.unique()),np.arange(1,len(rul)+1))),
    }
for p in (PROJECT/'data/raw').iterdir():
    other = WORKSPACE/'FleetGuard_Phase1_Starter/CMAPSSData'/p.name
    if p.is_file() and other.exists(): report['duplicate_data_hashes'][p.name] = sha(p)==sha(other)

db = PROJECT/'data/flairguard_triage.db'
with sqlite3.connect(db.as_uri()+'?mode=ro', uri=True) as c:
    c.row_factory=sqlite3.Row
    report['database']['schema']=[dict(x) for x in c.execute("select name,sql from sqlite_master where type in ('table','index')")]
    report['database']['work_orders']=[dict(x) for x in c.execute('select * from work_orders order by engine_id')]
    report['database']['event_counts']=[dict(x) for x in c.execute('select event_type,count(*) as count from audit_log group by event_type')]
    report['database']['event_cycle_ranges']=[dict(x) for x in c.execute('select engine_id,min(cycle) as first_cycle,max(cycle) as last_cycle,count(*) as events from audit_log group by engine_id')]
    report['database']['integrity']=[list(x) for x in c.execute('pragma integrity_check')]
    report['database']['foreign_keys_enabled']=c.execute('pragma foreign_keys').fetchone()[0]

saved = json.loads((PROJECT/'results/phase2_anomaly_triage_evaluation.json').read_text())
report['cv_summary_recomputed']={}
for name, row in saved['cross_validation_uncertainty'].items():
    report['cv_summary_recomputed'][name]={metric:{'mean':float(np.mean(values)),'population_std':float(np.std(values))}
                                                 for metric,values in row['raw_folds'].items()}
h = np.array(saved['cross_validation_uncertainty']['HistGradientBoosting']['raw_folds']['rmse'])
l = np.array(saved['cross_validation_uncertainty']['LightGBM']['raw_folds']['rmse'])
report['cv_paired_rmse_difference_lgb_minus_hist']={'fold_differences':(l-h).tolist(), 'mean':float((l-h).mean()),
                                                  'folds_lgb_lower':int((l<h).sum())}
report['metric_probe']={'implemented':regression_metrics([10,20],[12,18]),
                        'independent_phm08':float(np.expm1(2/10)+np.expm1(2/13))}

train,_,_=load_subset(PROJECT/'data/raw','FD001')
featured,features=add_causal_features(add_train_rul(train))
i,j=next(GroupShuffleSplit(n_splits=1,test_size=.2,random_state=42).split(featured,groups=featured.engine_id))
fit=featured.iloc[i]; val=featured.iloc[j]
report['split']={'fit_engines':sorted(map(int,fit.engine_id.unique())), 'validation_engines':sorted(map(int,val.engine_id.unique())),
                 'validation_min_life':int(val.groupby('engine_id').cycle.max().min()), 'features':features}
nominal_fit=fit[fit.cycle<=20][features].to_numpy()
nominal_val=val[val.cycle<=20][features].to_numpy()
report['diagnostic_probes']['anomaly_recalculation']={}
for name,det in [('zscore',StatisticalDeviationDetector()),('pca',PCAReconstructionDetector(5)),('iforest',IsolationForestDetector(100,42))]:
    det.fit(nominal_fit); threshold=det.calibrate_threshold(nominal_val,.05)
    noisy=nominal_val+np.random.default_rng(42).normal(0,3,size=nominal_val.shape)
    scaled=nominal_val*1.15
    cycle_shift=nominal_val.copy();cycle_shift[:,features.index('cycle')]+=100
    stats={'threshold':threshold, 'same_sample_far':float(np.mean(det.compute_raw_score(nominal_val)>=threshold)),
           'original_noise_rate':float(np.mean(det.compute_raw_score(noisy)>=threshold)),
           'original_scale_rate':float(np.mean(det.compute_raw_score(scaled)>=threshold)),
           'only_cycle_plus_100_rate':float(np.mean(det.compute_raw_score(cycle_shift)>=threshold)),
           'all_validation_cycles_alarm_fraction':float(np.mean(det.compute_raw_score(val[features].to_numpy())>=threshold))}
    report['diagnostic_probes']['anomaly_recalculation'][name]=stats
report['diagnostic_probes']['absolute_noise_sensor_equivalents']={s:float(3/fit.loc[fit.cycle<=20,s].std(ddof=0))
                                                                  for s in ACTIVE_SENSORS}

with tempfile.TemporaryDirectory(prefix='flairguard-audit-') as d:
    store=WorkOrderStore(Path(d)/'probe.db'); agent=RiskAwareTriageAgent(store)
    common={'engine_id':1,'uncertainty':15.,'anomaly_score':.8,'persistence_count':5}
    a=agent.evaluate(cycle=1,predicted_rul=75.,quality=QualityAssessment(True,'NOMINAL',{}),**common)
    b=agent.evaluate(cycle=2,predicted_rul=10.,quality=QualityAssessment(True,'NOMINAL',{}),**common)
    report['diagnostic_probes']['human_to_critical']={'first_decision':a.__dict__,'second_decision':b.__dict__,
                                                   'stored_order':store.get_active_work_order(1)}
    agent.evaluate(cycle=2,predicted_rul=10.,quality=QualityAssessment(True,'NOMINAL',{}),**common)
    report['diagnostic_probes']['same_event_replay_audit_count']=len(store.get_audit_trail(1))
    store.close_work_order(a.work_order_id)
    try:
        agent.evaluate(cycle=1,predicted_rul=75.,quality=QualityAssessment(True,'NOMINAL',{}),**common)
    except Exception as e: report['diagnostic_probes']['closed_order_replay_exception']=type(e).__name__+': '+str(e)

q=TelemetryQualityAuditor(stuck_window=5)
qresults=[]
for cycle in range(1,6):
    # All channels change, but one channel changes within np.allclose's default relative tolerance.
    values={s:100+cycle for s in ACTIVE_SENSORS}; values['sensor_8']=2388+cycle*.001
    qresults.append(q.audit_row(9,cycle,values).__dict__)
report['diagnostic_probes']['changing_sensor_false_stuck']=qresults[-1]
q=TelemetryQualityAuditor()
values={s:float(train.iloc[0][s]) for s in ACTIVE_SENSORS}
values.pop('sensor_2')
report['diagnostic_probes']['missing_key_assessment']=q.audit_row(1,1,values).__dict__
q=TelemetryQualityAuditor()
full={s:float(train.iloc[0][s]) for s in ACTIVE_SENSORS}
q.audit_row(1,1,full); q.audit_row(1,3,full)
report['diagnostic_probes']['gap_then_next_assessment']=q.audit_row(1,4,full).__dict__
(HERE/'workspace_findings.json').write_text(json.dumps(report,indent=2,default=lambda x:int(x) if isinstance(x,np.integer) else float(x)),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ['database','split','packages','cv_summary_recomputed']},indent=2))
print('Database counts:',report['database']['event_counts'])
print('Work-order severities:',pd.Series([x['severity'] for x in report['database']['work_orders']]).value_counts().to_dict())
print('Validation engines:',report['split']['validation_engines'])
