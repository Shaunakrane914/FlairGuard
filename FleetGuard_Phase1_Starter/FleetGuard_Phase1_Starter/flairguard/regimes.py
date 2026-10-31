"""Fit-only operating-condition normalization and causal FD002 features."""
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.dummy import DummyRegressor
from lightgbm import LGBMRegressor
from .quality import ACTIVE_SENSORS, TELEMETRY_CHANNELS

SETTINGS=[f'setting_{i}' for i in range(1,4)]
OBSERVATIONS=['engine_id','cycle',*TELEMETRY_CHANNELS]


def observations_only(frame):
    if set(frame.columns)-set(OBSERVATIONS):
        raise ValueError('Only observations may enter the feature boundary; labels are forbidden')
    if not set(OBSERVATIONS)<=set(frame.columns):
        raise ValueError('Incomplete observation schema')
    if frame.duplicated(['engine_id','cycle']).any():
        raise ValueError('Duplicate observation keys')
    if not frame.sort_values(['engine_id','cycle']).index.equals(frame.index):
        raise ValueError('Observations must be sorted by engine and cycle')


class RegimeFeatures:
    def __init__(self, mode='regime', n_regimes=6, nominal_cutoff=30, seed=42):
        if mode not in ('regime','global'):raise ValueError('Unknown normalization')
        self.mode=mode;self.n_regimes=n_regimes;self.nominal_cutoff=nominal_cutoff;self.seed=seed

    def fit(self, raw):
        observations_only(raw)
        if not np.isfinite(raw[TELEMETRY_CHANNELS].to_numpy()).all():raise ValueError('Fit data must be finite')
        self.fit_engines_=sorted(map(int,raw.engine_id.unique()))
        self.setting_scaler_=StandardScaler().fit(raw[SETTINGS])
        settings=self.setting_scaler_.transform(raw[SETTINGS])
        km=KMeans(n_clusters=self.n_regimes,n_init=10,random_state=self.seed).fit(settings)
        order=np.lexsort(km.cluster_centers_[:,::-1].T)
        self.centers_=km.cluster_centers_[order]
        regime,_=self.assign(raw)
        early=raw.cycle.to_numpy()<=self.nominal_cutoff
        sensor=raw[ACTIVE_SENSORS].to_numpy(dtype=float)
        self.means_=np.empty((self.n_regimes,len(ACTIVE_SENSORS)))
        self.scales_=np.empty_like(self.means_);self.reference_counts_=[]
        for k in range(self.n_regimes):
            mask=early & (regime==k)
            if mask.sum()<20:raise ValueError('Insufficient fit-only nominal regime reference')
            self.reference_counts_.append(int(mask.sum()))
            self.means_[k]=sensor[mask].mean(axis=0)
            self.scales_[k]=np.maximum(sensor[mask].std(axis=0),1e-3)
        self.global_mean_=sensor[early].mean(axis=0)
        self.global_scale_=np.maximum(sensor[early].std(axis=0),1e-3)
        return self

    def assign(self, raw):
        values=raw[SETTINGS].to_numpy(dtype=float)
        valid=np.isfinite(values).all(axis=1)
        scaled=(values-self.setting_scaler_.mean_)/self.setting_scaler_.scale_
        distance=np.sqrt(((scaled[:,None,:]-self.centers_[None,:,:])**2).sum(axis=2))
        labels=np.where(valid,np.nan_to_num(distance,nan=np.inf).argmin(axis=1),-1)
        return labels,np.where(valid,np.nan_to_num(distance,nan=np.inf).min(axis=1),np.nan)

    def transform(self, raw):
        observations_only(raw)
        regime,distance=self.assign(raw);safe=np.maximum(regime,0)
        sensor=raw[ACTIVE_SENSORS].to_numpy(dtype=float)
        mean=self.means_[safe] if self.mode=='regime' else self.global_mean_
        scale=self.scales_[safe] if self.mode=='regime' else self.global_scale_
        norm=pd.DataFrame((sensor-mean)/scale,index=raw.index,columns=ACTIVE_SENSORS)
        norm.loc[regime<0,:]=np.nan
        features=pd.DataFrame({'cycle':raw.cycle.astype(float)},index=raw.index)
        for j,key in enumerate(SETTINGS):features[key]=(raw[key]-self.setting_scaler_.mean_[j])/self.setting_scaler_.scale_[j]
        for k in range(self.n_regimes):features[f'regime_{k}']=(regime==k).astype(float)
        for key in ACTIVE_SENSORS:
            features[key]=norm[key]
            for window in (5,20):
                features[f'{key}_mean_{window}']=norm[key].groupby(raw.engine_id).transform(lambda x:x.rolling(window,min_periods=1).mean())
        finite=np.isfinite(raw[TELEMETRY_CHANNELS].to_numpy(dtype=float)).all(axis=1)
        history=np.zeros(len(raw),dtype=int)
        for positions in raw.groupby('engine_id',sort=False).indices.values():
            count=0;last=None
            for pos in positions:
                cycle=int(raw.iloc[pos].cycle)
                count=(count+1 if last is None or cycle==last+1 else 1) if finite[pos] else 0
                history[pos]=min(count,20);last=cycle
        flat=np.zeros(len(raw),dtype=bool)
        for key in ACTIVE_SENSORS:
            grouped=raw[key].groupby(raw.engine_id)
            low=grouped.transform(lambda x:x.rolling(10,min_periods=10).min())
            high=grouped.transform(lambda x:x.rolling(10,min_periods=10).max())
            flat |= (low==high).to_numpy()
        innovation=norm.groupby(raw.engine_id).diff().abs().mean(axis=1).fillna(0)
        diagnostic=pd.DataFrame(dict(regime=regime,setting_distance=distance,
            support_max=norm.abs().max(axis=1),support_mean=norm.abs().mean(axis=1),
            innovation_mean=innovation,flatline=flat,history_length=history,
            missing_fraction=1-np.isfinite(raw[TELEMETRY_CHANNELS].to_numpy()).mean(axis=1)),index=raw.index)
        return features.round(10),diagnostic


