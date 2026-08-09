#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,json,math
from pathlib import Path

FAMILY='RAPID_DOWNTREND_CONTINUATION_V1'
MOTIF='DOWNTREND_CONTINUATION_SWING'

def sha256(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def load_jsonl(p:Path):
    out=[]
    with p.open(encoding='utf-8') as h:
        for line in h:
            if line.strip(): out.append(json.loads(line))
    return out

def load_rows(p:Path):
    with p.open(newline='',encoding='utf-8') as h: rows=list(csv.DictReader(h))
    if not rows or not {'timestamp','session'}.issubset(rows[0]): raise ValueError('dataset_schema_mismatch')
    return rows

def finite(x):
    try:return math.isfinite(float(x))
    except:return False

def rate(vals,pred):
    xs=[x for x in vals if finite(x)]
    return None if not xs else sum(1 for x in xs if pred(float(x)))/len(xs)

def motif_temporal_features(m,ts_to_i):
    ps=m.get('pivots') or []
    if len(ps)!=3:return None
    try:
        p0=ts_to_i[ps[0]['pivot_timestamp']]
        p1=ts_to_i[ps[1]['pivot_timestamp']]
        p2=ts_to_i[ps[2]['pivot_timestamp']]
        c2=ts_to_i[ps[2]['confirmation_timestamp']]
    except (KeyError,TypeError):
        return None
    if not (p0<=p1<=p2<=c2):return None
    return {
        'formation_bars':p2-p0,
        'middle_to_second_bars':p2-p1,
        'confirmation_delay_bars':c2-p2,
    }

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve()
    fp=root/'research/strategy_certification/RAPID_DOWNTREND_CONTINUATION_V1_FREEZE.json'
    motifs_p=root/'research/evidence/market_structure_pattern_atlas_v1/BANKNIFTY_motifs.jsonl'
    outcomes_p=root/'research/evidence/market_structure_pattern_atlas_v1/BANKNIFTY_post_confirmation_outcomes_v1.jsonl'
    matrix_p=root/'research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv'
    out_p=root/'research/evidence/strategy_certification/RAPID_DOWNTREND_CONTINUATION_V1_DEVELOPMENT.json'
    res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'locked_outcomes_accessed':False}
    try:
        freeze=json.loads(fp.read_text())
        if freeze.get('candidate_family_id')!=FAMILY: raise ValueError('family_id_mismatch')
        if freeze.get('locked_outcomes_must_remain_unaccessed_during_development') is not True: raise ValueError('locked_policy_missing')
        rows=load_rows(matrix_p);ts_to_i={r['timestamp']:i for i,r in enumerate(rows)}
        motifs=[x for x in load_jsonl(motifs_p) if x.get('motif')==MOTIF]
        outcomes=[x for x in load_jsonl(outcomes_p) if x.get('motif')==MOTIF]
        key=lambda x:(x.get('confirmation_timestamp'),x.get('session'))
        omap={key(x):x for x in outcomes}
        joined=[];missing_temporal=0
        for m in motifs:
            o=omap.get(key(m))
            if o is None:continue
            feat=motif_temporal_features(m,ts_to_i)
            if feat is None:
                missing_temporal+=1;continue
            joined.append((feat,o))
        parent_down=[o.get('mae_down_bps') for _,o in joined]
        parent30=rate(parent_down,lambda x:x<=-30.0);parent20=rate(parent_down,lambda x:x<=-20.0)
        gate=freeze['development_gate'];cands=[]
        for d in freeze['definitions']:
            selected=[]
            for x,o in joined:
                if float(x['formation_bars'])<=d['formation_bars_max'] and float(x['middle_to_second_bars'])<=d['middle_to_second_bars_max'] and float(x['confirmation_delay_bars'])<=d['confirmation_delay_bars_max']:
                    selected.append(o)
            down=[o.get('mae_down_bps') for o in selected]
            r30=rate(down,lambda x:x<=-30.0);r20=rate(down,lambda x:x<=-20.0)
            imp30=None if r30 is None or parent30 is None else r30-parent30
            imp20=None if r20 is None or parent20 is None else r20-parent20
            reasons=[]
            if len(selected)<int(gate['minimum_candidate_episodes']):reasons.append('INSUFFICIENT_EPISODES')
            if imp30 is None or imp30<float(gate['minimum_absolute_primary_rate_improvement_vs_parent']):reasons.append('PRIMARY_IMPROVEMENT_GATE_FAIL')
            if imp20 is None or imp20<float(gate['minimum_secondary_rate_improvement_vs_parent']):reasons.append('SECONDARY_IMPROVEMENT_GATE_FAIL')
            cands.append({'candidate_id':d['candidate_id'],'definition':d,'episodes':len(selected),'down_30bps_rate':r30,'down_20bps_rate':r20,'primary_rate_improvement_vs_parent':imp30,'secondary_rate_improvement_vs_parent':imp20,'verdict':'DEVELOPMENT_PASS' if not reasons else 'DEVELOPMENT_FAIL','reasons':reasons})
        passing=[x for x in cands if x['verdict']=='DEVELOPMENT_PASS']
        passing.sort(key=lambda x:(x['primary_rate_improvement_vs_parent'],x['episodes']),reverse=True)
        nominated=passing[0]['candidate_id'] if passing else None
        res.update({'status':'RAPID_DOWNTREND_DEVELOPMENT_COMPLETE','family_id':FAMILY,'freeze_sha256':sha256(fp),'motifs_sha256':sha256(motifs_p),'outcomes_sha256':sha256(outcomes_p),'dataset_sha256':sha256(matrix_p),'parent_episodes':len(joined),'missing_temporal_features':missing_temporal,'parent_down_30bps_rate':parent30,'parent_down_20bps_rate':parent20,'candidates':cands,'nominated_candidate_id':nominated,'advanced_count':1 if nominated else 0,'next_action':'RUN_ONE_TIME_LOCKED_TEST' if nominated else 'CLOSE_HYPOTHESIS_NO_NOMINATION','locked_outcomes_accessed':False,'interpretation':'Development-only comparison using already-exposed characterization outcomes. Temporal anatomy is reconstructed deterministically from frozen motif pivot timestamps; no locked-session outcome is read by this runner; no edge or certification claim is made.'})
    except Exception as e:res['error']=f'{type(e).__name__}:{e}'
    out_p.parent.mkdir(parents=True,exist_ok=True);out_p.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(res,indent=2));return 0 if res['status']=='RAPID_DOWNTREND_DEVELOPMENT_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
