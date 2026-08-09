#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,math
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

def finite(x):
    try:return math.isfinite(float(x))
    except:return False

def rate(vals,pred):
    xs=[x for x in vals if finite(x)]
    return None if not xs else sum(1 for x in xs if pred(float(x)))/len(xs)

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve()
    fp=root/'research/strategy_certification/RAPID_DOWNTREND_CONTINUATION_V1_FREEZE.json'
    anatomy_p=root/'research/evidence/market_structure_pattern_atlas_v1/BANKNIFTY_pattern_anatomy_v1.jsonl'
    outcomes_p=root/'research/evidence/market_structure_pattern_atlas_v1/BANKNIFTY_post_confirmation_outcomes_v1.jsonl'
    out_p=root/'research/evidence/strategy_certification/RAPID_DOWNTREND_CONTINUATION_V1_DEVELOPMENT.json'
    res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'locked_outcomes_accessed':False}
    try:
        freeze=json.loads(fp.read_text())
        if freeze.get('candidate_family_id')!=FAMILY: raise ValueError('family_id_mismatch')
        if freeze.get('locked_outcomes_must_remain_unaccessed_during_development') is not True: raise ValueError('locked_policy_missing')
        anatomy=[x for x in load_jsonl(anatomy_p) if x.get('motif')==MOTIF]
        outcomes=[x for x in load_jsonl(outcomes_p) if x.get('motif')==MOTIF]
        key=lambda x:(x.get('confirmation_timestamp'),x.get('session'))
        omap={key(x):x for x in outcomes}
        joined=[]
        for x in anatomy:
            o=omap.get(key(x))
            if o is not None: joined.append((x,o))
        parent_down=[o.get('mae_down_bps') for _,o in joined]
        parent30=rate(parent_down,lambda x:x<=-30.0);parent20=rate(parent_down,lambda x:x<=-20.0)
        gate=freeze['development_gate'];cands=[]
        for d in freeze['definitions']:
            selected=[]
            for x,o in joined:
                if x.get('formation_bars') is None or x.get('middle_to_second_bars') is None or x.get('confirmation_delay_bars') is None: continue
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
        res.update({'status':'RAPID_DOWNTREND_DEVELOPMENT_COMPLETE','family_id':FAMILY,'freeze_sha256':sha256(fp),'anatomy_sha256':sha256(anatomy_p),'outcomes_sha256':sha256(outcomes_p),'parent_episodes':len(joined),'parent_down_30bps_rate':parent30,'parent_down_20bps_rate':parent20,'candidates':cands,'nominated_candidate_id':nominated,'advanced_count':1 if nominated else 0,'next_action':'RUN_ONE_TIME_LOCKED_TEST' if nominated else 'CLOSE_HYPOTHESIS_NO_NOMINATION','locked_outcomes_accessed':False,'interpretation':'Development-only comparison using already-exposed characterization outcomes. No locked-session outcome is read by this runner; no edge or certification claim is made.'})
    except Exception as e:res['error']=f'{type(e).__name__}:{e}'
    out_p.parent.mkdir(parents=True,exist_ok=True);out_p.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(res,indent=2));return 0 if res['status']=='RAPID_DOWNTREND_DEVELOPMENT_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
