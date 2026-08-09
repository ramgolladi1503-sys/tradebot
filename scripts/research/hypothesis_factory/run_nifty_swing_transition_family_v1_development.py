#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,json,math
from collections import defaultdict
from pathlib import Path
from statistics import mean,median

DATASET_SHA='6a145d4d17f124f9dc8ee272c5a19ca98988873a14b294765f44a27284d8b7e8'
MOTIFS_SHA='6daad77489fe032d8b78354ec4a00e89f69975df7085d09fd2c50c492a1953ec'
SCALE_SHA='2e24e0e91b6de19f7c0efa5c7c7b8d6c36c39fc602377440e323a5888a18cdcd'
FAMILY='NIFTY_SWING_TRANSITION_FAMILY_V1'

def sha256(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def bps(a,b):return (b/a-1.0)*10000.0 if a and a>0 else None

def load_rows(p:Path):
    with p.open(newline='',encoding='utf-8') as h:rs=list(csv.DictReader(h))
    req={'timestamp','open','high','low','close'}
    if not rs or not req.issubset(rs[0]):raise ValueError('dataset_schema_mismatch')
    out=[]
    for r in rs:
        try:o,h,l,c=(float(r[k]) for k in ('open','high','low','close'))
        except Exception:continue
        ts=r['timestamp'];sess=r.get('session') or ts[:10]
        if min(o,h,l,c)<=0 or h<l:continue
        out.append({'timestamp':ts,'session':sess,'open':o,'high':h,'low':l,'close':c})
    out.sort(key=lambda x:x['timestamp']);return out

def load_jsonl(p:Path):
    out=[]
    with p.open(encoding='utf-8') as h:
        for line in h:
            if line.strip():out.append(json.loads(line))
    return out

def summ(xs):
    ys=[x for x in xs if x is not None and math.isfinite(x)]
    return {'n':len(ys),'mean':mean(ys) if ys else None,'median':median(ys) if ys else None}

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve()
    dataset=root/'research/hypotheses/historical_corpus/kite_nifty_cache_v2/canonical/NIFTY.csv'
    motifs_p=root/'research/evidence/market_structure_pattern_atlas_v1/NIFTY_motifs.jsonl'
    freeze_p=root/'research/strategy_certification/NIFTY_SWING_TRANSITION_FAMILY_V1_FREEZE.json'
    out_p=root/'research/evidence/strategy_certification/NIFTY_SWING_TRANSITION_FAMILY_V1_DEVELOPMENT.json'
    ep_p=root/'research/evidence/strategy_certification/NIFTY_SWING_TRANSITION_FAMILY_V1_DEVELOPMENT_EPISODES.jsonl'
    res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'locked_outcomes_accessed':False,'family_id':FAMILY}
    try:
        if sha256(dataset)!=DATASET_SHA:raise ValueError('dataset_hash_mismatch')
        if sha256(motifs_p)!=MOTIFS_SHA:raise ValueError('motifs_hash_mismatch')
        freeze=json.loads(freeze_p.read_text())
        if freeze.get('family_id')!=FAMILY:raise ValueError('freeze_family_mismatch')
        if freeze.get('dataset_sha256')!=DATASET_SHA or freeze.get('motifs_sha256')!=MOTIFS_SHA or freeze.get('scale_sha256')!=SCALE_SHA:raise ValueError('freeze_binding_mismatch')
        rows=load_rows(dataset);motifs=load_jsonl(motifs_p);sessions=sorted({r['session'] for r in rows})
        cut=int(len(sessions)*float(freeze['development_fraction']));dev=set(sessions[:cut]);locked=set(sessions[cut:])
        by_ts={r['timestamp']:i for i,r in enumerate(rows)};allowed=set(freeze['motifs']);episode_rows=[];locked_skipped=0;missing=0
        for m in motifs:
            if m.get('motif') not in allowed:continue
            sess=m.get('session') or str(m.get('confirmation_timestamp',''))[:10]
            if sess in locked:
                locked_skipped+=1;continue
            if sess not in dev:continue
            i=by_ts.get(m.get('confirmation_timestamp'))
            if i is None:missing+=1;continue
            base=rows[i]['close'];rr={};
            for h in freeze['forward_horizons_bars']:
                j=i+int(h)
                rr[str(h)]=bps(base,rows[j]['close']) if j<len(rows) and rows[j]['session']==sess else None
            hi=base;lo=base
            for j in range(i+1,min(len(rows),i+1+int(freeze['excursion_horizon_bars']))):
                if rows[j]['session']!=sess:break
                hi=max(hi,rows[j]['high']);lo=min(lo,rows[j]['low'])
            up=bps(base,hi);down=-bps(base,lo) if bps(base,lo) is not None else None
            episode_rows.append({'motif':m['motif'],'session':sess,'confirmation_timestamp':m['confirmation_timestamp'],'returns_bps':rr,'up_excursion_bps':up,'down_excursion_bps':down})
        groups=defaultdict(list)
        for e in episode_rows:groups[e['motif']].append(e)
        gate=freeze['asymmetry_gate'];summaries={};survivors=[]
        for name in freeze['motifs']:
            es=groups.get(name,[]);r6=summ([e['returns_bps']['6'] for e in es]);r12=summ([e['returns_bps']['12'] for e in es])
            up20=sum(1 for e in es if e['up_excursion_bps'] is not None and e['up_excursion_bps']>=20)/len(es) if es else None
            dn20=sum(1 for e in es if e['down_excursion_bps'] is not None and e['down_excursion_bps']>=20)/len(es) if es else None
            up30=sum(1 for e in es if e['up_excursion_bps'] is not None and e['up_excursion_bps']>=30)/len(es) if es else None
            dn30=sum(1 for e in es if e['down_excursion_bps'] is not None and e['down_excursion_bps']>=30)/len(es) if es else None
            reasons=[];direction=None
            if len(es)<int(gate['minimum_episodes']):reasons.append('INSUFFICIENT_EPISODES')
            m6=r6['median'];m12=r12['median']
            if m6 is None or abs(m6)<float(gate['median_ret6_abs_min_bps']):reasons.append('RET6_MEDIAN_MAGNITUDE_GATE_FAIL')
            if m12 is None or abs(m12)<float(gate['median_ret12_abs_min_bps']):reasons.append('RET12_MEDIAN_MAGNITUDE_GATE_FAIL')
            if m6 is None or m12 is None or m6*m12<=0:reasons.append('RET6_RET12_SIGN_CONSISTENCY_FAIL')
            if not reasons or all(x not in reasons for x in ('RET6_RET12_SIGN_CONSISTENCY_FAIL','RET6_MEDIAN_MAGNITUDE_GATE_FAIL','RET12_MEDIAN_MAGNITUDE_GATE_FAIL')):
                if m6 is not None and m12 is not None and m6>0 and m12>0:direction='UP'
                elif m6 is not None and m12 is not None and m6<0 and m12<0:direction='DOWN'
            if direction=='UP':
                if up20 is None or dn20 is None or up20-dn20<float(gate['favorable_minus_adverse_rate_min_at_20bps']):reasons.append('20BPS_EXCURSION_ASYMMETRY_FAIL')
                if up30 is None or dn30 is None or up30-dn30<float(gate['favorable_minus_adverse_rate_min_at_30bps']):reasons.append('30BPS_EXCURSION_ASYMMETRY_FAIL')
            elif direction=='DOWN':
                if up20 is None or dn20 is None or dn20-up20<float(gate['favorable_minus_adverse_rate_min_at_20bps']):reasons.append('20BPS_EXCURSION_ASYMMETRY_FAIL')
                if up30 is None or dn30 is None or dn30-up30<float(gate['favorable_minus_adverse_rate_min_at_30bps']):reasons.append('30BPS_EXCURSION_ASYMMETRY_FAIL')
            else:
                if 'RET6_RET12_SIGN_CONSISTENCY_FAIL' not in reasons:reasons.append('NO_DIRECTION_INFERRED')
            verdict='DEVELOPMENT_ASYMMETRY_PASS' if not reasons else 'DEVELOPMENT_ASYMMETRY_FAIL'
            if verdict.endswith('PASS'):survivors.append({'motif':name,'direction':direction})
            summaries[name]={'episodes':len(es),'ret6_bps':r6,'ret12_bps':r12,'up_excursion_rate_20bps':up20,'down_excursion_rate_20bps':dn20,'up_excursion_rate_30bps':up30,'down_excursion_rate_30bps':dn30,'inferred_direction':direction,'verdict':verdict,'reasons':reasons}
        if len(survivors)>int(gate['maximum_survivors']):
            survivors=[];terminal='CLOSE_FAMILY_NO_CLEAR_ASYMMETRY';family_reason='TOO_MANY_SURVIVORS_FOR_BOUNDED_FOLLOWUP'
        else:
            terminal='ADVANCE_CLEAR_ASYMMETRY_TO_BOUNDED_ANATOMY' if survivors else 'CLOSE_FAMILY_NO_CLEAR_ASYMMETRY';family_reason=None
        ep_p.parent.mkdir(parents=True,exist_ok=True);ep_p.write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in episode_rows),encoding='utf-8')
        res.update({'status':'NIFTY_SWING_TRANSITION_DEVELOPMENT_COMPLETE','freeze_sha256':sha256(freeze_p),'scale_sha256':SCALE_SHA,'dataset_sha256':DATASET_SHA,'motifs_sha256':MOTIFS_SHA,'sessions_total':len(sessions),'development_sessions':len(dev),'locked_sessions':len(locked),'first_locked_session':sessions[cut] if cut<len(sessions) else None,'development_episodes':len(episode_rows),'locked_family_motifs_skipped_without_outcome_computation':locked_skipped,'motifs_missing_timestamp_match':missing,'motif_summaries':summaries,'survivors':survivors,'survivor_count':len(survivors),'family_reason':family_reason,'next_action':terminal,'development_episodes_path':str(ep_p),'development_episodes_sha256':sha256(ep_p),'interpretation':'Development-only NIFTY swing-transition asymmetry study. Motif names do not dictate post-confirmation direction. Final 20% session outcomes are not computed or read. PASS is not edge or strategy certification.'})
    except Exception as e:res['error']=f'{type(e).__name__}:{e}'
    out_p.parent.mkdir(parents=True,exist_ok=True);out_p.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(res,indent=2));return 0 if res.get('status')=='NIFTY_SWING_TRANSITION_DEVELOPMENT_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
