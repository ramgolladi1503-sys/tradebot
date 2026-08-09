#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,itertools,json,math
from pathlib import Path
from statistics import mean

EXPECTED_DATASET_SHA='66ddbfead966388262b9a1e49937fb227b711ce32f70eaf715a93a5e32572b32'
EXPECTED_GENERATION='HUNT_V3_GENERATION_FREEZE'

def sha256(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def f(r,k):
    try:return float(r[k])
    except Exception:return float('nan')
def sgn(x): return 1 if x>0 else -1 if x<0 else 0

def load_rows(p):
    with open(p,newline='',encoding='utf-8') as h: rows=list(csv.DictReader(h))
    req={'timestamp','session','banknifty_open','banknifty_high','banknifty_low','banknifty_close','nifty_ret_1_bps','sensex_ret_1_bps'}
    if not rows or not req.issubset(rows[0]): raise ValueError('dataset_schema_mismatch')
    return rows

def grid(g,horizons):
    keys=sorted(g);vals=[g[k] for k in keys]
    for combo in itertools.product(*vals):
        base=dict(zip(keys,combo))
        for h in horizons: yield {**base,'horizon_bars':int(h)}

def geom(r):
    o,h,l,c=(f(r,k) for k in ('banknifty_open','banknifty_high','banknifty_low','banknifty_close'))
    if not all(math.isfinite(x) for x in (o,h,l,c)) or min(o,h,l,c)<=0 or h<l:return None
    rng=max(h-l,0.0);mid=(h+l)/2.0
    rbps=(rng/o)*10000.0 if o>0 else 0.0
    body=c-o;body_abs=abs(body);body_frac=(body_abs/rng) if rng>0 else 0.0
    upper=h-max(o,c);lower=min(o,c)-l
    upper_frac=(upper/rng) if rng>0 else 0.0;lower_frac=(lower/rng) if rng>0 else 0.0
    close_from_high=(h-c)/rng if rng>0 else 1.0;close_from_low=(c-l)/rng if rng>0 else 1.0
    return {'o':o,'h':h,'l':l,'c':c,'rbps':rbps,'body':body,'body_frac':body_frac,'upper_frac':upper_frac,'lower_frac':lower_frac,'close_from_high':close_from_high,'close_from_low':close_from_low,'mid':mid}

def direction(pid,rows,i,c):
    g=geom(rows[i]);
    if g is None:return 0
    if pid=='HUNT_V3_RANGE_EXPANSION_STRONG_CLOSE_CONTINUATION':
        d=sgn(g['body'])
        if d==0 or g['rbps']<c['range_bps'] or g['body_frac']<c['body_fraction']:return 0
        extreme_ok=(g['close_from_high']<=c['close_extreme_fraction']) if d>0 else (g['close_from_low']<=c['close_extreme_fraction'])
        return d if extreme_ok else 0
    if pid=='HUNT_V3_WICK_REJECTION_REVERSAL':
        if g['rbps']<c['range_bps']:return 0
        if g['upper_frac']>=c['wick_fraction'] and g['c']<g['mid']:return -1
        if g['lower_frac']>=c['wick_fraction'] and g['c']>g['mid']:return 1
        return 0
    if pid=='HUNT_V3_TWO_BAR_COMPRESSION_BREAKOUT':
        if i<2 or rows[i-1]['session']!=rows[i]['session'] or rows[i-2]['session']!=rows[i]['session']:return 0
        g1=geom(rows[i-1]);g2=geom(rows[i-2])
        if g1 is None or g2 is None or g1['rbps']>c['compression_bps'] or g2['rbps']>c['compression_bps']:return 0
        ph=max(g1['h'],g2['h']);pl=min(g1['l'],g2['l']);base=max(rows[i-1] and g1['c'],1e-9)
        up=(g['c']-ph)/base*10000.0;dn=(pl-g['c'])/base*10000.0
        if up>=c['breakout_bps']:return 1
        if dn>=c['breakout_bps']:return -1
        return 0
    if pid=='HUNT_V3_FAILED_RANGE_ESCAPE_REVERSAL':
        if i<1 or rows[i-1]['session']!=rows[i]['session']:return 0
        p=geom(rows[i-1])
        if p is None or p['rbps']<c['prior_range_bps']:return 0
        base=max(p['c'],1e-9)
        up=(g['h']-p['h'])/base*10000.0;dn=(p['l']-g['l'])/base*10000.0
        inside=p['l']<=g['c']<=p['h']
        if not inside:return 0
        if up>=c['escape_bps'] and dn<c['escape_bps']:return -1
        if dn>=c['escape_bps'] and up<c['escape_bps']:return 1
        return 0
    if pid=='HUNT_V3_LEADER_CONFIRMED_STRONG_CLOSE':
        nr=f(rows[i],'nifty_ret_1_bps');sr=f(rows[i],'sensex_ret_1_bps');d=sgn(g['body'])
        if not all(math.isfinite(x) for x in (nr,sr)) or d==0:return 0
        if sgn(nr)!=d or sgn(sr)!=d:return 0
        if min(abs(nr),abs(sr))<c['leader_bps'] or g['rbps']<c['range_bps'] or g['body_frac']<c['body_fraction']:return 0
        return d
    raise ValueError('unknown_passport:'+pid)

def evaluate(rows,idxs,pid,c,cost):
    rets=[];i=min(idxs) if idxs else 0;end=max(idxs) if idxs else -1
    while i<=end:
        if i not in idxs:i+=1;continue
        d=direction(pid,rows,i,c)
        if not d:i+=1;continue
        entry=i+1;exit_=entry+c['horizon_bars'];sess=rows[i]['session']
        if entry not in idxs or exit_ not in idxs or exit_>end or rows[entry]['session']!=sess or rows[exit_]['session']!=sess:i+=1;continue
        p0=f(rows[entry],'banknifty_close');p1=f(rows[exit_],'banknifty_close')
        if not(math.isfinite(p0) and math.isfinite(p1) and p0>0):i+=1;continue
        rets.append(d*((p1-p0)/p0)*10000.0-float(cost));i=exit_+1
    if not rets:return {'trades':0,'mean_net_bps':None,'win_rate':None,'total_net_bps':None}
    return {'trades':len(rets),'mean_net_bps':mean(rets),'win_rate':sum(x>0 for x in rets)/len(rets),'total_net_bps':sum(rets)}

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');ap.add_argument('--dataset',default='research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv');ap.add_argument('--freeze',default='research/strategy_certification/passports/HUNT_V3_GENERATION_FREEZE.json');ap.add_argument('--output',default='research/evidence/strategy_certification/HUNT_V3_DEVELOPMENT_SCREEN.json');a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve();ds=root/a.dataset;fp=root/a.freeze;out=root/a.output
    res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'validation_accessed':False,'holdout_accessed':False}
    try:
        fr=json.loads(fp.read_text())
        if fr.get('generation_id')!=EXPECTED_GENERATION:raise ValueError('generation_id_mismatch')
        if fr.get('dataset_sha256')!=EXPECTED_DATASET_SHA or sha256(ds)!=EXPECTED_DATASET_SHA:raise ValueError('dataset_hash_mismatch')
        rows=load_rows(ds);sessions=sorted({r['session'] for r in rows});nd=int(len(sessions)*fr['split_contract']['development_fraction']);dev=set(sessions[:nd]);idx={i for i,r in enumerate(rows) if r['session'] in dev};horizons=fr['execution_contract']['development_horizons_bars'];cost=fr['execution_contract']['base_round_trip_cost_bps'];gate=fr['development_gate'];cands=[]
        for p in fr['passports']:
            arr=[]
            for c in grid(p['grid'],horizons):arr.append({'config':c,'metrics':evaluate(rows,idx,p['passport_id'],c,cost)})
            elig=[x for x in arr if x['metrics']['trades']>=gate['minimum_trades'] and x['metrics']['mean_net_bps'] is not None and x['metrics']['mean_net_bps']>0]
            elig.sort(key=lambda x:(x['metrics']['mean_net_bps'],x['metrics']['trades']),reverse=True);nom=elig[0] if elig else None
            cands.append({'passport_id':p['passport_id'],'configs_tested':len(arr),'development_status':'NOMINATED_FOR_VALIDATION' if nom else 'REJECTED_IN_DEVELOPMENT','nomination':nom,'all_development_results':arr})
        nv=int(len(sessions)*fr['split_contract']['validation_fraction'])
        res.update({'status':'DEVELOPMENT_SCREEN_COMPLETE','dataset_sha256':sha256(ds),'generation_sha256':sha256(fp),'sessions_total':len(sessions),'development_sessions':nd,'validation_sessions_reserved':nv,'holdout_sessions_reserved':len(sessions)-nd-nv,'candidates':cands,'nominated_count':sum(x['development_status']=='NOMINATED_FOR_VALIDATION' for x in cands),'parameters_tuned':False})
    except Exception as e:res['error']=f'{type(e).__name__}:{e}'
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n');print(json.dumps(res,indent=2));return 0 if res['status']=='DEVELOPMENT_SCREEN_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
