#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,json,math
from collections import Counter
from pathlib import Path
from statistics import mean,median

STUDY='NIFTY_UPTREND_CONTINUATION_ANATOMY_V1'
MOTIF='UPTREND_CONTINUATION_SWING'
DATASET_SHA='6a145d4d17f124f9dc8ee272c5a19ca98988873a14b294765f44a27284d8b7e8'
MOTIFS_SHA='6daad77489fe032d8b78354ec4a00e89f69975df7085d09fd2c50c492a1953ec'
DEV_EPISODES_SHA='063579299febe7d90230e858524805f9954346b0e48d68802f0f03498e2aab74'

def sha256(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def load_jsonl(p:Path):
 out=[]
 with p.open(encoding='utf-8') as h:
  for line in h:
   if line.strip():out.append(json.loads(line))
 return out

def finite(x):return isinstance(x,(int,float)) and math.isfinite(x)
def bps(a,b):return (b/a-1.0)*10000.0 if finite(a) and finite(b) and a>0 else None
def summ(xs):
 ys=[float(x) for x in xs if finite(x)]
 return {'n':len(ys),'mean':mean(ys) if ys else None,'median':median(ys) if ys else None}
def bucket(i,total):
 if total<=1:return 'UNKNOWN'
 q=i/max(total-1,1)
 return 'OPENING' if q<.20 else 'MORNING' if q<.50 else 'MIDDAY' if q<.80 else 'LATE_SESSION'

def main(argv=None):
 ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');a=ap.parse_args(argv)
 root=Path(a.repo_root).resolve()
 dataset=root/'research/hypotheses/historical_corpus/kite_nifty_cache_v2/canonical/NIFTY.csv'
 motifs_p=root/'research/evidence/market_structure_pattern_atlas_v1/NIFTY_motifs.jsonl'
 context_p=root/'research/evidence/market_structure_pattern_atlas_v1/NIFTY_motif_context_episodes_v1.jsonl'
 dev_p=root/'research/evidence/strategy_certification/NIFTY_SWING_TRANSITION_FAMILY_V1_DEVELOPMENT.json'
 dev_ep_p=root/'research/evidence/strategy_certification/NIFTY_SWING_TRANSITION_FAMILY_V1_DEVELOPMENT_EPISODES.jsonl'
 freeze_p=root/'research/strategy_certification/NIFTY_UPTREND_CONTINUATION_ANATOMY_V1.json'
 out_p=root/'research/evidence/strategy_certification/NIFTY_UPTREND_CONTINUATION_ANATOMY_V1.json'
 ep_out=root/'research/evidence/strategy_certification/NIFTY_UPTREND_CONTINUATION_ANATOMY_V1_EPISODES.jsonl'
 res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'locked_outcomes_accessed':False,'study_id':STUDY}
 try:
  if sha256(dataset)!=DATASET_SHA:raise ValueError('dataset_hash_mismatch')
  if sha256(motifs_p)!=MOTIFS_SHA:raise ValueError('motifs_hash_mismatch')
  if sha256(dev_ep_p)!=DEV_EPISODES_SHA:raise ValueError('development_episodes_hash_mismatch')
  freeze=json.loads(freeze_p.read_text());dev=json.loads(dev_p.read_text())
  if freeze.get('study_id')!=STUDY or freeze.get('locked_outcomes_permitted') is not False:raise ValueError('freeze_policy_mismatch')
  if dev.get('locked_outcomes_accessed') is not False:raise ValueError('development_locked_outcome_contamination')
  if dev.get('survivors')!=[{'direction':'UP','motif':MOTIF}]:raise ValueError('survivor_binding_mismatch')
  with dataset.open(newline='',encoding='utf-8') as h:raw=list(csv.DictReader(h))
  rows=[]
  for r in raw:
   try:o,hi,lo,c=(float(r[k]) for k in ('open','high','low','close'))
   except:continue
   ts=r['timestamp'];rows.append({'timestamp':ts,'session':r.get('session') or ts[:10],'open':o,'high':hi,'low':lo,'close':c})
  rows.sort(key=lambda r:r['timestamp']);idx={r['timestamp']:i for i,r in enumerate(rows)};session_counts=Counter(r['session'] for r in rows)
  session_pos={};seen=Counter()
  for i,r in enumerate(rows):session_pos[i]=seen[r['session']];seen[r['session']]+=1
  motifs={(m.get('motif'),m.get('confirmation_timestamp')):m for m in load_jsonl(motifs_p) if m.get('motif')==MOTIF}
  contexts={(m.get('motif'),m.get('confirmation_timestamp')):m for m in load_jsonl(context_p) if m.get('motif')==MOTIF}
  dev_eps=[e for e in load_jsonl(dev_ep_p) if e.get('motif')==MOTIF]
  episodes=[];missing_motif=missing_context=0
  for o in dev_eps:
   key=(MOTIF,o.get('confirmation_timestamp'));m=motifs.get(key);ctx=contexts.get(key)
   if m is None:missing_motif+=1;continue
   if ctx is None:missing_context+=1;continue
   piv=m.get('pivots') or []
   if len(piv)<3:continue
   i0=idx.get(piv[0].get('pivot_timestamp'));i1=idx.get(piv[1].get('pivot_timestamp'));i2=idx.get(piv[2].get('pivot_timestamp'));ic=idx.get(m.get('confirmation_timestamp'))
   if None in (i0,i1,i2,ic):continue
   sess=o['session']
   if not all(rows[i]['session']==sess for i in (i0,i1,i2,ic)):continue
   p0,p1,p2=(float(p['price']) for p in piv[:3]);pre=ctx.get('preformation_context') or {}
   desc={'formation_bars':i2-i0,'first_to_middle_bars':i1-i0,'middle_to_second_bars':i2-i1,'leg_duration_ratio':((i2-i1)/(i1-i0) if i1>i0 else None),'first_to_middle_bps':bps(p0,p1),'middle_to_second_bps':bps(p1,p2),'first_to_second_bps':bps(p0,p2),'confirmation_delay_bars':ic-i2,'preformation_nifty_ret_3_bps':pre.get('nifty_ret_3_bps'),'preformation_nifty_ret_6_bps':pre.get('nifty_ret_6_bps'),'preformation_leader_state':pre.get('leader_state'),'preformation_volatility_state':pre.get('volatility_state'),'formation_session_bucket':bucket(session_pos[i2],session_counts[sess])}
   episodes.append({'motif':MOTIF,'session':sess,'confirmation_timestamp':o['confirmation_timestamp'],'descriptors':desc,'outcome':{'up_excursion_bps':o.get('up_excursion_bps'),'down_excursion_bps':o.get('down_excursion_bps'),'ret6_bps':(o.get('returns_bps') or {}).get('6'),'ret12_bps':(o.get('returns_bps') or {}).get('12')}})
  thresholds=[float(x) for x in freeze['favorable_excursion_cohorts_bps']];numeric=[x for x in freeze['descriptors'] if x not in ('preformation_leader_state','preformation_volatility_state','formation_session_bucket')];categorical=['preformation_leader_state','preformation_volatility_state','formation_session_bucket'];cohorts={}
  for t in thresholds:
   yes=[e for e in episodes if finite(e['outcome']['up_excursion_bps']) and e['outcome']['up_excursion_bps']>=t];no=[e for e in episodes if not (finite(e['outcome']['up_excursion_bps']) and e['outcome']['up_excursion_bps']>=t)]
   block={}
   for name,subset in [('favorable',yes),('not_favorable',no)]:
    block[name]={'n':len(subset),'numeric':{k:summ([e['descriptors'].get(k) for e in subset]) for k in numeric},'categorical':{k:dict(sorted(Counter((e['descriptors'].get(k) or 'UNKNOWN') for e in subset).items())) for k in categorical}}
   cohorts[f'{int(t)}bps']=block
  ep_out.parent.mkdir(parents=True,exist_ok=True);ep_out.write_text(''.join(json.dumps(e,sort_keys=True)+'\n' for e in episodes),encoding='utf-8')
  res.update({'status':'NIFTY_UPTREND_CONTINUATION_ANATOMY_COMPLETE','freeze_sha256':sha256(freeze_p),'development_sha256':sha256(dev_p),'development_episodes_sha256':sha256(dev_ep_p),'dataset_sha256':DATASET_SHA,'motifs_sha256':MOTIFS_SHA,'motif':MOTIF,'direction':'UP','episodes':len(episodes),'missing_motif_join':missing_motif,'missing_context_join':missing_context,'cohorts':cohorts,'episodes_path':str(ep_out),'episodes_sha256':sha256(ep_out),'interpretation':'Bounded descriptive anatomy of the sole NIFTY swing-transition development survivor. Uses development outcomes only. No cutpoint search, combination search, locked outcome access, strategy, or edge claim.'})
 except Exception as e:res['error']=f'{type(e).__name__}:{e}'
 out_p.parent.mkdir(parents=True,exist_ok=True);out_p.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(res,indent=2));return 0 if res.get('status')=='NIFTY_UPTREND_CONTINUATION_ANATOMY_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
