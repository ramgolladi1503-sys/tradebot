#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,json,math
from pathlib import Path

FAMILY='COMPACT_MATCHED_DOUBLE_BOTTOM_V1'
MOTIF='DOUBLE_BOTTOM_STRUCTURE'

def sha256(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def load_jsonl(p:Path):
    out=[]
    with p.open(encoding='utf-8') as h:
        for line in h:
            if line.strip():out.append(json.loads(line))
    return out

def load_rows(p:Path):
    with p.open(newline='',encoding='utf-8') as h:rows=list(csv.DictReader(h))
    if not rows or not {'timestamp','session'}.issubset(rows[0]):raise ValueError('dataset_schema_mismatch')
    return rows

def finite(x):
    try:return math.isfinite(float(x))
    except:return False

def rate(vals,pred):
    xs=[float(x) for x in vals if finite(x)]
    return None if not xs else sum(1 for x in xs if pred(x))/len(xs)

def motif_features(m,ts_to_i):
    ps=m.get('pivots') or []
    if len(ps)!=3:return None
    try:
        p0=ts_to_i[ps[0]['pivot_timestamp']]
        p1=ts_to_i[ps[1]['pivot_timestamp']]
        p2=ts_to_i[ps[2]['pivot_timestamp']]
        c2=ts_to_i[ps[2]['confirmation_timestamp']]
        pr0=float(ps[0]['price']);pr2=float(ps[2]['price'])
    except (KeyError,TypeError,ValueError):return None
    if not (p0<=p1<=p2<=c2) or pr0<=0:return None
    return {
      'formation_bars':p2-p0,
      'middle_to_second_bars':p2-p1,
      'confirmation_delay_bars':c2-p2,
      'absolute_first_second_separation_bps':abs((pr2/pr0-1.0)*10000.0),
    }

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve()
    freeze_p=root/'research/strategy_certification/COMPACT_MATCHED_DOUBLE_BOTTOM_V1_FREEZE.json'
    motifs_p=root/'research/evidence/market_structure_pattern_atlas_v1/BANKNIFTY_motifs.jsonl'
    outcomes_p=root/'research/evidence/market_structure_pattern_atlas_v1/BANKNIFTY_post_confirmation_outcomes_v1.jsonl'
    matrix_p=root/'research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv'
    prior_consumed_p=root/'research/evidence/strategy_certification/RAPID_DOWNTREND_CONTINUATION_V1_LOCKED_TEST_CONSUMED.json'
    double_bottom_consumed_p=root/'research/evidence/strategy_certification/COMPACT_MATCHED_DOUBLE_BOTTOM_V1_LOCKED_TEST_CONSUMED.json'
    out_p=root/'research/evidence/strategy_certification/COMPACT_MATCHED_DOUBLE_BOTTOM_V1_DEVELOPMENT.json'
    res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'locked_outcomes_accessed':False}
    try:
        freeze=json.loads(freeze_p.read_text())
        if freeze.get('candidate_family_id')!=FAMILY:raise ValueError('family_id_mismatch')
        if double_bottom_consumed_p.exists():raise ValueError('DOUBLE_BOTTOM_LOCKED_OUTCOMES_ALREADY_CONSUMED')
        rows=load_rows(matrix_p);sessions=sorted({r['session'] for r in rows});cut=int(len(sessions)*0.80);locked=set(sessions[cut:]);ts_to_i={r['timestamp']:i for i,r in enumerate(rows)}
        motifs=[m for m in load_jsonl(motifs_p) if m.get('motif')==MOTIF]
        outcomes=[o for o in load_jsonl(outcomes_p) if o.get('motif')==MOTIF]
        # The outcome file was created from characterization sessions only. Recheck that invariant here.
        leaked=[o.get('session') for o in outcomes if o.get('session') in locked]
        if leaked:raise ValueError('LOCKED_DOUBLE_BOTTOM_OUTCOME_LEAK_IN_DEVELOPMENT_SOURCE')
        key=lambda x:(x.get('confirmation_timestamp'),x.get('session'))
        omap={key(o):o for o in outcomes}
        joined=[];missing_features=0
        for m in motifs:
            o=omap.get(key(m))
            if o is None:continue
            feat=motif_features(m,ts_to_i)
            if feat is None:missing_features+=1;continue
            joined.append((feat,o))
        parent_up=[o.get('mfe_up_bps') for _,o in joined]
        parent30=rate(parent_up,lambda x:x>=30.0);parent20=rate(parent_up,lambda x:x>=20.0)
        d=freeze['definition'];selected=[]
        for feat,o in joined:
            if (feat['formation_bars']<=d['formation_bars_max'] and feat['middle_to_second_bars']<=d['middle_to_second_bars_max'] and feat['absolute_first_second_separation_bps']<=d['absolute_first_second_separation_bps_max'] and feat['confirmation_delay_bars']<=d['confirmation_delay_bars_max']):
                selected.append(o)
        up=[o.get('mfe_up_bps') for o in selected]
        r30=rate(up,lambda x:x>=30.0);r20=rate(up,lambda x:x>=20.0)
        imp30=None if r30 is None or parent30 is None else r30-parent30
        imp20=None if r20 is None or parent20 is None else r20-parent20
        gate=freeze['development_gate'];reasons=[]
        if len(selected)<int(gate['minimum_candidate_episodes']):reasons.append('INSUFFICIENT_EPISODES')
        if imp30 is None or imp30<float(gate['minimum_absolute_primary_rate_improvement_vs_parent']):reasons.append('PRIMARY_IMPROVEMENT_GATE_FAIL')
        if imp20 is None or imp20<float(gate['minimum_secondary_rate_improvement_vs_parent']):reasons.append('SECONDARY_IMPROVEMENT_GATE_FAIL')
        verdict='DEVELOPMENT_PASS' if not reasons else 'DEVELOPMENT_FAIL'
        res.update({
          'status':'COMPACT_MATCHED_DOUBLE_BOTTOM_DEVELOPMENT_COMPLETE','family_id':FAMILY,'candidate_id':d['candidate_id'],'definition':d,
          'freeze_sha256':sha256(freeze_p),'motifs_sha256':sha256(motifs_p),'outcomes_sha256':sha256(outcomes_p),'dataset_sha256':sha256(matrix_p),
          'sessions_total':len(sessions),'characterization_sessions':len(sessions[:cut]),'locked_sessions':len(locked),'development_locked_double_bottom_sessions_found':len(leaked),
          'prior_downtrend_locked_consumption_marker_present':prior_consumed_p.exists(),'double_bottom_locked_consumption_marker_present':False,
          'parent_episodes':len(joined),'missing_temporal_features':missing_features,'candidate_episodes':len(selected),
          'parent_up_30bps_rate':parent30,'parent_up_20bps_rate':parent20,'candidate_up_30bps_rate':r30,'candidate_up_20bps_rate':r20,
          'primary_rate_improvement_vs_parent':imp30,'secondary_rate_improvement_vs_parent':imp20,
          'verdict':verdict,'reasons':reasons,'advanced_count':1 if verdict=='DEVELOPMENT_PASS' else 0,
          'next_action':'RUN_ONE_TIME_DOUBLE_BOTTOM_LOCKED_TEST' if verdict=='DEVELOPMENT_PASS' else 'CLOSE_HYPOTHESIS_NO_NOMINATION',
          'locked_outcomes_accessed':False,
          'interpretation':'Single predeclared double-bottom morphology candidate evaluated only on the already-exposed 80% characterization outcomes. The final-20% DOUBLE_BOTTOM_STRUCTURE outcomes are not read.'
        })
    except Exception as e:res['error']=f'{type(e).__name__}:{e}'
    out_p.parent.mkdir(parents=True,exist_ok=True);out_p.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(res,indent=2));return 0 if res.get('status')=='COMPACT_MATCHED_DOUBLE_BOTTOM_DEVELOPMENT_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
