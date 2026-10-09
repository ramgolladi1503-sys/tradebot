from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from core.analytics import candidate_ml_v2 as mod
from core.analytics.candidate_ml_v2 import certification as certification_mod


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
    assert sum(1 for _ in splits)==4
    for train_idx,test_idx in splits:
        assert train_idx.max()<test_idx.min()
        assert train_idx.size>0 and test_idx.size>0
        assert df.iloc[train_idx]["session_date"].nunique() >= 4


def test_purged_walk_forward_removes_training_labels_crossing_test_boundary():
    df = make_dataset(rows_per_session=6, sessions=12)
    df["outcome_ts_epoch_ms"] = df["decision_ts_epoch_ms"] + 60_000
    # One training observation has a multi-session label horizon. Fixed-row
    # purging alone cannot guarantee its label is known before the test fold.
    df.loc[0, "outcome_ts_epoch_ms"] = int(df.loc[18, "decision_ts_epoch_ms"])
    splits = mod.purged_walk_forward_splits(
        df, n_splits=3, purge_rows=0, min_train_sessions=3
    )
    for train_idx, test_idx in splits:
        first_test = int(df.iloc[test_idx]["decision_ts_epoch_ms"].min())
        assert (df.iloc[train_idx]["outcome_ts_epoch_ms"] < first_test).all()
    assert 0 not in splits[0][0]


def test_purged_walk_forward_applies_explicit_time_embargo():
    df = make_dataset(rows_per_session=6, sessions=12)
    df["outcome_ts_epoch_ms"] = df["decision_ts_epoch_ms"] + 60_000
    first_test = int(df.loc[18, "decision_ts_epoch_ms"])
    df.loc[16, "decision_ts_epoch_ms"] = first_test - 10 * 60_000
    df.loc[16, "feature_cutoff_ts_epoch_ms"] = first_test - 10 * 60_000
    df.loc[16, "outcome_ts_epoch_ms"] = first_test - 9 * 60_000
    df.loc[17, "decision_ts_epoch_ms"] = first_test - 2 * 60_000
    df.loc[17, "feature_cutoff_ts_epoch_ms"] = first_test - 2 * 60_000
    df.loc[17, "outcome_ts_epoch_ms"] = first_test - 60_000
    df = df.sort_values("decision_ts_epoch_ms", kind="stable").reset_index(drop=True)
    boundary_inside_id = "e17"
    boundary_outside_id = "e16"
    embargo = 5 * 60_000
    splits = mod.purged_walk_forward_splits(
        df, n_splits=3, purge_rows=0, min_train_sessions=3, embargo_ms=embargo
    )
    train_idx, test_idx = splits[0]
    first_test = int(df.iloc[test_idx]["decision_ts_epoch_ms"].min())
    training_ids = set(df.iloc[train_idx]["event_id"])
    assert df.loc[df["event_id"] == boundary_inside_id, "outcome_ts_epoch_ms"].iloc[0] >= first_test - embargo
    assert boundary_inside_id not in training_ids
    assert boundary_outside_id in training_ids
    assert (df.iloc[train_idx]["outcome_ts_epoch_ms"] < first_test - embargo).all()


def test_ablation_training_obeys_label_purge_and_embargo(monkeypatch):
    df = make_dataset(rows_per_session=6, sessions=12)
    validation_start = int(df.loc[36, "decision_ts_epoch_ms"])
    df.loc[34, "decision_ts_epoch_ms"] = validation_start - 10 * 60_000
    df.loc[34, "feature_cutoff_ts_epoch_ms"] = validation_start - 10 * 60_000
    df.loc[34, "outcome_ts_epoch_ms"] = validation_start - 9 * 60_000
    df.loc[35, "decision_ts_epoch_ms"] = validation_start - 2 * 60_000
    df.loc[35, "feature_cutoff_ts_epoch_ms"] = validation_start - 2 * 60_000
    df.loc[35, "outcome_ts_epoch_ms"] = validation_start - 60_000
    df = df.sort_values("decision_ts_epoch_ms", kind="stable").reset_index(drop=True)
    observed_train_ids = []
    monkeypatch.setattr(certification_mod, "feature_columns", lambda frame: ["synthetic_feature"])

    def fake_nested_model(train, _config, *, features, embargo_ms):
        assert embargo_ms == 5 * 60_000
        observed_train_ids.extend(train["event_id"].tolist())
        return object()

    monkeypatch.setattr(certification_mod, "_nested_model", fake_nested_model)
    monkeypatch.setattr(certification_mod, "_score_frame", lambda _bundle, frame: frame)
    monkeypatch.setattr(certification_mod, "_fold_metrics", lambda _frame: {"lift_r": 0.0})
    certification_mod._ablation_report(
        df,
        mod.CandidateMLConfig(purge_rows=1),
        certification_mod.CandidateMLCertificationConfig(embargo_ms=5 * 60_000),
        supported_train_sessions=6,
    )
    assert "e35" not in observed_train_ids
    assert "e34" not in observed_train_ids
    assert "e33" in observed_train_ids


