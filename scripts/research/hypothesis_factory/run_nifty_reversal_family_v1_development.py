#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,json,math
from collections import defaultdict
from pathlib import Path
from statistics import mean,median

FAMILY='NIFTY_REVERSAL_FAMILY_V1'
EXPECTED_DATASET_SHA='6a145d4d17f124f9dc8ee272c5a19ca98988873a14b294765f44a27284d8b7e8'
EXPECTED_MOTIFS_SHA='6daad77489fe032d8b78354ec4a00e89f69975df7085d09fd2c50c492a1953ec'
EXPECTED_SCALE_SHA='2e24e0e91b6de19f7c0efa5c7c7b8d6c36c39fc602377440e323a5888a18cdcd'

def sha256(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()

def load_rows(p:Path):
    with p.open(newline='',encoding='utf-8') as h:rows=list(csv.DictReader(h))
    req={'timestamp','open','high','low','close'}
    if not rows or not req.issubset(rows[0]):raise ValueError('dataset_schema_mismatch')
    out=[]
    for r in rows:
        ts=r.get('timestamp');sess=r.get('session') or (ts[:10] if ts else None)
        if not ts or not sess:continue
        try:o,h,l,c=(float(r[k]) for k in ('open','high','low','close'))
        except:continue
        if not all(math.isfinite(x) and x>0 for x in (o,h,l,c)) or h<l:continue
        out.append({'timestamp':ts,'session':sess,'open':o,'high':h,'low':l,'close':c})
    out.sort(key=lambda x:x['timestamp'])
    return out

def load_jsonl(p:Path):
    out=[]
    with p.open(encoding='utf-8') as h:
        for line in h:
            if line.strip():out.append(json.loads(line))
    return out

def bps(a,b):return (b/a-1.0)*10000.0

def summarize(xs):
    vals=[float(x) for x in xs if x is not None and math.isfinite(float(x))]
    return {'n':len(vals),'mean':None if not vals else mean(vals),'median':None if not vals else median(vals)}

def rate(xs,pred):
    vals=[float(x) for x in xs if x is not None and math.isfinite(float(x))]
    return None if not vals else sum(1 for x in vals if pred(x))/len(vals)

def directional_outcome(rows,ci,direction,horizons):
    sess=rows[ci]['session'];c0=rows[ci]['close'];fwd=[]
    rets={int(h):None for h in horizons}
    for j in range(ci+1,min(len(rows),ci+max(horizons)+1)):
        if rows[j]['session']!=sess:break
        step=j-ci;up=bps(c0,rows[j]['high']);down=bps(c0,rows[j]['low']);fwd.append((up,down))
        if step in rets:rets[step]=bps(c0,rows[j]['close'])
    max_up=max((x[0] for x in fwd),default=None);min_down=min((x[1] for x in fwd),default=None)
    if direction=='UP':
        fav=max_up;adv=None if min_down is None else -min_down
        signed={h:rets[h] for h in rets}
    elif direction=='DOWN':
        fav=None if min_down is None else -min_down;adv=max_up
        signed={h:(None if rets[h] is None else -rets[h]) for h in rets}
    else:raise ValueError('unsupported_direction')
    return {'directional_ret_bps':signed,'favorable_excursion_bps':fav,'adverse_excursion_bps':adv}

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve()
    freeze_p=root/'research/strategy_certification/NIFTY_REVERSAL_FAMILY_V1_FREEZE.json'
    scale_p=root/'research/strategy_certification/NIFTY_STRUCTURE_SCALE_V1.json'
    data_p=root/'research/hypotheses/historical_corpus/kite_nifty_cache_v2/canonical/NIFTY.csv'
    motifs_p=root/'research/evidence/market_structure_pattern_atlas_v1/NIFTY_motifs.jsonl'
    out_p=root/'research/evidence/strategy_certification/NIFTY_REVERSAL_FAMILY_V1_DEVELOPMENT.json'
    ep_p=root/'research/evidence/strategy_certification/NIFTY_REVERSAL_FAMILY_V1_DEVELOPMENT_EPISODES.jsonl'
    res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'locked_outcomes_accessed':False}
    try:
        freeze=json.loads(freeze_p.read_text())
        if freeze.get('family_id')!=FAMILY:raise ValueError('family_id_mismatch')
        if sha256(data_p)!=EXPECTED_DATASET_SHA or freeze.get('dataset_sha256')!=EXPECTED_DATASET_SHA:raise ValueError('dataset_hash_mismatch')
        if sha256(motifs_p)!=EXPECTED_MOTIFS_SHA or freeze.get('motifs_sha256')!=EXPECTED_MOTIFS_SHA:raise ValueError('motifs_hash_mismatch')
        if sha256(scale_p)!=EXPECTED_SCALE_SHA or freeze.get('scale_sha256')!=EXPECTED_SCALE_SHA:raise ValueError('scale_hash_mismatch')
        if freeze.get('locked_outcomes_must_remain_unaccessed_during_development') is not True:raise ValueError('locked_policy_missing')
        rows=load_rows(data_p);sessions=sorted({r['session'] for r in rows});cut=int(len(sessions)*float(freeze['development_fraction']))
        dev=set(sessions[:cut]);locked=set(sessions[cut:])
        if dev & locked:raise ValueError('session_split_overlap')
        by_ts={r['timestamp']:i for i,r in enumerate(rows)}
        family_map={x['motif']:x['direction'] for x in freeze['families']}
        motifs=[m for m in load_jsonl(motifs_p) if m.get('motif') in family_map]
        horizons=[int(x) for x in freeze['fixed_horizons_bars']];thresholds=[float(x) for x in freeze['fixed_excursion_thresholds_bps']]
        episodes=[];locked_motifs_skipped=0;missing_ts=0
        for m in motifs:
            ci=by_ts.get(m.get('confirmation_timestamp'))
            if ci is None:missing_ts+=1;continue
            sess=rows[ci]['session']
            if sess in locked:
                locked_motifs_skipped+=1
                continue
            if sess not in dev:raise ValueError('motif_session_outside_split')
            direction=family_map[m['motif']]
            o=directional_outcome(rows,ci,direction,horizons)
            episodes.append({'motif':m['motif'],'direction':direction,'session':sess,'confirmation_timestamp':m['confirmation_timestamp'],**o})
        groups=defaultdict(list)
        for e in episodes:groups[e['motif']].append(e)
        gate=freeze['development_gate'];summaries={};survivors=[]
        for motif,direction in family_map.items():
            es=groups.get(motif,[]);reasons=[]
            dr={str(h):summarize([e['directional_ret_bps'].get(h) for e in es]) for h in horizons}
            fav={str(int(t)):rate([e['favorable_excursion_bps'] for e in es],lambda x,t=t:x>=t) for t in thresholds}
            adv={str(int(t)):rate([e['adverse_excursion_bps'] for e in es],lambda x,t=t:x>=t) for t in thresholds}
            if len(es)<int(gate['minimum_episodes_per_motif']):reasons.append('INSUFFICIENT_EPISODES')
            if gate['require_directional_median_ret6_positive'] and (dr.get('6',{}).get('median') is None or dr['6']['median']<=0):reasons.append('NONPOSITIVE_DIRECTIONAL_MEDIAN_RET6')
            if gate['require_directional_median_ret12_positive'] and (dr.get('12',{}).get('median') is None or dr['12']['median']<=0):reasons.append('NONPOSITIVE_DIRECTIONAL_MEDIAN_RET12')
            if gate['require_favorable_20bps_rate_gt_adverse_20bps_rate'] and (fav.get('20') is None or adv.get('20') is None or fav['20']<=adv['20']):reasons.append('NO_20BPS_FAVORABLE_ASYMMETRY')
            if gate['require_favorable_30bps_rate_gte_adverse_30bps_rate'] and (fav.get('30') is None or adv.get('30') is None or fav['30']<adv['30']):reasons.append('NO_30BPS_FAVORABLE_ASYMMETRY')
            verdict='DEVELOPMENT_STRUCTURE_SCREEN_PASS' if not reasons else 'DEVELOPMENT_STRUCTURE_SCREEN_FAIL'
            if not reasons:survivors.append(motif)
            summaries[motif]={'direction':direction,'episodes':len(es),'directional_returns_bps':dr,'favorable_excursion_rates':fav,'adverse_excursion_rates':adv,'favorable_excursion_bps':summarize([e['favorable_excursion_bps'] for e in es]),'adverse_excursion_bps':summarize([e['adverse_excursion_bps'] for e in es]),'verdict':verdict,'reasons':reasons}
        ep_p.parent.mkdir(parents=True,exist_ok=True);ep_p.write_text(''.join(json.dumps(e,sort_keys=True)+'\n' for e in episodes),encoding='utf-8')
        res.update({'status':'NIFTY_REVERSAL_FAMILY_DEVELOPMENT_COMPLETE','family_id':FAMILY,'freeze_sha256':sha256(freeze_p),'scale_sha256':sha256(scale_p),'dataset_sha256':sha256(data_p),'motifs_sha256':sha256(motifs_p),'sessions_total':len(sessions),'development_sessions':len(dev),'locked_sessions':len(locked),'first_locked_session':sessions[cut] if cut<len(sessions) else None,'motifs_received':len(motifs),'development_episodes':len(episodes),'locked_family_motifs_skipped_without_outcome_computation':locked_motifs_skipped,'motifs_missing_timestamp_match':missing_ts,'motif_summaries':summaries,'surviving_motifs':survivors,'survivor_count':len(survivors),'next_action':'ADVANCE_SURVIVORS_TO_BOUNDED_ANATOMY' if survivors else 'CLOSE_REVERSAL_FAMILY_NO_DEVELOPMENT_ASYMMETRY','development_episodes_path':str(ep_p),'development_episodes_sha256':sha256(ep_p),'locked_outcomes_accessed':False,'cost_slippage_applied':False,'cost_slippage_reason':'Structural index-outcome stage only; execution costs become mandatory after a causal entry/exit strategy is frozen.','interpretation':'Symmetric development-only NIFTY double-bottom/double-top structural outcome screen. Final 20% session outcomes are not computed or read. A PASS is not an edge or strategy certification.'})
    except Exception as e:res['error']=f'{type(e).__name__}:{e}'
    out_p.parent.mkdir(parents=True,exist_ok=True);out_p.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(res,indent=2));return 0 if res.get('status')=='NIFTY_REVERSAL_FAMILY_DEVELOPMENT_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
