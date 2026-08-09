#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,json,math
from collections import Counter,defaultdict
from pathlib import Path
from statistics import mean,median

STUDY_ID='MARKET_STRUCTURE_PATTERN_ANATOMY_V1'

def sha256(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def load_jsonl(path:Path):
    out=[]
    with path.open(encoding='utf-8') as h:
        for line in h:
            if line.strip():out.append(json.loads(line))
    return out

def load_matrix(path:Path):
    with path.open(newline='',encoding='utf-8') as h:rows=list(csv.DictReader(h))
    req={'timestamp','session'}
    if not rows or not req.issubset(rows[0]):raise ValueError('dataset_schema_mismatch')
    return rows

def finite(x):return x is not None and isinstance(x,(int,float)) and math.isfinite(x)
def bps(a,b):return (b/a-1.0)*10000.0 if finite(a) and finite(b) and a>0 else None

def summarize(vals):
    xs=[float(x) for x in vals if finite(x)]
    if not xs:return {'n':0,'mean':None,'median':None}
    return {'n':len(xs),'mean':mean(xs),'median':median(xs)}

def bucket(i,total):
    if total<=1:return 'UNKNOWN'
    q=i/max(total-1,1)
    if q<.20:return 'OPENING'
    if q<.50:return 'MORNING'
    if q<.80:return 'MIDDAY'
    return 'LATE_SESSION'

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.')
    ap.add_argument('--matrix',default='research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv')
    ap.add_argument('--motifs',default='research/evidence/market_structure_pattern_atlas_v1/BANKNIFTY_motifs.jsonl')
    ap.add_argument('--context',default='research/evidence/market_structure_pattern_atlas_v1/BANKNIFTY_motif_context_episodes.jsonl')
    ap.add_argument('--outcomes',default='research/evidence/market_structure_pattern_atlas_v1/BANKNIFTY_post_confirmation_outcomes_v1.jsonl')
    ap.add_argument('--contract',default='research/strategy_certification/MARKET_STRUCTURE_PATTERN_ANATOMY_V1.json')
    ap.add_argument('--output-dir',default='research/evidence/market_structure_pattern_atlas_v1');a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve();mp=root/a.matrix;motp=root/a.motifs;cp=root/a.context;op=root/a.outcomes;kp=root/a.contract;od=root/a.output_dir
    res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'locked_outcomes_accessed':False}
    try:
        contract=json.loads(kp.read_text())
        if contract.get('study_id')!=STUDY_ID:raise ValueError('study_id_mismatch')
        motifs=load_jsonl(motp);contexts=load_jsonl(cp);outs=load_jsonl(op);rows=load_matrix(mp)
        families=set(contract['motif_families']);thresholds=[float(x) for x in contract['favorable_excursion_cohorts_bps']]
        idx={r['timestamp']:i for i,r in enumerate(rows)};session_counts=Counter(r['session'] for r in rows)
        motif_map={(m.get('motif'),m.get('confirmation_timestamp')):m for m in motifs if m.get('motif') in families}
        ctx_map={(c.get('motif'),c.get('confirmation_timestamp')):c for c in contexts if c.get('motif') in families}
        episodes=[];missing_motif=missing_context=0
        for o in outs:
            key=(o.get('motif'),o.get('confirmation_timestamp'))
            if o.get('motif') not in families:continue
            m=motif_map.get(key);c=ctx_map.get(key)
            if m is None:missing_motif+=1;continue
            if c is None:missing_context+=1;continue
            piv=m.get('pivots') or []
            if len(piv)<3:continue
            a0,a1,a2=piv[0],piv[1],piv[2]
            i0=idx.get(a0.get('pivot_timestamp'));i1=idx.get(a1.get('pivot_timestamp'));i2=idx.get(a2.get('pivot_timestamp'));ic=idx.get(m.get('confirmation_timestamp'))
            if None in (i0,i1,i2,ic):continue
            sess=rows[ic]['session']
            if not all(rows[ii]['session']==sess for ii in (i0,i1,i2,ic)):continue
            p0=float(a0['price']);p1=float(a1['price']);p2=float(a2['price'])
            d01=i1-i0;d12=i2-i1;form=i2-i0
            move01=bps(p0,p1);move12=bps(p1,p2);move02=bps(p0,p2)
            ratio=None
            if finite(move01) and move01!=0 and finite(move12):ratio=abs(move12)/abs(move01)
            pre=(c.get('preformation_context') or {})
            rec={'motif':o['motif'],'confirmation_timestamp':o['confirmation_timestamp'],'session':sess,
                 'descriptors':{'formation_bars':form,'first_to_middle_bars':d01,'middle_to_second_bars':d12,
                  'leg_duration_ratio':(d12/d01 if d01>0 else None),'first_to_middle_bps':move01,'middle_to_second_bps':move12,
                  'first_to_second_bps':move02,'absolute_first_second_separation_bps':abs(move02) if finite(move02) else None,
                  'rebound_retracement_ratio':ratio,'confirmation_delay_bars':ic-i2,
                  'formation_session_bucket':bucket(i2,session_counts[sess]),
                  'preformation_leader_state':pre.get('leader_state'),'preformation_volatility_state':pre.get('volatility_state'),
                  'preformation_banknifty_ret_3_bps':pre.get('banknifty_ret_3_bps'),'preformation_banknifty_ret_6_bps':pre.get('banknifty_ret_6_bps')},
                 'outcome':{'mfe_up_bps':o.get('mfe_up_bps'),'mae_down_bps':o.get('mae_down_bps')}}
            episodes.append(rec)
        groups=defaultdict(list)
        for e in episodes:groups[e['motif']].append(e)
        summaries={}
        numeric=['formation_bars','first_to_middle_bars','middle_to_second_bars','leg_duration_ratio','first_to_middle_bps','middle_to_second_bps','first_to_second_bps','absolute_first_second_separation_bps','rebound_retracement_ratio','confirmation_delay_bars','preformation_banknifty_ret_3_bps','preformation_banknifty_ret_6_bps']
        categorical=['formation_session_bucket','preformation_leader_state','preformation_volatility_state']
        for motif,es in sorted(groups.items()):
            direction='UP' if motif=='DOUBLE_BOTTOM_STRUCTURE' else 'DOWN'
            item={'episodes':len(es),'directional_reference':direction,'cohorts':{}}
            for t in thresholds:
                if direction=='UP':pred=lambda e,t=t: finite(e['outcome']['mfe_up_bps']) and e['outcome']['mfe_up_bps']>=t
                else:pred=lambda e,t=t: finite(e['outcome']['mae_down_bps']) and e['outcome']['mae_down_bps']<=-t
                yes=[e for e in es if pred(e)];no=[e for e in es if not pred(e)]
                comp={}
                for name,subset in [('favorable',yes),('not_favorable',no)]:
                    comp[name]={'n':len(subset),'numeric':{k:summarize([e['descriptors'].get(k) for e in subset]) for k in numeric},
                                'categorical':{k:dict(sorted(Counter(e['descriptors'].get(k) or 'UNKNOWN' for e in subset).items())) for k in categorical}}
                item['cohorts'][f'{int(t)}bps']=comp
            summaries[motif]=item
        od.mkdir(parents=True,exist_ok=True);ep=od/'BANKNIFTY_pattern_anatomy_v1.jsonl';sp=od/'BANKNIFTY_pattern_anatomy_summary_v1.json'
        ep.write_text(''.join(json.dumps(e,sort_keys=True)+'\n' for e in episodes),encoding='utf-8')
        res.update({'status':'PATTERN_ANATOMY_ANALYSIS_COMPLETE','study_id':STUDY_ID,'contract_sha256':sha256(kp),'motifs_sha256':sha256(motp),'context_sha256':sha256(cp),'outcomes_sha256':sha256(op),'locked_outcomes_accessed':False,'episodes':len(episodes),'missing_motif_join':missing_motif,'missing_context_join':missing_context,'motif_summaries':summaries,'episodes_path':str(ep),'episodes_sha256':sha256(ep),'interpretation':'Descriptive anatomy comparison inside the already-exposed 80% characterization pool only. No cutpoint search, combination ranking, strategy, or edge claim.'})
    except Exception as e:res['error']=f'{type(e).__name__}:{e}'
    od.mkdir(parents=True,exist_ok=True);sp=od/'BANKNIFTY_pattern_anatomy_summary_v1.json';sp.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(res,indent=2));return 0 if res['status']=='PATTERN_ANATOMY_ANALYSIS_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
