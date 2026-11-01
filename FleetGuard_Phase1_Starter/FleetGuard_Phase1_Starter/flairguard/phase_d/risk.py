"""Decision-horizon models trained on genuinely engine-held-out base forecasts."""
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from lightgbm import LGBMClassifier
from sklearn.metrics import brier_score_loss,log_loss,average_precision_score
from .telemetry import decision_features


class DecisionRisk:
    def fit(self,stream,truth,horizon,seed):
        X=decision_features(stream)
        self.columns_=list(X)
        y=(np.asarray(truth)<=horizon).astype(int)
        if len(np.unique(y))!=2:raise ValueError('Risk fit requires both outcome classes')
        weights=1/stream.engine_id.map(stream.groupby('engine_id').size()).to_numpy()
        weights*=len(weights)/weights.sum()
        self.logistic_=make_pipeline(StandardScaler(),LogisticRegression(C=1.,max_iter=500,random_state=seed))
        self.logistic_.fit(X,y,logisticregression__sample_weight=weights)
        self.boosted_=LGBMClassifier(n_estimators=100,num_leaves=7,min_child_samples=40,
            learning_rate=.05,n_jobs=2,verbosity=-1,random_state=seed)
        self.boosted_.fit(X,y,sample_weight=weights)
        # Empirical residual CDF is an estimate, not an asserted distributional guarantee.
        finite=stream.prediction.notna().to_numpy()
        self.optimism_=np.sort(stream.prediction.to_numpy()[finite]-np.asarray(truth)[finite])
        self.horizon_=horizon;self.calibration_={}
        return self
    def raw(self,stream):
        X=decision_features(stream)
        if list(X)!=self.columns_:raise ValueError('Risk feature contract changed')
        residual=1-np.searchsorted(self.optimism_,stream.prediction.fillna(125).to_numpy()-self.horizon_,side='left')/len(self.optimism_)
        return dict(logistic=self.logistic_.predict_proba(X)[:,1],
                    boosted=self.boosted_.predict_proba(X)[:,1],residual=residual)
    def calibrate(self,stream,truth):
        y=(np.asarray(truth)<=self.horizon_).astype(int)
        weights=1/stream.engine_id.map(stream.groupby('engine_id').size()).to_numpy()
        for name,values in self.raw(stream).items():
            self.calibration_[name]=IsotonicRegression(out_of_bounds='clip').fit(values,y,sample_weight=weights)
        return self
    def predict(self,stream):
        raw=self.raw(stream)
        return {name:self.calibration_[name].predict(values) if name in self.calibration_ else values for name,values in raw.items()}


def risk_metrics(stream,truth,scores,threshold):
    target=np.asarray(truth)<=15;predicted=np.asarray(scores)>=threshold
    tp=int((target&predicted).sum());fp=int((~target&predicted).sum());positives=int(target.sum())
    frame=stream[['engine_id','cycle']].copy();frame['target']=target;frame['alarm']=predicted
    frame['truth']=np.asarray(truth)
    positive_engines=frame.loc[frame.target].engine_id.unique()
    detected=frame.loc[frame.target&frame.alarm].engine_id.nunique()
    leads=frame.loc[frame.target&frame.alarm].groupby('engine_id').truth.max()
    bins=[]
    for low,high in zip(np.linspace(0,1,11)[:-1],np.linspace(0,1,11)[1:]):
        mask=(scores>=low)&((scores<high) if high<1 else (scores<=high))
        if np.any(mask):bins.append(dict(lower=float(low),upper=float(high),rows=int(mask.sum()),
            predicted=float(np.asarray(scores)[mask].mean()),observed=float(target[mask].mean())))
    return dict(rows=len(stream),engines=int(stream.engine_id.nunique()),positives=positives,
        sensitivity=tp/positives if positives else None,precision=tp/(tp+fp) if tp+fp else None,
        false_positive_rate=fp/int((~target).sum()) if (~target).any() else None,
        referral_rate=float(predicted.mean()),automation_coverage=float(1-predicted.mean()),
        brier=float(brier_score_loss(target,scores)),log_loss=float(log_loss(target,np.clip(scores,1e-10,1-1e-10))),
        average_precision=float(average_precision_score(target,scores)),
        positive_engines=len(positive_engines),detected_engines=int(detected),
        mean_detection_lead=float(leads.mean()) if len(leads) else None,calibration_bins=bins,
        probability_scope='Retrospective empirical calibration only; no established sequential or deployment guarantee')
