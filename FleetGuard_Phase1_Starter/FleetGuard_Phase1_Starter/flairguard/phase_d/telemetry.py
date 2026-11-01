"""Causal corruptions, recovery and saved-model inference; no outcome-label access."""
import hashlib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from flairguard.regimes import OBSERVATIONS, observations_only
from flairguard.quality import TELEMETRY_CHANNELS, ACTIVE_SENSORS
from flairguard.features import add_causal_features


def frame_hash(frame):
    return hashlib.sha256(frame.to_csv(index=False,float_format='%.17g').encode()).hexdigest()


def corrupt(raw,scenario,seed,clean_stream=None,reference=None):
    observations_only(raw)
    changed=raw.copy(deep=True)
    records=[]
    regimes=reference.assign(raw)[0] if reference is not None else np.zeros(len(raw),dtype=int)
    for eid,positions in raw.groupby('engine_id',sort=False).indices.items():
        group=raw.iloc[positions];onset=scenario['onset'];kind=scenario['kind']
        if kind=='clean':continue
        if kind=='trigger':
            if clean_stream is None:raise ValueError('Trigger requires causal forecasts')
            candidate=clean_stream.loc[(clean_stream.engine_id==eid)&(clean_stream.cycle>=20)&(clean_stream.prediction<=40)]
            onset=int(candidate.cycle.iloc[0])+1 if len(candidate) else None
        if kind=='regime':
            rg=regimes[positions]
            candidates=np.flatnonzero((group.cycle.to_numpy()>=100)&np.r_[False,rg[1:]!=rg[:-1]])
            onset=int(group.iloc[candidates[0]].cycle) if len(candidates) else None
        channels=TELEMETRY_CHANNELS if scenario['channels']=='all' else scenario['channels']
        indices=group.index[group.cycle.between(onset,onset+scenario['duration']-1)] if onset else []
        changed.loc[indices,channels]=np.nan
        records.append(dict(engine_id=int(eid),scenario=scenario['name'],version='phase-d-corruption-v1',
            onset=onset,duration=scenario['duration'],observed_affected_rows=len(indices),channels=list(channels),
            seed=seed+int(eid),delay=scenario.get('delay',0),
            delay_handling='Late timestamped packets are rejected from current-cycle state; do not relabel them as current' if kind=='delay' else None,
            original_hash=frame_hash(group),modified_hash=frame_hash(changed.loc[group.index])))
    return changed,records


def fit_reference(bundle,fit_raw):
    observations_only(fit_raw)
    references={key:float(fit_raw[key].median()) for key in TELEMETRY_CHANNELS}
    return references


def impute(raw,reference,regime=False,bundle=None,limit=5):
    """Bounded past-only fill; regime sensor fallback uses fit-derived means only."""
    filled=raw.copy()
    for key in TELEMETRY_CHANNELS:
        filled[key]=raw.groupby('engine_id')[key].ffill(limit=limit)
    if regime and 'models' in bundle:
        features=bundle['models'][bundle['selected']].features_
        labels,_=features.assign(filled)
        # Missing settings cannot reveal a new regime. Reuse bounded observed settings only.
        for j,key in enumerate(ACTIVE_SENSORS):
            mask=filled[key].isna() & (labels>=0)
            filled.loc[mask,key]=features.means_[labels[mask],j]
    return filled


def predict_frame(bundle,raw):
    observations_only(raw)
    if 'models' in bundle:
        values,diag=bundle['models'][bundle['selected']].predict(raw)
        regime=diag.regime.to_numpy()
    else:
        # A clean model is never given made-up zero values. The safe filler here only
        # enables batch computation; availability separately masks every affected window.
        safe=raw.copy()
        safe[TELEMETRY_CHANNELS]=safe[TELEMETRY_CHANNELS].fillna(0.)
        features,_=add_causal_features(safe)
        values=bundle['model'].predict(features[bundle['features']].round(10))
        regime=np.zeros(len(raw),dtype=int)
    return np.asarray(values,dtype=float),regime


