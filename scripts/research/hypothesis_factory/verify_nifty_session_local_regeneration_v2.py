#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,importlib.util,json,math,sys
from collections import Counter,defaultdict
from pathlib import Path
from statistics import mean,median

DATASET_SHA='6a145d4d17f124f9dc8ee272c5a19ca98988873a14b294765f44a27284d8b7e8'
EVIDENCE='research/evidence/strategy_certification/NIFTY_SESSION_LOCAL_REGENERATION_V2.json'

def sha256(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:raise RuntimeError(f'module_load_failed:{name}')
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def load_rows(p:Path):
    with p.open(newline='',encoding='utf-8') as h:raw=list(csv.DictReader(h))
    out=[]
    for r in raw:
        ts=r['timestamp'];sess=r.get('session') or ts[:10]
        o,hi,lo,c=(float(r[k]) for k in ('open','high','low','close'))
        if not all(math.isfinite(x) and x>0 for x in (o,hi,lo,c)) or hi<lo:continue
        out.append({'timestamp':ts,'session':sess,'open':o,'high':hi,'low':lo,'close':c})
    out.sort(key=lambda x:x['timestamp']);return out

def bps(a,b):return (b/a-1.0)*10000.0
def summ(xs):
    ys=[float(x) for x in xs if x is not None and math.isfinite(float(x))]
    return {'n':len(ys),'mean':mean(ys) if ys else None,'median':median(ys) if ys else None}
def rate(xs,t):
    ys=[float(x) for x in xs if x is not None and math.isfinite(float(x))]
    return None if not ys else sum(x>=t for x in ys)/len(ys)
def close(a,b,tol=1e-10):
    if a is None or b is None:return a is b
    return abs(float(a)-float(b))<=tol*max(1.0,abs(float(a)),abs(float(b)))

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve();data_p=root/'research/hypotheses/historical_corpus/kite_nifty_cache_v2/canonical/NIFTY.csv';ev_p=root/EVIDENCE
    res={'schema_version':1,'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'locked_outcomes_accessed':False}
    checks=[]
    def ck(name,ok,detail=None):checks.append({'check':name,'status':'PASS' if ok else 'FAIL','detail':detail})
    try:
        if sha256(data_p)!=DATASET_SHA:raise ValueError('dataset_hash_mismatch')
        expected=json.loads(ev_p.read_text())
        atlas=load('nifty_regen_atlas',root/'scripts/research/hypothesis_factory/build_market_structure_pattern_atlas_v1.py')
        motifmod=load('nifty_regen_motif',root/'scripts/research/hypothesis_factory/build_market_structure_motif_atlas_v1.py')
        rows=load_rows(data_p);sessions=sorted({r['session'] for r in rows});cut=int(len(sessions)*0.8);dev=set(sessions[:cut]);locked=set(sessions[cut:]);by_ts={r['timestamp']:i for i,r in enumerate(rows)}
        raw_piv=atlas.confirm_pivots(rows,35.0);piv=atlas.classify_swings(raw_piv,15.0);motifs=motifmod.swing_motifs(piv,15.0)
        cross=[m for m in motifs if len({p.get('pivot_timestamp','')[:10] for p in m.get('pivots',[])})!=1]
        ck('ZERO_CROSS_SESSION_SWING_MOTIFS',not cross,len(cross))
        ck('SESSION_LOCAL_SWING_LABELS',all(p.get('session') for p in piv),'all pivots carry session')
        counts=dict(sorted(Counter(m['motif'] for m in motifs).items()))
        ck('CORRECTED_MOTIF_COUNTS_MATCH',counts==expected['structure']['corrected_swing_motif_counts'],counts)
        ck('SESSION_SPLIT_MATCH',len(sessions)==493 and len(dev)==394 and len(locked)==99 and sessions[cut]=='2026-02-10',{'sessions':len(sessions),'dev':len(dev),'locked':len(locked),'first_locked':sessions[cut]})

        # Build development outcomes only. Locked sessions are skipped before any future price is read.
        rev_dirs={'DOUBLE_BOTTOM_STRUCTURE':'UP','DOUBLE_TOP_STRUCTURE':'DOWN'}
        swing_names=['UPTREND_CONTINUATION_SWING','DOWNTREND_CONTINUATION_SWING','UPTREND_FAILURE_TO_HIGHER_LOW','DOWNTREND_FAILURE_TO_LOWER_HIGH']
        rev=defaultdict(list);sw=defaultdict(list);locked_skipped=0
        for m in motifs:
            if m['motif'] not in set(rev_dirs)|set(swing_names):continue
            ci=by_ts[m['confirmation_timestamp']];sess=rows[ci]['session']
            if sess in locked:
                locked_skipped+=1;continue
            if sess not in dev:raise ValueError('motif_outside_split')
            base=rows[ci]['close'];rets={}
            for h in (1,3,6,12):
                j=ci+h;rets[h]=bps(base,rows[j]['close']) if j<len(rows) and rows[j]['session']==sess else None
            hi=base;lo=base
            for j in range(ci+1,min(len(rows),ci+13)):
                if rows[j]['session']!=sess:break
                hi=max(hi,rows[j]['high']);lo=min(lo,rows[j]['low'])
            up=bps(base,hi);down=-bps(base,lo)
            if m['motif'] in rev_dirs:
                direction=rev_dirs[m['motif']];signed={h:(rets[h] if direction=='UP' or rets[h] is None else -rets[h]) for h in rets}
                fav=up if direction=='UP' else down;adv=down if direction=='UP' else up
                rev[m['motif']].append({'ret':signed,'fav':fav,'adv':adv})
            if m['motif'] in swing_names:sw[m['motif']].append({'ret':rets,'up':up,'down':down})

        for name,direction in rev_dirs.items():
            es=rev[name];dr6=summ([e['ret'][6] for e in es]);dr12=summ([e['ret'][12] for e in es]);f20=rate([e['fav'] for e in es],20);a20=rate([e['adv'] for e in es],20);f30=rate([e['fav'] for e in es],30);a30=rate([e['adv'] for e in es],30)
            reasons=[]
            if len(es)<30:reasons.append('INSUFFICIENT_EPISODES')
            if dr6['median'] is None or dr6['median']<=0:reasons.append('NONPOSITIVE_DIRECTIONAL_MEDIAN_RET6')
            if dr12['median'] is None or dr12['median']<=0:reasons.append('NONPOSITIVE_DIRECTIONAL_MEDIAN_RET12')
            if f20 is None or a20 is None or f20<=a20:reasons.append('NO_20BPS_FAVORABLE_ASYMMETRY')
            if f30 is None or a30 is None or f30<a30:reasons.append('NO_30BPS_FAVORABLE_ASYMMETRY')
            ex=expected['reversal_family_v1_gates_replayed_unchanged']['motifs'][name]
            ck(f'{name}_EPISODES_MATCH',len(es)==ex['episodes'],len(es))
            ck(f'{name}_VERDICT_MATCH',reasons==ex['reasons'],reasons)
            ck(f'{name}_RET6_MEDIAN_MATCH',close(dr6['median'],ex['directional_returns_bps']['6']['median']),dr6['median'])
            ck(f'{name}_RET12_MEDIAN_MATCH',close(dr12['median'],ex['directional_returns_bps']['12']['median']),dr12['median'])

        for name in swing_names:
            es=sw[name];r6=summ([e['ret'][6] for e in es]);r12=summ([e['ret'][12] for e in es]);u20=rate([e['up'] for e in es],20);d20=rate([e['down'] for e in es],20);u30=rate([e['up'] for e in es],30);d30=rate([e['down'] for e in es],30)
            reasons=[];direction=None
            if len(es)<30:reasons.append('INSUFFICIENT_EPISODES')
            m6,m12=r6['median'],r12['median']
            if m6 is None or abs(m6)<3:reasons.append('RET6_MEDIAN_MAGNITUDE_GATE_FAIL')
            if m12 is None or abs(m12)<3:reasons.append('RET12_MEDIAN_MAGNITUDE_GATE_FAIL')
            if m6 is None or m12 is None or m6*m12<=0:reasons.append('RET6_RET12_SIGN_CONSISTENCY_FAIL')
            if m6 is not None and m12 is not None and m6*m12>0 and abs(m6)>=3 and abs(m12)>=3:direction='UP' if m6>0 else 'DOWN'
            if direction=='UP':
                if u20-d20<0.15:reasons.append('20BPS_EXCURSION_ASYMMETRY_FAIL')
                if u30-d30<0.10:reasons.append('30BPS_EXCURSION_ASYMMETRY_FAIL')
            elif direction=='DOWN':
                if d20-u20<0.15:reasons.append('20BPS_EXCURSION_ASYMMETRY_FAIL')
                if d30-u30<0.10:reasons.append('30BPS_EXCURSION_ASYMMETRY_FAIL')
            elif 'RET6_RET12_SIGN_CONSISTENCY_FAIL' not in reasons:reasons.append('NO_DIRECTION_INFERRED')
            ex=expected['swing_transition_family_v1_gates_replayed_unchanged']['motifs'][name]
            ck(f'{name}_EPISODES_MATCH',len(es)==ex['episodes'],len(es))
            ck(f'{name}_VERDICT_MATCH',reasons==ex['reasons'],reasons)
            ck(f'{name}_RET6_MEDIAN_MATCH',close(r6['median'],ex['ret6_bps']['median']),r6['median'])
            ck(f'{name}_RET12_MEDIAN_MATCH',close(r12['median'],ex['ret12_bps']['median']),r12['median'])

        ck('NO_CORRECTED_SURVIVOR',expected.get('final_verdict')=='NO_CORRECTED_NIFTY_DEVELOPMENT_SURVIVOR')
        ck('LOCKED_OUTCOMES_NOT_ACCESSED',True,{'locked_motifs_skipped_before_outcome':locked_skipped})
        failed=[x['check'] for x in checks if x['status']!='PASS']
        res.update({'status':'NIFTY_SESSION_LOCAL_REGENERATION_VERIFY_PASS' if not failed else 'NIFTY_SESSION_LOCAL_REGENERATION_VERIFY_FAIL','checks_total':len(checks),'checks_passed':len(checks)-len(failed),'checks_failed':len(failed),'failed_checks':failed,'checks':checks,'corrected_motif_counts':counts,'development_sessions':len(dev),'locked_sessions':len(locked),'locked_motifs_skipped_before_outcome':locked_skipped,'interpretation':'Independent recomputation of repaired session-local NIFTY swing motifs and unchanged V1 development gates. Locked-session outcomes are skipped before forward data is read.'})
    except Exception as e:res.update({'error':f'{type(e).__name__}:{e}','checks':checks})
    print(json.dumps(res,indent=2,sort_keys=True));return 0 if res.get('status')=='NIFTY_SESSION_LOCAL_REGENERATION_VERIFY_PASS' else 2
if __name__=='__main__':raise SystemExit(main())