@pytest.mark.parametrize("kwargs", [{"embargo_ms": -1}, {"purge_rows": -1}])
def test_purged_walk_forward_rejects_negative_gap_controls(kwargs):
    with pytest.raises(ValueError, match="purge_and_embargo_must_be_nonnegative"):
        mod.purged_walk_forward_splits(make_dataset(), **kwargs)


def test_purged_walk_forward_fails_closed_if_temporal_purge_removes_train_sessions():
    df = make_dataset(rows_per_session=6, sessions=12)
    first_test_start = int(df.loc[18, "decision_ts_epoch_ms"])
    df.loc[df["session_date"].isin({df.loc[6, "session_date"], df.loc[12, "session_date"]}), "outcome_ts_epoch_ms"] = first_test_start
    with pytest.raises(ValueError, match="insufficient_train_sessions_after_purge"):
        mod.purged_walk_forward_splits(
            df, n_splits=3, purge_rows=0, min_train_sessions=3
        )


def test_nested_chronological_split_purges_unresolved_labels_and_embargo():
    df = make_dataset(rows_per_session=20, sessions=8)
    validation_start = int(df.loc[120, "decision_ts_epoch_ms"])
    df.loc[118, "decision_ts_epoch_ms"] = validation_start - 10 * 60_000
    df.loc[118, "feature_cutoff_ts_epoch_ms"] = validation_start - 10 * 60_000
    df.loc[118, "outcome_ts_epoch_ms"] = validation_start - 9 * 60_000
    df.loc[119, "decision_ts_epoch_ms"] = validation_start - 2 * 60_000
    df.loc[119, "feature_cutoff_ts_epoch_ms"] = validation_start - 2 * 60_000
    df.loc[119, "outcome_ts_epoch_ms"] = validation_start - 60_000
    df = df.sort_values("decision_ts_epoch_ms", kind="stable").reset_index(drop=True)
    train, validation = mod.chronological_split(
        df,
        mod.CandidateMLConfig(
            min_train_rows=20, min_validation_rows=20,
            purge_rows=0, validation_fraction=0.25,
        ),
        embargo_ms=5 * 60_000,
    )
    assert "e119" not in set(train["event_id"])
    assert "e118" in set(train["event_id"])
    assert validation["session_date"].nunique() == 2


def test_nested_model_forwards_certification_embargo(monkeypatch):
    df = make_dataset(rows_per_session=20, sessions=8)
    observed = {}
    monkeypatch.setattr(certification_mod, "feature_columns", lambda _frame: ["x"])

    def fake_split(frame, config, *, embargo_ms):
        observed["embargo_ms"] = embargo_ms
        return frame.iloc[:-20].copy(), frame.iloc[-20:].copy()

    monkeypatch.setattr(certification_mod, "chronological_split", fake_split)
    monkeypatch.setattr(certification_mod, "_fit_unit", lambda *args: object())
    certification_mod._nested_model(
        df, mod.CandidateMLConfig(), embargo_ms=1234
    )
    assert observed["embargo_ms"] == 1234


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


