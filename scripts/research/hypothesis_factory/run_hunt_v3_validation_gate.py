#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,json,math
from pathlib import Path
from statistics import mean

EXPECTED_DATASET_SHA='66ddbfead966388262b9a1e49937fb227b711ce32f70eaf715a93a5e32572b32'
EXPECTED_GENERATION_SHA='904bf1d086b1d3b81942faae1ae63d31c9f1fcd92cc82a7090737605e703f819'
EXPECTED_POLICY='HUNT_V3_VALIDATION_GATE'

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

def geom(r):
    o,h,l,c=(f(r,k) for k in ('banknifty_open','banknifty_high','banknifty_low','banknifty_close'))
    if not all(math.isfinite(x) for x in (o,h,l,c)) or min(o,h,l,c)<=0 or h<l:return None
    rng=max(h-l,0.0);mid=(h+l)/2.0
    rbps=(rng/o)*10000.0 if o>0 else 0.0
    upper=h-max(o,c);lower=min(o,c)-l
    upper_frac=(upper/rng) if rng>0 else 0.0;lower_frac=(lower/rng) if rng>0 else 0.0
    return {'o':o,'h':h,'l':l,'c':c,'rbps':rbps,'upper_frac':upper_frac,'lower_frac':lower_frac,'mid':mid}

def direction(pid,rows,i,c):
    g=geom(rows[i])
    if g is None:return 0
    if pid=='HUNT_V3_WICK_REJECTION_REVERSAL':
        if g['rbps']<c['range_bps']:return 0
        if g['upper_frac']>=c['wick_fraction'] and g['c']<g['mid']:return -1
        if g['lower_frac']>=c['wick_fraction'] and g['c']>g['mid']:return 1
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
    raise ValueError('unknown_passport:'+pid)

def evaluate(rows,idxs,pid,c,cost):
    rets=[];i=min(idxs) if idxs else 0;end=max(idxs) if idxs else -1
    while i<=end:
        if i not in idxs:i+=1;continue
        d=direction(pid,rows,i,c)
        if not d:i+=1;continue
        entry=i+1;exit_=entry+int(c['horizon_bars']);sess=rows[i]['session']
        if entry not in idxs or exit_ not in idxs or exit_>end or rows[entry]['session']!=sess or rows[exit_]['session']!=sess:i+=1;continue
        p0=f(rows[entry],'banknifty_close');p1=f(rows[exit_],'banknifty_close')
        if not(math.isfinite(p0) and math.isfinite(p1) and p0>0):i+=1;continue
        rets.append(d*((p1-p0)/p0)*10000.0-float(cost));i=exit_+1
    if not rets:return {'trades':0,'mean_net_bps':None,'win_rate':None,'total_net_bps':None}
    return {'trades':len(rets),'mean_net_bps':mean(rets),'win_rate':sum(x>0 for x in rets)/len(rets),'total_net_bps':sum(rets)}

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');ap.add_argument('--dataset',default='research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv');ap.add_argument('--generation',default='research/strategy_certification/passports/HUNT_V3_GENERATION_FREEZE.json');ap.add_argument('--development',default='research/evidence/strategy_certification/HUNT_V3_DEVELOPMENT_SCREEN.json');ap.add_argument('--policy',default='research/strategy_certification/passports/HUNT_V3_VALIDATION_GATE.json');ap.add_argument('--output',default='research/evidence/strategy_certification/HUNT_V3_VALIDATION_RESULT.json');a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve();ds=root/a.dataset;gp=root/a.generation;dp=root/a.development;pp=root/a.policy;out=root/a.output
    res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'holdout_outcomes_accessed':False}
    try:
        pol=json.loads(pp.read_text());dev=json.loads(dp.read_text())
        if pol.get('policy_id')!=EXPECTED_POLICY:raise ValueError('policy_id_mismatch')
        if pol.get('generation_sha256')!=EXPECTED_GENERATION_SHA or sha256(gp)!=EXPECTED_GENERATION_SHA:raise ValueError('generation_hash_mismatch')
        if pol.get('dataset_sha256')!=EXPECTED_DATASET_SHA or sha256(ds)!=EXPECTED_DATASET_SHA:raise ValueError('dataset_hash_mismatch')
        if dev.get('status')!='DEVELOPMENT_SCREEN_COMPLETE' or dev.get('validation_accessed') is not False or dev.get('holdout_accessed') is not False:raise ValueError('development_evidence_state_invalid')
        if dev.get('generation_sha256')!=EXPECTED_GENERATION_SHA or dev.get('dataset_sha256')!=EXPECTED_DATASET_SHA:raise ValueError('development_binding_mismatch')
        if dev.get('nominated_count')!=2:raise ValueError('development_nomination_count_mismatch')
        dev_by={x['passport_id']:x for x in dev.get('candidates',[])}
        for n in pol['nominations']:
            d=dev_by.get(n['passport_id'])
            if not d or d.get('development_status')!='NOMINATED_FOR_VALIDATION':raise ValueError('nomination_missing:'+n['passport_id'])
            if d.get('nomination',{}).get('config')!=n['configuration']:raise ValueError('nomination_config_mismatch:'+n['passport_id'])
            if d.get('nomination',{}).get('metrics')!=n['development_metrics']:raise ValueError('nomination_metrics_mismatch:'+n['passport_id'])
        rows=load_rows(ds);sessions=sorted({r['session'] for r in rows});nd=int(len(sessions)*0.6);nv=int(len(sessions)*0.2);val=set(sessions[nd:nd+nv]);idx={i for i,r in enumerate(rows) if r['session'] in val};gate=pol['validation_gate'];cands=[]
        for n in pol['nominations']:
            m=evaluate(rows,idx,n['passport_id'],n['configuration'],gate['base_round_trip_cost_bps'])
            reasons=[]
            if m['trades']<gate['minimum_trades']:reasons.append('INSUFFICIENT_VALIDATION_TRADES')
            if m['mean_net_bps'] is None or m['mean_net_bps']<=0:reasons.append('NONPOSITIVE_VALIDATION_MEAN')
            if m['total_net_bps'] is None or m['total_net_bps']<=0:reasons.append('NONPOSITIVE_VALIDATION_TOTAL')
            verdict='VALIDATION_PASS' if not reasons else 'VALIDATION_FAIL'
            cands.append({'passport_id':n['passport_id'],'configuration':n['configuration'],'verdict':verdict,'reasons':reasons,'metrics':m})
        adv=[x['passport_id'] for x in cands if x['verdict']=='VALIDATION_PASS']
        res.update({'status':'VALIDATION_FAMILY_COMPLETE','policy_sha256':sha256(pp),'development_evidence_sha256':sha256(dp),'generation_sha256':sha256(gp),'dataset_sha256':sha256(ds),'sessions_total':len(sessions),'validation_sessions':nv,'candidates_evaluated':len(cands),'candidates':cands,'advanced_count':len(adv),'advanced_passport_ids':adv,'parameters_tuned':False,'next_action':'PRE_HOLDOUT_ROBUSTNESS_AND_NEGATIVE_CONTROLS' if adv else 'CLOSE_HUNT_V3_NO_CANDIDATE_ADVANCED'})
    except Exception as e:res['error']=f'{type(e).__name__}:{e}'
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n');print(json.dumps(res,indent=2));return 0 if res['status']=='VALIDATION_FAMILY_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
