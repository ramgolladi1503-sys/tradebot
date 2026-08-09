#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,json,math
from pathlib import Path
from statistics import mean,median

FAMILY='RAPID_DOWNTREND_CONTINUATION_V1'
MOTIF='DOWNTREND_CONTINUATION_SWING'
EXPECTED_NOMINEE='RAPID'

def sha256(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()

def load_jsonl(p:Path):
    out=[]
    with p.open(encoding='utf-8') as h:
        for line in h:
            if line.strip():out.append(json.loads(line))
    return out

def load_rows(p:Path):
    with p.open(newline='',encoding='utf-8') as h:return list(csv.DictReader(h))

def finite(x):
    try:return math.isfinite(float(x))
    except:return False

def rate(vals,pred):
    xs=[float(x) for x in vals if finite(x)]
    return None if not xs else sum(1 for x in xs if pred(x))/len(xs)

def summarize(vals):
    xs=[float(x) for x in vals if finite(x)]
    if not xs:return {'n':0,'mean':None,'median':None}
    return {'n':len(xs),'mean':mean(xs),'median':median(xs)}

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve()
    freeze_p=root/'research/strategy_certification/RAPID_DOWNTREND_CONTINUATION_V1_FREEZE.json'
    dev_p=root/'research/evidence/strategy_certification/RAPID_DOWNTREND_CONTINUATION_V1_DEVELOPMENT.json'
    motifs_p=root/'research/evidence/market_structure_pattern_atlas_v1/BANKNIFTY_motifs.jsonl'
    data_p=root/'research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv'
    out_p=root/'research/evidence/strategy_certification/RAPID_DOWNTREND_CONTINUATION_V1_LOCKED_TEST.json'
    seal_p=root/'research/evidence/strategy_certification/RAPID_DOWNTREND_CONTINUATION_V1_LOCKED_TEST_CONSUMED.json'
    res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'locked_outcomes_accessed':False}
    try:
        if seal_p.exists():raise ValueError('LOCKED_TEST_ALREADY_CONSUMED')
        freeze=json.loads(freeze_p.read_text());dev=json.loads(dev_p.read_text())
        if freeze.get('candidate_family_id')!=FAMILY:raise ValueError('family_id_mismatch')
        if dev.get('family_id')!=FAMILY:raise ValueError('development_family_mismatch')
        if dev.get('advanced_count')!=1 or dev.get('nominated_candidate_id')!=EXPECTED_NOMINEE:raise ValueError('single_nomination_required')
        if dev.get('next_action')!='RUN_ONE_TIME_LOCKED_TEST':raise ValueError('development_not_authorized_for_locked_test')
        if dev.get('locked_outcomes_accessed') is not False:raise ValueError('development_locked_state_invalid')
        if dev.get('freeze_sha256')!=sha256(freeze_p):raise ValueError('freeze_hash_mismatch')
        if dev.get('motifs_sha256')!=sha256(motifs_p):raise ValueError('motif_hash_mismatch')
        if dev.get('dataset_sha256')!=sha256(data_p):raise ValueError('dataset_hash_mismatch')
        definition=next((d for d in freeze['definitions'] if d['candidate_id']==EXPECTED_NOMINEE),None)
        if definition is None:raise ValueError('nominated_definition_missing')
        rows=load_rows(data_p);sessions=sorted({r['session'] for r in rows});cut=int(len(sessions)*0.80);locked=set(sessions[cut:])
        ts_to_i={r['timestamp']:i for i,r in enumerate(rows)}
        motifs=[m for m in load_jsonl(motifs_p) if m.get('motif')==MOTIF]
        selected=[];parent=[];missing=0
        for m in motifs:
            ts=m.get('confirmation_timestamp');i=ts_to_i.get(ts)
            if i is None:missing+=1;continue
            sess=rows[i]['session']
            if sess not in locked:continue
            piv=m.get('pivots') or []
            if len(piv)!=3:continue
            idx=[]
            for p in piv:
                pi=ts_to_i.get(p.get('pivot_timestamp'))
                if pi is None:idx=[];break
                idx.append(pi)
            ci=ts_to_i.get(m.get('confirmation_timestamp'))
            if len(idx)!=3 or ci is None:continue
            formation=idx[2]-idx[0];middle_to_second=idx[2]-idx[1];confirmation_delay=ci-idx[2]
            c0=float(rows[ci]['banknifty_close'])
            lows=[];ret6=None;ret12=None
            for j in range(ci+1,min(len(rows),ci+13)):
                if rows[j]['session']!=sess:break
                lows.append((float(rows[j]['banknifty_low'])/c0-1.0)*10000.0)
                if j==ci+6:ret6=(float(rows[j]['banknifty_close'])/c0-1.0)*10000.0
                if j==ci+12:ret12=(float(rows[j]['banknifty_close'])/c0-1.0)*10000.0
            mae=min(lows) if lows else None
            rec={'confirmation_timestamp':ts,'session':sess,'formation_bars':formation,'middle_to_second_bars':middle_to_second,'confirmation_delay_bars':confirmation_delay,'mae_down_bps':mae,'ret6_bps':ret6,'ret12_bps':ret12}
            parent.append(rec)
            if formation<=definition['formation_bars_max'] and middle_to_second<=definition['middle_to_second_bars_max'] and confirmation_delay<=definition['confirmation_delay_bars_max']:
                selected.append(rec)
        p30=rate([x['mae_down_bps'] for x in parent],lambda x:x<=-30.0);p20=rate([x['mae_down_bps'] for x in parent],lambda x:x<=-20.0)
        c30=rate([x['mae_down_bps'] for x in selected],lambda x:x<=-30.0);c20=rate([x['mae_down_bps'] for x in selected],lambda x:x<=-20.0)
        min_n=int(freeze['locked_test_policy']['minimum_locked_episodes'])
        dev_parent30=float(dev['parent_down_30bps_rate'])
        reasons=[]
        if len(selected)<min_n:reasons.append('INSUFFICIENT_LOCKED_EPISODES')
        if c30 is None or c30<dev_parent30:reasons.append('PRIMARY_RATE_BELOW_CHARACTERIZATION_PARENT')
        verdict='LOCKED_VALIDATION_PASS' if not reasons else 'LOCKED_VALIDATION_FAIL'
        res.update({'status':'RAPID_DOWNTREND_LOCKED_TEST_COMPLETE','family_id':FAMILY,'candidate_id':EXPECTED_NOMINEE,'definition':definition,'freeze_sha256':sha256(freeze_p),'development_sha256':sha256(dev_p),'motifs_sha256':sha256(motifs_p),'dataset_sha256':sha256(data_p),'sessions_total':len(sessions),'locked_sessions':len(locked),'locked_outcomes_accessed':True,'locked_parent_episodes':len(parent),'locked_candidate_episodes':len(selected),'locked_parent_down_30bps_rate':p30,'locked_parent_down_20bps_rate':p20,'locked_candidate_down_30bps_rate':c30,'locked_candidate_down_20bps_rate':c20,'candidate_ret6_bps':summarize([x['ret6_bps'] for x in selected]),'candidate_ret12_bps':summarize([x['ret12_bps'] for x in selected]),'motifs_missing_timestamp_match':missing,'verdict':verdict,'reasons':reasons,'edge_claimed':False,'interpretation':'One-time locked validation of the frozen RAPID temporal definition on the final 20% sessions. This is structural validation only, not strategy or edge certification.'})
        seal={'family_id':FAMILY,'candidate_id':EXPECTED_NOMINEE,'locked_test_consumed':True,'result_sha256_pending_self_reference':True,'freeze_sha256':sha256(freeze_p),'development_sha256':sha256(dev_p)}
        seal_p.parent.mkdir(parents=True,exist_ok=True);seal_p.write_text(json.dumps(seal,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    except Exception as e:res['error']=f'{type(e).__name__}:{e}'
    out_p.parent.mkdir(parents=True,exist_ok=True);out_p.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(res,indent=2));return 0 if res.get('status')=='RAPID_DOWNTREND_LOCKED_TEST_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