def test_temporal_feature_builder_is_causal_and_computes_cross_market_features():
    decision=1_700_000_600_000
    underlying=[]
    option=[]
    mirror=[]
    for index in range(7):
        ts=decision-(6-index)*60_000
        underlying.append({'ts_epoch_ms':ts,'close':100+index,'vwap':101,'atr':2,'volume':1000+100*index})
        option.append({'ts_epoch_ms':ts,'mark_price':50+2*index,'bid':61 if index==6 else 49+2*index,'ask':63 if index==6 else 51+2*index,'volume':100+20*index,'oi':1000+10*index})
        mirror.append({'ts_epoch_ms':ts,'mark_price':55-index,'bid':48,'ask':50,'volume':100,'oi':1000})
    constituents=[]
    for offset,ts in enumerate((decision-60_000,decision)):
        for symbol,ret,weight in [('A',0.01+offset*0.002,0.5),('B',-0.004,0.3),('C',0.006,0.2)]:
            constituents.append({'ts_epoch_ms':ts,'symbol':symbol,'return_1':ret,'weight':weight})
    features=mod.build_temporal_candidate_features(
        decision_ts_epoch_ms=decision,
        underlying_rows=underlying,
        constituent_rows=constituents,
        option_rows=option,
        mirror_option_rows=mirror,
        expiry_ts_epoch_ms=decision+180*60_000,
    )
    assert features['feature_source_max_ts_epoch_ms']<=decision
    assert features['breadth_up_1']>features['breadth_down_1']
    assert features['spread_pct']>0
    assert features['option_mirror_response_gap'] is not None
    assert features['minutes_to_expiry']==180
    contaminated=list(option)+[{'ts_epoch_ms':decision+1,'mark_price':999}]
    with pytest.raises(ValueError,match='option_future_row'):
        mod.build_temporal_candidate_features(
            decision_ts_epoch_ms=decision,
            underlying_rows=underlying,
            constituent_rows=constituents,
            option_rows=contaminated,
        )


def test_locked_holdout_is_durable_and_requires_acknowledgement(tmp_path):
    df=make_dataset(rows_per_session=20,sessions=15)
    research,seal=mod.seal_locked_holdout(df,holdout_path=tmp_path/'holdout.parquet',holdout_fraction=0.20)
    mod.verify_locked_holdout(seal)
    assert research.shape[0]+seal.rows==df.shape[0]
    assert seal.acknowledgement_imported is False
    assert seal.to_dict()['allowed_for_live_execution'] is False
    assert seal.to_dict()['allowed_for_paper_execution'] is False
    with pytest.raises(PermissionError,match='acknowledgement_invalid'):
        mod.open_locked_holdout(seal,acknowledgement='NO')
    opened=mod.open_locked_holdout(seal,acknowledgement=mod.HOLDOUT_ACKNOWLEDGEMENT)
    assert mod.semantic_dataset_hash(opened)==seal.semantic_sha256


def test_certification_reports_wfa_controls_without_consuming_holdout(tmp_path):
    full=make_dataset(rows_per_session=25,sessions=22)
    research,seal=mod.seal_locked_holdout(full,holdout_path=tmp_path/'locked.parquet',holdout_fraction=0.20)
    model_cfg=mod.CandidateMLConfig(
        min_train_rows=60,
        min_validation_rows=20,
        min_strategy_rows=100,
        min_positive_rows=5,
        purge_rows=1,
        max_missing_ratio=0.25,
        ood_z_threshold=8.0,
    )
    cert_cfg=mod.CandidateMLCertificationConfig(
        n_splits=3,
        min_train_sessions=5,
        min_selected_per_fold=1,
        min_positive_fold_fraction=0.33,
        max_ece=0.99,
        max_top_five_positive_contribution=1.0,
        max_best_session_positive_contribution=1.0,
        min_permutation_gap_r=-10.0,
        min_delayed_mean_lift_r=-10.0,
        max_ablation_features=1,
    )
    report=mod.certify_candidate_ml(research,model_config=model_cfg,certification_config=cert_cfg)
    assert report['verdict'] in {'READY_FOR_LOCKED_HOLDOUT','ML_EVIDENCE_QUARANTINED','NO_OUT_OF_SAMPLE_ML_LIFT','INSUFFICIENT_EVIDENCE'}
    assert report['holdout_metrics_consumed'] is False
    assert report['allowed_for_live_execution'] is False
    assert report['walk_forward_support']['support_gates_lowered'] is False
    assert report['walk_forward_support']['effective_min_train_sessions'] >= cert_cfg.min_train_sessions
    assert report['walk_forward_support']['nested_train_rows'] >= model_cfg.min_train_rows
    assert report['walk_forward_support']['nested_validation_rows'] >= model_cfg.min_validation_rows
    assert report['base_walk_forward']['summary']['folds']>=1
    assert report['label_permutation_control']['summary']['folds']>=1
    assert report['one_row_delayed_feature_control']['summary']['folds']>=1
    mod.verify_locked_holdout(seal)