class RegimeModel:
    def __init__(self, name, protocol):self.name=name;self.protocol=protocol

    def fit(self, raw, truth):
        p=self.protocol
        self.features_=RegimeFeatures('global' if self.name=='GlobalLightGBM' else 'regime',
                                     p['regimes'],p['nominal_cutoff'],p['seed']).fit(raw)
        X,_=self.features_.transform(raw);self.columns_=list(X)
        weights=1/raw.engine_id.map(raw.groupby('engine_id').size()).to_numpy(dtype=float)
        weights*=len(weights)/weights.sum()
        y=np.clip(np.asarray(truth,dtype=float),0,p['rul_cap'])
        if self.name=='AgeRidge':self.estimator_=Ridge(alpha=100.0)
        elif self.name=='Constant':self.estimator_=DummyRegressor()
        else:self.estimator_=LGBMRegressor(**p['predictor'],random_state=p['seed'],n_jobs=2,verbosity=-1)
        self.estimator_.fit(X[['cycle']] if self.name=='AgeRidge' else X,y,sample_weight=weights)
        return self

    def predict(self, raw):
        X,diagnostic=self.features_.transform(raw)
        if list(X)!=self.columns_:raise ValueError('Feature contract changed')
        values=self.estimator_.predict(X[['cycle']] if self.name=='AgeRidge' else X)
        return np.asarray(values,dtype=float),diagnostic


def corrupt_measurements(raw, scenario, reference, seed):
    """Corrupt raw sensors in local regime SD units; never alter IDs/settings/T."""
    changed=raw.copy(deep=True)
    if scenario['kind']=='clean':return changed
    regimes,_=reference.assign(raw)
    for engine,positions in raw.groupby('engine_id',sort=False).groups.items():
        group=raw.loc[positions];mask=group.cycle.between(scenario['onset'],scenario['onset']+scenario['duration']-1)
        indices=group.index[mask];n=len(indices)
        if not n:continue
        rng=np.random.default_rng(seed+int(engine)+scenario['onset'])
        shared_noise=rng.normal(size=n)
        for sensor in scenario['sensors']:
            if scenario['kind']=='missing':changed.loc[indices,sensor]=np.nan
            elif scenario['kind']=='stuck':
                previous=group[group.cycle<scenario['onset']]
                if previous.empty:raise ValueError('Stuck case needs an observed previous sample')
                changed.loc[indices,sensor]=previous[sensor].iloc[-1]
            else:
                j=ACTIVE_SENSORS.index(sensor)
                # Labels from assign() follow positional order, not DataFrame index values.
                position=raw.index.get_indexer(indices)
                sd=reference.scales_[regimes[position],j]
                effect=shared_noise if scenario['kind']=='noise' else (group.loc[indices,'cycle'].to_numpy()-scenario['onset']+1)/scenario['duration']
                if scenario['kind'] not in ('noise','drift'):raise ValueError('Unknown corruption')
                changed.loc[indices,sensor]+=scenario['sigma']*sd*effect
    return changed


def selector_inputs(stream, n_regimes=6):
    """Declared observational predictors of error; never interval width or labels."""
    keys=['cycle','prediction','disagreement','support_max','support_mean','innovation_mean',
          'setting_distance','history_length','missing_fraction','flatline']
    result=stream[keys].astype(float).copy()
    for k in range(n_regimes):result[f'regime_{k}']=(stream.regime==k).astype(float)
    return result