class MissingAwareModel:
    """Fit-only augmented model, explicit masks and bounded stale inputs."""
    def __init__(self,bundle):self.bundle=bundle
    def matrix(self,raw):
        filled=impute(raw,self.reference_,limit=20)
        filled[TELEMETRY_CHANNELS]=filled[TELEMETRY_CHANNELS].fillna(self.reference_)
        if 'models' in self.bundle:
            X,_=self.bundle['models'][self.bundle['selected']].features_.transform(filled)
        else:X,_=add_causal_features(filled);X=X[self.bundle['features']]
        for key in TELEMETRY_CHANNELS:X['missing_'+key]=raw[key].isna().astype(float).to_numpy()
        return X.fillna(0.).round(10)
    def fit(self,raw,truth,seed):
        observations_only(raw)
        self.fit_engines_=sorted(map(int,raw.engine_id.unique()))
        self.reference_=fit_reference(self.bundle,raw)
        augmented=raw.copy()
        rng=np.random.default_rng(seed)
        for _,positions in augmented.groupby('engine_id').indices.items():
            # Fixed usage-time corruptions, independent of eventual failure/RUL.
            for onset,duration in [(60,5),(120,20),(180,10)]:
                pos=positions[(augmented.iloc[positions].cycle.to_numpy()>=onset)&(augmented.iloc[positions].cycle.to_numpy()<onset+duration)]
                channels=list(rng.choice(TELEMETRY_CHANNELS,size=3,replace=False))
                augmented.loc[pos,channels]=np.nan
        X=pd.concat([self.matrix(raw),self.matrix(augmented)],ignore_index=True)
        y=np.tile(np.clip(np.asarray(truth),0,125),2)
        self.model_=LGBMRegressor(n_estimators=120,num_leaves=15,learning_rate=.07,
            random_state=seed,n_jobs=2,verbosity=-1)
        self.model_.fit(X,y)
        return self
    def predict(self,raw):return self.model_.predict(self.matrix(raw))


def prediction_stream(bundle,raw,strategy='abstain',reference=None,missing_model=None,stale_limit=20):
    observations_only(raw)
    finite=np.isfinite(raw[TELEMETRY_CHANNELS].to_numpy()).all(axis=1)
    if strategy in ('forward_fill','regime_impute'):
        prepared=impute(raw,reference,regime=strategy=='regime_impute',bundle=bundle,limit=5)
    else:prepared=raw
    values,regime=predict_frame(bundle,prepared)
    usable_rows=np.isfinite(prepared[TELEMETRY_CHANNELS].to_numpy()).all(axis=1)
    if strategy=='missing_aware':
        if missing_model is None:raise ValueError('Missingness-aware fitted model required')
        values=missing_model.predict(raw)
    available=np.zeros(len(raw),dtype=bool);age=np.zeros(len(raw),dtype=int)
    prediction=np.clip(values,0,125);raw_prediction=values.copy()
    for positions in raw.groupby('engine_id',sort=False).indices.values():
        continuous=0;last=None;missing_age=0
        for pos in positions:
            cycle=int(raw.iloc[pos].cycle)
            missing_age=0 if finite[pos] else missing_age+1
            continuous=continuous+1 if usable_rows[pos] else 0
            ok=continuous>=20 and np.isfinite(prediction[pos])
            if strategy=='missing_aware':ok=cycle>=20 and missing_age<=stale_limit
            if finite[pos] and continuous>=20:last=(cycle,float(prediction[pos]))
            age[pos]=missing_age
            if strategy in ('bounded_last','decision_fallback') and not ok and last and cycle-last[0]<=stale_limit:
                prediction[pos]=max(0.,last[1]-(cycle-last[0]));ok=True
            available[pos]=ok
    # Explicit unavailable values never become pseudo forecasts.
    prediction=np.where(available,prediction,np.nan)
    result=raw[['engine_id','cycle']].copy()
    result['raw_prediction']=raw_prediction;result['prediction']=prediction
    result['available']=available;result['regime']=regime;result['stale_age']=age
    result['missing_fraction']=1-np.isfinite(raw[TELEMETRY_CHANNELS].to_numpy()).mean(axis=1)
    result['recovery']=strategy
    return result


def decision_features(stream):
    forbidden={'true_rul','failure_cycle','outcome','T'}
    if forbidden & set(stream):raise ValueError('Evaluator labels forbidden in decision features')
    result=stream[['cycle','stale_age','missing_fraction']].astype(float).copy()
    result['prediction']=stream.prediction.fillna(125.)
    result['available']=stream.available.astype(float)
    groups=stream.engine_id.astype(str)+(('_'+stream.scenario.astype(str)) if 'scenario' in stream else '')
    grouped=result.prediction.groupby(groups)
    result['slope_5']=grouped.diff(5).fillna(0.)/5
    result['volatility_10']=grouped.transform(lambda x:x.rolling(10,min_periods=2).std()).fillna(0.)
    changes=stream.regime.groupby(groups).diff().fillna(0.).ne(0).astype(float)
    result['regime_change_10']=changes.groupby(groups).transform(lambda x:x.rolling(10,min_periods=1).sum())
    return result.fillna(0.).round(10)
