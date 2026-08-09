#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,itertools,json,math
from pathlib import Path
from statistics import mean
EXPECTED_DATASET_SHA='66ddbfead966388262b9a1e49937fb227b711ce32f70eaf715a93a5e32572b32'
EXPECTED_GENERATION='HUNT_V2_GENERATION_FREEZE'
def sha256(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def f(r,k):
    try:return float(r[k])
    except Exception:return float('nan')
def sgn(x): return 1 if x>0 else -1 if x<0 else 0
def load_rows(p):
    with open(p,newline='',encoding='utf-8') as h: rows=list(csv.DictReader(h))
    req={'timestamp','session','banknifty_close','banknifty_ret_1_bps','nifty_ret_1_bps','sensex_ret_1_bps','banknifty_from_open_bps','nifty_from_open_bps','sensex_from_open_bps','bn_minus_nifty_bps','bn_minus_sensex_bps'}
    if not rows or not req.issubset(rows[0]): raise ValueError('dataset_schema_mismatch')
    return rows
def grid(g,horizons):
    keys=sorted(g); vals=[g[k] for k in keys]
    for combo in itertools.product(*vals):
        base=dict(zip(keys,combo))
        for h in horizons: yield {**base,'horizon_bars':int(h)}
def direction(pid,r,c):
    br=f(r,'banknifty_ret_1_bps');nr=f(r,'nifty_ret_1_bps');sr=f(r,'sensex_ret_1_bps');bfo=f(r,'banknifty_from_open_bps');nfo=f(r,'nifty_from_open_bps');sfo=f(r,'sensex_from_open_bps');dn=f(r,'bn_minus_nifty_bps');ds=f(r,'bn_minus_sensex_bps')
    if not all(math.isfinite(x) for x in (br,nr,sr,bfo,nfo,sfo,dn,ds)): return 0
    if pid=='HUNT_V2_BANKNIFTY_OPENING_SHOCK_DECAY':
        return sgn(br) if abs(bfo)>=c['shock_bps'] and sgn(br)!=0 and sgn(br)==-sgn(bfo) and abs(br)>=c['counter_bar_bps'] else 0
    if pid=='HUNT_V2_CROSS_MARKET_DISPERSION_COMPRESSION':
        return -sgn(dn) if sgn(dn)!=0 and sgn(dn)==sgn(ds) and min(abs(dn),abs(ds))>=c['dispersion_bps'] else 0
    if pid=='HUNT_V2_RELATIVE_ACCELERATION_CONTINUATION':
        avg=(abs(nfo)+abs(sfo))/2
        return sgn(br) if sgn(br)!=0 and sgn(br)==sgn(bfo) and abs(br)>=c['bar_bps'] and abs(bfo)-avg>=c['margin_bps'] else 0
    if pid=='HUNT_V2_TWO_BAR_LEADER_CONFIRMATION':
        if sgn(nr)==0 or sgn(nr)!=sgn(sr): return 0
        d=sgn(nr); avg=(abs(nr)+abs(sr))/2
        return d if min(abs(nr),abs(sr))>=c['leader_bar_bps'] and sgn(br)==d and avg-abs(br)>=c['gap_bps'] else 0
    if pid=='HUNT_V2_OPENING_DISLOCATION_REJOIN':
        if sgn(nfo)==0 or sgn(nfo)!=sgn(sfo): return 0
        d=sgn(nfo)
        return d if sgn(bfo)==-d and min(abs(nfo),abs(sfo))>=c['leader_open_bps'] and abs(bfo)>=c['bn_open_bps'] else 0
    raise ValueError('unknown_passport:'+pid)
def evaluate(rows,idxs,pid,c,cost):
    rets=[];i=min(idxs) if idxs else 0;end=max(idxs) if idxs else -1
    while i<=end:
        if i not in idxs:i+=1;continue
        d=direction(pid,rows[i],c)
        if not d:i+=1;continue
        entry=i+1;exit_=entry+c['horizon_bars'];sess=rows[i]['session']
        if entry not in idxs or exit_ not in idxs or exit_>end or rows[entry]['session']!=sess or rows[exit_]['session']!=sess:i+=1;continue
        p0=f(rows[entry],'banknifty_close');p1=f(rows[exit_],'banknifty_close')
        if not(math.isfinite(p0) and math.isfinite(p1) and p0>0):i+=1;continue
        rets.append(d*((p1-p0)/p0)*10000.0-float(cost));i=exit_+1
    if not rets:return {'trades':0,'mean_net_bps':None,'win_rate':None,'total_net_bps':None}
    return {'trades':len(rets),'mean_net_bps':mean(rets),'win_rate':sum(x>0 for x in rets)/len(rets),'total_net_bps':sum(rets)}
def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');ap.add_argument('--dataset',default='research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv');ap.add_argument('--freeze',default='research/strategy_certification/passports/HUNT_V2_GENERATION_FREEZE.json');ap.add_argument('--output',default='research/evidence/strategy_certification/HUNT_V2_DEVELOPMENT_SCREEN.json');a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve();ds=root/a.dataset;fp=root/a.freeze;out=root/a.output;res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'validation_accessed':False,'holdout_accessed':False}
    try:
        fr=json.loads(fp.read_text());
        if fr.get('generation_id')!=EXPECTED_GENERATION: raise ValueError('generation_id_mismatch')
        if fr.get('dataset_sha256')!=EXPECTED_DATASET_SHA or sha256(ds)!=EXPECTED_DATASET_SHA: raise ValueError('dataset_hash_mismatch')
        rows=load_rows(ds);sessions=sorted({r['session'] for r in rows});nd=int(len(sessions)*fr['split_contract']['development_fraction']);dev=set(sessions[:nd]);idx={i for i,r in enumerate(rows) if r['session'] in dev};horizons=fr['execution_contract']['development_horizons_bars'];cost=fr['execution_contract']['base_round_trip_cost_bps'];gate=fr['development_gate'];cands=[]
        for p in fr['passports']:
            arr=[]
            for c in grid(p['grid'],horizons): arr.append({'config':c,'metrics':evaluate(rows,idx,p['passport_id'],c,cost)})
            elig=[x for x in arr if x['metrics']['trades']>=gate['minimum_trades'] and x['metrics']['mean_net_bps'] is not None and x['metrics']['mean_net_bps']>0]
            elig.sort(key=lambda x:(x['metrics']['mean_net_bps'],x['metrics']['trades']),reverse=True);nom=elig[0] if elig else None
            cands.append({'passport_id':p['passport_id'],'configs_tested':len(arr),'development_status':'NOMINATED_FOR_VALIDATION' if nom else 'REJECTED_IN_DEVELOPMENT','nomination':nom,'all_development_results':arr})
        res.update({'status':'DEVELOPMENT_SCREEN_COMPLETE','dataset_sha256':sha256(ds),'generation_sha256':sha256(fp),'sessions_total':len(sessions),'development_sessions':nd,'validation_sessions_reserved':int(len(sessions)*fr['split_contract']['validation_fraction']),'holdout_sessions_reserved':len(sessions)-nd-int(len(sessions)*fr['split_contract']['validation_fraction']),'candidates':cands,'nominated_count':sum(x['development_status']=='NOMINATED_FOR_VALIDATION' for x in cands),'parameters_tuned':False})
    except Exception as e:res['error']=f'{type(e).__name__}:{e}'
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n');print(json.dumps(res,indent=2));return 0 if res['status']=='DEVELOPMENT_SCREEN_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
