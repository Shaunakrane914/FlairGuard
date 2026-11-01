"""Freeze actual model lineage and bounded Phase D design before running comparisons."""
import json
from pathlib import Path
import joblib
from flairguard.evidence import file_sha
from flairguard.serving import predictor_fit_engines


def load_predictor(project, subset):
    project = Path(project)
    if subset in ('FD001','FD002'):
        folder = project/'artifacts'/('phase_a/fd001-v1-run002' if subset=='FD001' else 'phase_b/fd002-v1-run002')
        path = folder/'models/bundle.joblib'
        bundle = joblib.load(path)
        protocol = json.loads((folder/'protocol.json').read_text())
        preprocessing = predictor_fit_engines(bundle)
    else:
        folder = project/'artifacts/coverage_study/run001'/subset
        path = folder/'RegimeLightGBM.joblib'
        model = joblib.load(path)
        protocol = json.loads((folder/'protocol.json').read_text())
        bundle = dict(models={'RegimeLightGBM':model}, selected='RegimeLightGBM',
                      model_id='coverage-'+subset+'-RegimeLightGBM',rul_cap=125,min_history=20)
        preprocessing = model.features_.fit_engines_
    fit = predictor_fit_engines(bundle)
    roles = protocol['partitions']
    evaluation = roles['evaluation']
    development = roles.get('policy_dev',roles.get('development',roles.get('calibration')))
    if set(evaluation+development) & set(fit+preprocessing):
        raise ValueError('Predictor or preprocessing fit/evaluation overlap')
    lineage = dict(predictor_fit=fit,preprocessing_fit=list(map(int,preprocessing)),
        calibration=roles.get('calibration',[]),historical_roles=roles,
        model_selection='Fit-only OOF for Phase A/B; fixed comparator for coverage study',
        historical_evaluation=evaluation,development=development,evaluation=evaluation,
        source_artifact=str(path.relative_to(project)),sha256=file_sha(path),
        history='All supplied data historically exposed; retrospective development only')
    bundle['artifact_sha256'] = file_sha(path)
    return bundle,lineage,protocol


def freeze(project):
    lineage = {ds:load_predictor(project,ds)[1] for ds in ('FD001','FD002','FD003','FD004')}
    dev4 = lineage['FD004']['development']
    return dict(protocol_id='phase-d-reliability-v1',seed=2026110104,
        scope='Retrospective/developmental; no fresh confirmation or champion promotion',lineage=lineage,
        risk=dict(subset='FD004',target='Failure within next 15 operating cycles',horizon=15,
            oof_folds=3,calibration_engines=dev4[::2],policy_development_engines=dev4[1::2],
            thresholds=[0.1,0.25,0.5,0.75],review_budgets=[0.05,0.1,0.2],
            models=['conservative','slope','staleness','logistic','boosted','residual_cdf'],
            acceptance='>=5% cost improvement versus tuned point, engine bootstrap upper cost difference <0, no additional failed engines; otherwise no promotion'),
        tuning=dict(point_thresholds=[10,20,30,40],fixed_ages=[100,140,180,220],
            conservative_thresholds=[20,30,40,50],stale_limits=[0,5,20],
            criterion='minimum development mean cost; ties prefer simpler/lower threshold'),
        scenarios=[dict(name='clean',kind='clean',onset=0,duration=0,channels=[]),
            dict(name='single_reading',kind='missing',onset=120,duration=1,channels=['sensor_8']),
            dict(name='multi_short',kind='missing',onset=140,duration=5,channels=['sensor_8','sensor_11','sensor_15']),
            dict(name='packet_20',kind='packet',onset=140,duration=20,channels='all'),
            dict(name='packet_40',kind='packet',onset=180,duration=40,channels='all'),
            dict(name='causal_trigger',kind='trigger',onset=None,duration=20,channels=['sensor_8']),
            dict(name='delayed_10',kind='delay',onset=140,duration=20,channels='all',delay=10),
            dict(name='regime_outage',kind='regime',onset=100,duration=10,channels=['sensor_8','sensor_11'])],
        recovery=['abstain','bounded_last','forward_fill','regime_impute','missing_aware','decision_fallback'],
        policies=['none','fixed','FCFS','EDF','point','conservative','margin','lookahead'],
        conditions=[dict(name='reference',bays=3,technicians=3,duration=4,lead=1,offset=0,fleet_limit=None),
            dict(name='congested',bays=1,technicians=1,duration=8,lead=2,offset=0,fleet_limit=None),
            dict(name='staggered',bays=2,technicians=1,duration=4,lead=2,offset=15,fleet_limit=20)],
        review=dict(capacity=1,delay=2,accuracy='uninformative; completed review authorizes conservative replacement'),
        costs=dict(failure=10.,service=1.,waste=.05,delay=.1,downtime=.05,inspection=.2),
        sensitivities=dict(failure=[5.,10.,20.],waste=[.01,.05,.1]),
        bootstrap=dict(replicates=1000,unit='engine; average repeated conditions/scenarios within each engine first'),
        clock='global tick = local operating cycle + fixed engine offset; all clocks age through queue and service',
        repair='First completion or failure ends engine episode; no post-repair trajectory',
        boundary='Failure wins completion ties; no prediction using terminal failure row',
        precision='CSV %.17g, raw and clipped point outputs, scorer-only true labels')
