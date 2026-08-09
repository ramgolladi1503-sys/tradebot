#!/usr/bin/env python3
"""Validation-only gate for the exact HUNT_V1 development nomination.

Evaluates only the frozen nominated configuration on the reserved chronological
validation block. Does not test neighboring configs and does not evaluate holdout outcomes.
Research-only; no runtime/broker authority.
"""
from __future__ import annotations
import argparse,csv,hashlib,importlib.util,json,math,sys
from pathlib import Path
from statistics import mean

EXPECTED_DATASET_SHA="66ddbfead966388262b9a1e49937fb227b711ce32f70eaf715a93a5e32572b32"
EXPECTED_GENERATION_SHA="3c74dc940645f4d34edf211c436183cb9f3742457c9b8386ff6e8b1f2db0cb1e"
EXPECTED_GATE_ID="HUNT_V1_VALIDATION_GATE_FREEZE"
EXPECTED_PID="HUNT_V1_LEADER_REVERSAL_TRANSMISSION"
EXPECTED_CONFIG={"from_open_min_bps":40,"reversal_bar_min_bps":15,"horizon_bars":3}


def sha256(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def f(r,k):
    try:return float(r[k])
    except Exception:return float('nan')

def load_dev_module(root):
    path=root/'scripts/research/hypothesis_factory/run_hunt_v1_development_screen.py'
    spec=importlib.util.spec_from_file_location('hunt_v1_dev_module',path)
    if spec is None or spec.loader is None: raise RuntimeError('dev_module_import_spec_failed')
    mod=importlib.util.module_from_spec(spec);sys.modules['hunt_v1_dev_module']=mod;spec.loader.exec_module(mod);return mod

def load_rows(path):
    with open(path,newline='',encoding='utf-8') as h:return list(csv.DictReader(h))

def evaluate(rows,idxs,mod,pid,c,cost_bps):
    rets=[];i=min(idxs) if idxs else 0;end=max(idxs) if idxs else -1
    while i<=end:
        if i not in idxs:i+=1;continue
        d=mod.direction(pid,rows[i],c)
        if not d:i+=1;continue
        entry=i+1;exit_=entry+c['horizon_bars']
        if entry not in idxs or exit_ not in idxs or exit_>end:i+=1;continue
        sess=rows[i]['session']
        if rows[entry]['session']!=sess or rows[exit_]['session']!=sess:i+=1;continue
        p0=f(rows[entry],'banknifty_close');p1=f(rows[exit_],'banknifty_close')
        if not (math.isfinite(p0) and math.isfinite(p1) and p0>0):i+=1;continue
        rets.append(d*((p1-p0)/p0)*10000.0-float(cost_bps));i=exit_+1
    if not rets:return {'trades':0,'mean_net_bps':None,'win_rate':None,'total_net_bps':None}
    return {'trades':len(rets),'mean_net_bps':mean(rets),'win_rate':sum(x>0 for x in rets)/len(rets),'total_net_bps':sum(rets)}

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.')
    ap.add_argument('--dataset',default='research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv')
    ap.add_argument('--generation',default='research/strategy_certification/passports/HUNT_V1_GENERATION_FREEZE.json')
    ap.add_argument('--gate',default='research/strategy_certification/passports/HUNT_V1_VALIDATION_GATE_FREEZE.json')
    ap.add_argument('--development-evidence',default='research/evidence/strategy_certification/HUNT_V1_DEVELOPMENT_SCREEN.json')
    ap.add_argument('--output',default='research/evidence/strategy_certification/HUNT_V1_VALIDATION_RESULT.json')
    a=ap.parse_args(argv);root=Path(a.repo_root).resolve();ds=root/a.dataset;gp=root/a.generation;gatep=root/a.gate;devp=root/a.development_evidence;out=root/a.output
    result={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'holdout_outcomes_accessed':False}
    try:
        if sha256(ds)!=EXPECTED_DATASET_SHA: raise ValueError('dataset_hash_mismatch')
        if sha256(gp)!=EXPECTED_GENERATION_SHA: raise ValueError('generation_hash_mismatch')
        gate=json.loads(gatep.read_text(encoding='utf-8'))
        if gate.get('gate_id')!=EXPECTED_GATE_ID: raise ValueError('gate_id_mismatch')
        if gate.get('parent_generation_sha256')!=EXPECTED_GENERATION_SHA: raise ValueError('gate_parent_generation_mismatch')
        if gate.get('nominated_passport_id')!=EXPECTED_PID or gate.get('nominated_configuration')!=EXPECTED_CONFIG: raise ValueError('gate_nomination_mismatch')
        dev=json.loads(devp.read_text(encoding='utf-8'))
        if dev.get('status')!='DEVELOPMENT_SCREEN_COMPLETE' or dev.get('nominated_count')!=1: raise ValueError('development_evidence_state_mismatch')
        if dev.get('validation_accessed') is not False or dev.get('holdout_accessed') is not False: raise ValueError('development_evidence_contaminated')
        cand=next((x for x in dev.get('candidates',[]) if x.get('passport_id')==EXPECTED_PID),None)
        if not cand or cand.get('development_status')!='NOMINATED_FOR_VALIDATION': raise ValueError('expected_nomination_missing')
        nom=cand.get('nomination') or {}
        if nom.get('config')!=EXPECTED_CONFIG: raise ValueError('development_nomination_config_mismatch')
        dm=nom.get('metrics') or {}
        if dm.get('trades')!=65 or abs(float(dm.get('mean_net_bps'))-0.23406261792223698)>1e-12: raise ValueError('development_nomination_metrics_mismatch')
        rows=load_rows(ds);sessions=sorted({r['session'] for r in rows})
        if len(sessions)!=493: raise ValueError('session_count_mismatch')
        val_sessions=set(sessions[295:393]);val_idx={i for i,r in enumerate(rows) if r['session'] in val_sessions}
        mod=load_dev_module(root);cost=float(gate['validation_gate']['cost_bps'])
        metrics=evaluate(rows,val_idx,mod,EXPECTED_PID,EXPECTED_CONFIG,cost)
        vg=gate['validation_gate'];passed=(metrics['trades']>=int(vg['minimum_trades']) and metrics['mean_net_bps'] is not None and metrics['mean_net_bps']>float(vg['require_mean_net_bps_gt']) and metrics['total_net_bps'] is not None and metrics['total_net_bps']>float(vg['require_total_net_bps_gt']))
        result.update({'status':'VALIDATION_COMPLETE','verdict':'VALIDATION_PASS' if passed else 'VALIDATION_FAIL','passport_id':EXPECTED_PID,'configuration':EXPECTED_CONFIG,'validation_sessions':98,'metrics':metrics,'development_evidence_sha256':sha256(devp),'validation_gate_sha256':sha256(gatep),'generation_sha256':sha256(gp),'dataset_sha256':sha256(ds),'holdout_outcomes_accessed':False,'next_action':'FREEZE_HOLDOUT_GATE_BEFORE_ACCESS' if passed else 'REJECT_CANDIDATE_NO_RETUNE'})
    except Exception as e: result['error']=f'{type(e).__name__}:{e}'
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(result,indent=2));return 0 if result['status']=='VALIDATION_COMPLETE' else 2
if __name__=='__main__': raise SystemExit(main())
