#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,json,math
from collections import defaultdict
from pathlib import Path
from statistics import mean,median

STUDY_ID='MARKET_STRUCTURE_POST_CONFIRMATION_OUTCOME_V1'

def sha256(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def f(r,k):
    try:return float(r[k])
    except:return float('nan')
def finite(*xs):return all(math.isfinite(x) for x in xs)
def bps(a,b):return (b/a-1.0)*10000.0 if finite(a,b) and a>0 else float('nan')

def load_matrix(path:Path):
    with path.open(newline='',encoding='utf-8') as h:rows=list(csv.DictReader(h))
    req={'timestamp','session','banknifty_high','banknifty_low','banknifty_close'}
    if not rows or not req.issubset(rows[0]):raise ValueError('dataset_schema_mismatch')
    return rows

def load_jsonl(path:Path):
    out=[]
    with path.open(encoding='utf-8') as h:
        for line in h:
            if line.strip():out.append(json.loads(line))
    return out

def summarize(xs):
    ys=[x for x in xs if x is not None and math.isfinite(x)]
    if not ys:return {'n':0,'mean':None,'median':None}
    return {'n':len(ys),'mean':mean(ys),'median':median(ys)}

def rate(vals,pred):
    xs=[x for x in vals if x is not None and math.isfinite(x)]
    if not xs:return {'n':0,'rate':None}
    return {'n':len(xs),'rate':sum(1 for x in xs if pred(x))/len(xs)}

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');ap.add_argument('--input',default='research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv');ap.add_argument('--motifs',default='research/evidence/market_structure_pattern_atlas_v1/BANKNIFTY_motifs.jsonl');ap.add_argument('--contract',default='research/strategy_certification/MARKET_STRUCTURE_POST_CONFIRMATION_OUTCOME_V1.json');ap.add_argument('--output-dir',default='research/evidence/market_structure_pattern_atlas_v1');a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve();ip=root/a.input;mp=root/a.motifs;cp=root/a.contract;od=root/a.output_dir
    res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'locked_outcomes_accessed':False}
    try:
        contract=json.loads(cp.read_text())
        if contract.get('study_id')!=STUDY_ID:raise ValueError('study_id_mismatch')
        if sha256(ip)!=contract['dataset_sha256']:raise ValueError('dataset_hash_mismatch')
        if sha256(mp)!=contract['motifs_sha256']:raise ValueError('motifs_hash_mismatch')
        rows=load_matrix(ip);motifs=load_jsonl(mp)
        sessions=sorted({r['session'] for r in rows});cut=int(len(sessions)*float(contract['session_split']['characterization_fraction']))
        characterization=set(sessions[:cut]);locked=set(sessions[cut:])
        ts_to_i={r['timestamp']:i for i,r in enumerate(rows)}
        fam=set(contract['motif_families']);hs=[int(x) for x in contract['horizons_bars']];window=int(contract['excursion_window_bars']);thr=[float(x) for x in contract['thresholds_bps_for_excursion_rates']]
        groups=defaultdict(list);skipped_locked=0;missing=0
        for m in motifs:
            if m.get('motif') not in fam:continue
            ts=m.get('confirmation_timestamp');i=ts_to_i.get(ts)
            if i is None:missing+=1;continue
            sess=rows[i]['session']
            if sess in locked:
                skipped_locked+=1;continue
            if sess not in characterization:continue
            c0=f(rows[i],'banknifty_close')
            if not math.isfinite(c0) or c0<=0:continue
            rec={'motif':m['motif'],'confirmation_timestamp':ts,'session':sess,'horizon_return_bps':{},'mfe_up_bps':None,'mae_down_bps':None}
            for h in hs:
                j=i+h
                if j<len(rows) and rows[j]['session']==sess:
                    c1=f(rows[j],'banknifty_close');rec['horizon_return_bps'][str(h)]=bps(c0,c1) if math.isfinite(c1) else None
                else:rec['horizon_return_bps'][str(h)]=None
            highs=[];lows=[]
            for j in range(i+1,min(len(rows),i+1+window)):
                if rows[j]['session']!=sess:break
                hi=f(rows[j],'banknifty_high');lo=f(rows[j],'banknifty_low')
                if math.isfinite(hi):highs.append(bps(c0,hi))
                if math.isfinite(lo):lows.append(bps(c0,lo))
            rec['mfe_up_bps']=max(highs) if highs else None;rec['mae_down_bps']=min(lows) if lows else None
            groups[m['motif']].append(rec)
        summaries={}
        direction=contract['directional_reference']
        for motif,es in sorted(groups.items()):
            item={'episodes':len(es),'forward_return_bps':{},'mfe_up_bps':summarize([e['mfe_up_bps'] for e in es]),'mae_down_bps':summarize([e['mae_down_bps'] for e in es]),'excursion_rates':{}}
            for h in hs:item['forward_return_bps'][str(h)]=summarize([e['horizon_return_bps'][str(h)] for e in es])
            d=direction.get(motif,'STRUCTURE_SIDE_UNKNOWN_DESCRIPTIVE_ONLY')
            item['directional_reference']=d
            if d=='UP':
                for t in thr:item['excursion_rates'][f'up_{int(t)}bps_before_window_end']=rate([e['mfe_up_bps'] for e in es],lambda x,t=t:x>=t)
                for t in thr:item['excursion_rates'][f'down_{int(t)}bps_adverse_within_window']=rate([e['mae_down_bps'] for e in es],lambda x,t=t:x<=-t)
            elif d=='DOWN':
                for t in thr:item['excursion_rates'][f'down_{int(t)}bps_before_window_end']=rate([e['mae_down_bps'] for e in es],lambda x,t=t:x<=-t)
                for t in thr:item['excursion_rates'][f'up_{int(t)}bps_adverse_within_window']=rate([e['mfe_up_bps'] for e in es],lambda x,t=t:x>=t)
            summaries[motif]=item
        od.mkdir(parents=True,exist_ok=True);ep=od/'BANKNIFTY_post_confirmation_outcomes_v1.jsonl';sp=od/'BANKNIFTY_post_confirmation_outcome_summary_v1.json';ep.write_text(''.join(json.dumps(e,sort_keys=True)+'\n' for motif in sorted(groups) for e in groups[motif]),encoding='utf-8')
        res.update({'status':'POST_CONFIRMATION_OUTCOME_STUDY_COMPLETE','study_id':STUDY_ID,'dataset_sha256':sha256(ip),'motifs_sha256':sha256(mp),'contract_sha256':sha256(cp),'sessions_total':len(sessions),'characterization_sessions':len(characterization),'locked_outcome_sessions':len(locked),'locked_outcomes_accessed':False,'motifs_skipped_due_locked_sessions':skipped_locked,'motifs_missing_timestamp_match':missing,'motif_summaries':summaries,'episodes_path':str(ep),'episodes_sha256':sha256(ep),'interpretation':'Descriptive post-confirmation characterization on the first 80% of sessions only. Final 20% outcome sessions remain locked. No strategy, expectancy, cost-adjusted edge, or certification claim is made.'})
    except Exception as e:res['error']=f'{type(e).__name__}:{e}'
    od.mkdir(parents=True,exist_ok=True);sp=od/'BANKNIFTY_post_confirmation_outcome_summary_v1.json';sp.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(res,indent=2));return 0 if res['status']=='POST_CONFIRMATION_OUTCOME_STUDY_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
