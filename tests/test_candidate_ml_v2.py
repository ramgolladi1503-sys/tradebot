from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from core.analytics import candidate_ml_v2 as mod


def make_dataset(rows_per_session=30, sessions=14):
    rng = np.random.default_rng(7)
    rows=[]
    base=datetime(2025,1,1,3,45,tzinfo=timezone.utc)
    idx=0
    for day in range(sessions):
        for j in range(rows_per_session):
            ts=int((base+timedelta(days=day,minutes=j)).timestamp()*1000)
            breadth=float(rng.uniform(0.05,0.35))
            divergence=float(rng.normal(0,0.001))
            spread=float(rng.uniform(0.1,1.5))
            rv=float(rng.uniform(0.4,3.0))
            signal=2.0*breadth-1.2*spread/2+0.8*rv/3-300*divergence+rng.normal(0,0.2)
            target=int(signal>0.45)
            rows.append({
                'schema_version':mod.SCHEMA_VERSION,'event_id':f'e{idx}','trade_key':f't{idx}',
                'strategy_id':'MEG' if j%2==0 else 'VWAP','symbol':'NIFTY','option_type':'CE',
                'decision_ts_epoch_ms':ts,'feature_cutoff_ts_epoch_ms':ts,'outcome_ts_epoch_ms':ts+600000,
                'session_date':(base+timedelta(days=day)).date().isoformat(),'target':target,'stop_hit':1-target,
                'exec_feasible':1,'future_mfe_points':20.0 if target else 3.0,'future_mae_points':2.0 if target else 10.0,
                'future_net_r':1.4 if target else -1.1,'friction_r':0.1,
                'spread_pct':spread,'quote_age_sec':float(rng.uniform(0,2)),'relative_volume':rv,
                'distance_from_vwap_atr':float(rng.normal()),'breadth_up_1':breadth,'breadth_down_1':1-breadth,
                'index_breadth_divergence':divergence,'option_return_1':float(rng.normal(0,0.01)),
                'option_return_3':float(rng.normal(0,0.02)),'minutes_to_expiry':float(200-j),
                'read_only':True,'is_order_action':False,'broker_api_called':False,
                'allowed_for_live_execution':False,'append':False,
            })
            idx+=1
    df=pd.DataFrame(rows).sort_values('decision_ts_epoch_ms').reset_index(drop=True)
    for i in range(0,len(df),10):
        df.loc[i,'target']=0
        if i+1<len(df):
            df.loc[i+1,'target']=1
    return df


def test_build_candidate_row_rejects_future_feature_and_aligns_outcome():
    event={'event_id':'e1','trade_key':'t1','strategy_id':'MEG','symbol':'NIFTY','option_type':'CE',
           'ts_epoch_ms':1_700_000_000_000,'entry_price':100,'target_price':120,'stop_price':90,
           'metrics_snapshot':{'spread_pct':0.5,'relative_volume':1.2}}
    outcome={'event_ref_id':'e1','resolution_ts_epoch_ms':1_700_000_600_000,
             'trade_outcome':{'outcome':'hit_target','exec_feasible':True,'mfe_points':25,'mae_points':4}}
    row=mod.build_candidate_row(event,outcome)
    assert row['target']==1
    assert row['future_net_r']>0
    assert row['allowed_for_live_execution'] is False
    bad=dict(event)
    bad['metrics_snapshot']={'future_return':0.5}
    with pytest.raises(ValueError,match='forbidden_future_feature'):
        mod.build_candidate_row(bad,outcome)


def test_dataset_and_purged_walk_forward_are_chronological():
    df=make_dataset()
    mod.validate_candidate_dataset(df)
    splits=mod.purged_walk_forward_splits(df,n_splits=4,purge_rows=3,min_train_sessions=4)
    assert len(splits)==4
    for train_idx,test_idx in splits:
        assert train_idx.max()<test_idx.min()
        assert len(train_idx)>0 and len(test_idx)>0


def test_fit_predict_calibration_abstention_and_manifest(tmp_path):
    df=make_dataset(rows_per_session=40,sessions=16)
    cfg=mod.CandidateMLConfig(min_train_rows=100,min_validation_rows=40,min_strategy_rows=120,
        min_positive_rows=10,purge_rows=3,max_missing_ratio=0.25,ood_z_threshold=6.0)
    bundle=mod.fit_candidate_ml(df,cfg)
    assert bundle.global_model is not None
    row=df.iloc[-1].to_dict()
    pred=bundle.predict(row)
    assert pred.status in {mod.PredictionStatus.VALID,mod.PredictionStatus.BELOW_VALUE_THRESHOLD,mod.PredictionStatus.MODEL_DISAGREEMENT}
    assert pred.safety['allowed_for_live_execution'] is False
    incomplete={k:v for k,v in row.items() if k not in cfg.required_features[:5]}
    pred2=bundle.predict(incomplete)
    assert pred2.status==mod.PredictionStatus.FEATURES_INCOMPLETE
    ood=dict(row)
    ood['spread_pct']=1_000_000
    pred3=bundle.predict(ood)
    assert pred3.status==mod.PredictionStatus.OUT_OF_DISTRIBUTION
    path=bundle.save(tmp_path/'bundle.joblib')
    loaded=mod.CandidateMLBundle.load(path)
    assert loaded.dataset_hash==bundle.dataset_hash
    manifest=mod.bundle_manifest(bundle)
    assert manifest['allowed_for_live_execution'] is False


def test_drift_and_counterfactual_reporting():
    ref=pd.DataFrame({'x':np.linspace(0,1,100),'y':np.linspace(2,3,100)})
    cur=pd.DataFrame({'x':np.linspace(10,11,100),'y':np.linspace(2,3,100)})
    report=mod.drift_report(ref,cur)
    assert report['status']=='QUARANTINE_REQUIRED'
    shadow=mod.counterfactual_shadow_report([
        {'actual_decision':'ACCEPT','ml_status':'PREDICTION_VALID','future_net_r':1.0},
        {'actual_decision':'ACCEPT','ml_status':'BELOW_VALUE_THRESHOLD','future_net_r':-1.0},
        {'actual_decision':'REJECT','ml_status':'PREDICTION_VALID','future_net_r':0.5},
        {'actual_decision':'REJECT','ml_status':'MODEL_UNAVAILABLE','future_net_r':0.0},
    ])
    assert shadow['summary']['ACTUAL_ACCEPT_ML_ACCEPT']['rows']==1
    assert shadow['summary']['ACTUAL_ACCEPT_ML_REJECT']['mean_future_net_r']==-1.0
    assert shadow['summary']['UNRESOLVED']['rows']==1
