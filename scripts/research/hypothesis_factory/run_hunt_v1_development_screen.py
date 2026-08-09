#!/usr/bin/env python3
"""Development-only screen for HUNT_V1_GENERATION_FREEZE.

Uses only the chronological first 60% of sessions for economic evaluation.
Validation and holdout outcomes are not evaluated or printed. Research-only.
"""
from __future__ import annotations
import argparse,csv,hashlib,itertools,json,math
from pathlib import Path
from statistics import mean

EXPECTED_DATASET_SHA="66ddbfead966388262b9a1e49937fb227b711ce32f70eaf715a93a5e32572b32"
EXPECTED_GENERATION="HUNT_V1_GENERATION_FREEZE"


def sha256(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def f(r,k):
    try:return float(r[k])
    except Exception:return float('nan')
def sgn(x): return 1 if x>0 else -1 if x<0 else 0

def load_rows(p):
    with open(p,newline='',encoding='utf-8') as h: rows=list(csv.DictReader(h))
    req={'timestamp','session','banknifty_close','banknifty_ret_1_bps','nifty_ret_1_bps','sensex_ret_1_bps','banknifty_from_open_bps','nifty_from_open_bps','sensex_from_open_bps','bn_minus_nifty_bps','bn_minus_sensex_bps','leaders_consensus'}
    if not rows or not req.issubset(rows[0]): raise ValueError('dataset_schema_mismatch')
    return rows

def config_grid(grid,horizons):
    keys=sorted(grid)
    vals=[grid[k] for k in keys]
    for combo in itertools.product(*vals):
        base=dict(zip(keys,combo))
        for h in horizons: yield {**base,'horizon_bars':int(h)}

def direction(pid,r,c):
    br=f(r,'banknifty_ret_1_bps'); nr=f(r,'nifty_ret_1_bps'); sr=f(r,'sensex_ret_1_bps')
    bfo=f(r,'banknifty_from_open_bps'); nfo=f(r,'nifty_from_open_bps'); sfo=f(r,'sensex_from_open_bps')
    if not all(math.isfinite(x) for x in (br,nr,sr,bfo,nfo,sfo)): return 0
    if pid=='HUNT_V1_LEADER_CONSENSUS_LAG_CATCHUP':
        if sgn(nr)==0 or sgn(nr)!=sgn(sr): return 0
        d=sgn(nr); avg=(nr+sr)/2
        return d if abs(avg)>=c['leader_min_bps'] and d*(avg-br)>=c['lag_gap_bps'] else 0
    if pid=='HUNT_V1_FROM_OPEN_RELATIVE_STRENGTH_PERSISTENCE':
        if sgn(nfo)==0 or sgn(nfo)!=sgn(sfo): return 0
        d=sgn(nfo); avg=(nfo+sfo)/2
        return d if min(abs(nfo),abs(sfo))>=c['leader_from_open_min_bps'] and sgn(bfo)==d and d*(bfo-avg)>=c['relative_strength_margin_bps'] else 0
    if pid=='HUNT_V1_TRANSIENT_DIVERGENCE_MEAN_REVERSION':
        dn=f(r,'bn_minus_nifty_bps'); ds=f(r,'bn_minus_sensex_bps')
        if not math.isfinite(dn) or not math.isfinite(ds) or sgn(dn)==0 or sgn(dn)!=sgn(ds): return 0
        d=sgn(dn); avgfo=(nfo+sfo)/2
        return -d if min(abs(dn),abs(ds))>=c['divergence_min_bps'] and d*bfo<=d*avgfo+c['confirmation_margin_bps'] else 0
    if pid=='HUNT_V1_LEADER_REVERSAL_TRANSMISSION':
        if sgn(nr)==0 or sgn(nr)!=sgn(sr) or sgn(nfo)==0 or sgn(nfo)!=sgn(sfo): return 0
        d=sgn(nr); prior=sgn(nfo)
        return d if prior==-d and min(abs(nfo),abs(sfo))>=c['from_open_min_bps'] and min(abs(nr),abs(sr))>=c['reversal_bar_min_bps'] and sgn(bfo)==prior else 0
    if pid=='HUNT_V1_DISAGREEMENT_RESOLUTION':
        cons=int(round(f(r,'leaders_consensus')))
        if cons!=0 or sgn(nfo)==0 or sgn(nfo)!=sgn(sfo): return 0
        d=sgn(nfo)
        return d if min(abs(nfo),abs(sfo))>=c['from_open_min_bps'] else 0
    raise ValueError('unknown_passport:'+pid)

def evaluate(rows,dev_idx,pid,c,cost_bps):
    rets=[]; i=min(dev_idx) if dev_idx else 0; end=max(dev_idx) if dev_idx else -1
    while i<=end:
        if i not in dev_idx: i+=1; continue
        d=direction(pid,rows[i],c)
        if not d: i+=1; continue
        entry=i+1; exit_=entry+c['horizon_bars']
        if entry not in dev_idx or exit_ not in dev_idx or exit_>end: i+=1; continue
        sess=rows[i]['session']
        if rows[entry]['session']!=sess or rows[exit_]['session']!=sess: i+=1; continue
        p0=f(rows[entry],'banknifty_close'); p1=f(rows[exit_],'banknifty_close')
        if not (math.isfinite(p0) and math.isfinite(p1) and p0>0): i+=1; continue
        gross=d*((p1-p0)/p0)*10000.0
        rets.append(gross-float(cost_bps))
        i=exit_+1
    if not rets:return {'trades':0,'mean_net_bps':None,'win_rate':None,'total_net_bps':None}
    return {'trades':len(rets),'mean_net_bps':mean(rets),'win_rate':sum(x>0 for x in rets)/len(rets),'total_net_bps':sum(rets)}

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.')
    ap.add_argument('--dataset',default='research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv')
    ap.add_argument('--freeze',default='research/strategy_certification/passports/HUNT_V1_GENERATION_FREEZE.json')
    ap.add_argument('--output',default='research/evidence/strategy_certification/HUNT_V1_DEVELOPMENT_SCREEN.json')
    a=ap.parse_args(argv);root=Path(a.repo_root).resolve();ds=root/a.dataset;fp=root/a.freeze;out=root/a.output
    result={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'validation_accessed':False,'holdout_accessed':False}
    try:
        freeze=json.loads(fp.read_text(encoding='utf-8'))
        if freeze.get('generation_id')!=EXPECTED_GENERATION: raise ValueError('generation_id_mismatch')
        if freeze.get('dataset_sha256')!=EXPECTED_DATASET_SHA or sha256(ds)!=EXPECTED_DATASET_SHA: raise ValueError('dataset_hash_mismatch')
        rows=load_rows(ds);sessions=sorted({r['session'] for r in rows});n_dev=int(len(sessions)*freeze['split_contract']['development_fraction']);dev_sessions=set(sessions[:n_dev]);dev_idx={i for i,r in enumerate(rows) if r['session'] in dev_sessions}
        horizons=freeze['execution_contract']['development_horizons_bars'];cost=freeze['execution_contract']['base_round_trip_cost_bps'];gate=freeze['development_gate']
        candidates=[]
        for p in freeze['passports']:
            configs=[]
            for c in config_grid(p['grid'],horizons):
                m=evaluate(rows,dev_idx,p['passport_id'],c,cost);configs.append({'config':c,'metrics':m})
            eligible=[x for x in configs if x['metrics']['trades']>=gate['minimum_trades'] and x['metrics']['mean_net_bps'] is not None and x['metrics']['mean_net_bps']>0]
            eligible.sort(key=lambda x:(x['metrics']['mean_net_bps'],x['metrics']['trades']),reverse=True)
            nomination=eligible[0] if eligible else None
            candidates.append({'passport_id':p['passport_id'],'configs_tested':len(configs),'development_status':'NOMINATED_FOR_VALIDATION' if nomination else 'REJECTED_IN_DEVELOPMENT','nomination':nomination,'all_development_results':configs})
        result.update({'status':'DEVELOPMENT_SCREEN_COMPLETE','dataset_sha256':sha256(ds),'generation_sha256':sha256(fp),'sessions_total':len(sessions),'development_sessions':n_dev,'validation_sessions_reserved':int(len(sessions)*freeze['split_contract']['validation_fraction']),'holdout_sessions_reserved':len(sessions)-n_dev-int(len(sessions)*freeze['split_contract']['validation_fraction']),'candidates':candidates,'nominated_count':sum(c['development_status']=='NOMINATED_FOR_VALIDATION' for c in candidates),'validation_accessed':False,'holdout_accessed':False,'parameters_tuned':False,'selection_note':'NOMINATIONS USE ONLY DEVELOPMENT RESULTS WITHIN EACH FROZEN PASSPORT GRID; NO VALIDATION OR HOLDOUT OUTCOMES WERE EVALUATED.'})
    except Exception as e: result['error']=f'{type(e).__name__}:{e}'
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(result,indent=2));return 0 if result['status']=='DEVELOPMENT_SCREEN_COMPLETE' else 2
if __name__=='__main__': raise SystemExit(main())
