#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,importlib.util,json,sys
from collections import Counter
from pathlib import Path

def sha256(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def load_module(path:Path):
 spec=importlib.util.spec_from_file_location('pattern_atlas_v1',path)
 if spec is None or spec.loader is None:raise RuntimeError('module_load_failed')
 m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

def bps(a,b):return (b/a-1)*10000 if a and a>0 else float('nan')

def swing_motifs(pivots,tol):
 out=[]
 for i in range(2,len(pivots)):
  a,b,c=pivots[i-2:i+1]
  if not (a['type']!=b['type'] and b['type']!=c['type'] and a['type']==c['type']):continue
  labs=set(c.get('swing_labels',[]));motif=None
  if a['type']=='HIGH':
   if 'HIGHER_HIGH' in labs and any(x in set(b.get('swing_labels',[])) for x in ('HIGHER_LOW','DOUBLE_BOTTOM_LIKE')):motif='UPTREND_CONTINUATION_SWING'
   elif 'LOWER_HIGH' in labs and any(x in set(b.get('swing_labels',[])) for x in ('LOWER_LOW','DOUBLE_BOTTOM_LIKE')):motif='DOWNTREND_FAILURE_TO_LOWER_HIGH'
   elif 'DOUBLE_TOP_LIKE' in labs:motif='DOUBLE_TOP_STRUCTURE'
  else:
   if 'LOWER_LOW' in labs and any(x in set(b.get('swing_labels',[])) for x in ('LOWER_HIGH','DOUBLE_TOP_LIKE')):motif='DOWNTREND_CONTINUATION_SWING'
   elif 'HIGHER_LOW' in labs and any(x in set(b.get('swing_labels',[])) for x in ('HIGHER_HIGH','DOUBLE_TOP_LIKE')):motif='UPTREND_FAILURE_TO_HIGHER_LOW'
   elif 'DOUBLE_BOTTOM_LIKE' in labs:motif='DOUBLE_BOTTOM_STRUCTURE'
  if motif:
   out.append({'motif':motif,'start_confirmation_timestamp':a['confirmation_timestamp'],'confirmation_timestamp':c['confirmation_timestamp'],'session':c.get('session'),'pivots':[{'type':x['type'],'price':x['price'],'pivot_timestamp':x['pivot_timestamp'],'confirmation_timestamp':x['confirmation_timestamp']} for x in (a,b,c)]})
 return out

def triangle_motifs(pivots,tol):
 out=[]
 for i in range(4,len(pivots)):
  w=pivots[i-4:i+1]
  if any(w[j]['type']==w[j+1]['type'] for j in range(4)):continue
  highs=[x for x in w if x['type']=='HIGH'];lows=[x for x in w if x['type']=='LOW']
  if len(highs)<2 or len(lows)<2:continue
  lower_highs=all(bps(highs[j]['price'],highs[j+1]['price'])<-tol for j in range(len(highs)-1))
  higher_lows=all(bps(lows[j]['price'],lows[j+1]['price'])>tol for j in range(len(lows)-1))
  if lower_highs and higher_lows:
   out.append({'motif':'TRIANGLE_LIKE_CONVERGENCE','start_confirmation_timestamp':w[0]['confirmation_timestamp'],'confirmation_timestamp':w[-1]['confirmation_timestamp'],'session':w[-1].get('session'),'pivots':[{'type':x['type'],'price':x['price'],'pivot_timestamp':x['pivot_timestamp'],'confirmation_timestamp':x['confirmation_timestamp']} for x in w]})
 return out

def zone_motifs(rows,zones,tol,lookahead_bars=12):
 ts_to_i={r['timestamp']:i for i,r in enumerate(rows)};out=[]
 for z in zones:
  first_i=ts_to_i.get(z['first_confirmation_timestamp'])
  if first_i is None:continue
  broken=None
  for i in range(first_i,len(rows)):
   r=rows[i];d=bps(z['center'],r['close'])
   if (z['side']=='RESISTANCE' and d>tol) or (z['side']=='SUPPORT' and d<-tol):broken=i;break
  if broken is None:continue
  for j in range(broken+1,min(len(rows),broken+1+lookahead_bars)):
   if rows[j]['session']!=rows[broken]['session']:break
   if abs(bps(z['center'],rows[j]['close']))<=tol:
    held=False
    if j+1<len(rows) and rows[j+1]['session']==rows[j]['session']:
     nxt=bps(z['center'],rows[j+1]['close'])
     held=(z['side']=='RESISTANCE' and nxt>=0) or (z['side']=='SUPPORT' and nxt<=0)
    out.append({'motif':'BREAK_RETEST_HOLD' if held else 'BREAK_RETEST_UNRESOLVED','zone_id':z['zone_id'],'former_side':z['side'],'zone_center':z['center'],'break_timestamp':rows[broken]['timestamp'],'confirmation_timestamp':rows[j]['timestamp'],'session':rows[j]['session']});break
 return out

def context_motifs(rows,bar_fn,zones,tol,lookback):
 # Collapse adjacent qualifying bars into one zone-interaction episode.
 out=[]
 for z in zones:
  active={'COMPRESSION':False,'WICK':False}
  for i,r in enumerate(rows):
   if r['timestamp']<z['first_confirmation_timestamp']:continue
   near=abs(bps(z['center'],r['close']))<=tol
   if not near:
    active={'COMPRESSION':False,'WICK':False};continue
   ps=set(bar_fn(rows,i,lookback)['primitives'])
   comp='RANGE_COMPRESSION' in ps
   wick=(z['side']=='RESISTANCE' and 'UPPER_WICK_REJECTION' in ps) or (z['side']=='SUPPORT' and 'LOWER_WICK_REJECTION' in ps)
   if comp and not active['COMPRESSION']:
    out.append({'motif':'COMPRESSION_AT_'+z['side'],'confirmation_timestamp':r['timestamp'],'session':r['session'],'zone_id':z['zone_id'],'zone_center':z['center']})
   if wick and not active['WICK']:
    out.append({'motif':'WICK_REJECTION_AT_'+z['side'],'confirmation_timestamp':r['timestamp'],'session':r['session'],'zone_id':z['zone_id'],'zone_center':z['center']})
   active['COMPRESSION']=comp;active['WICK']=wick
 return out

def main(argv=None):
 ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');ap.add_argument('--input',required=True);ap.add_argument('--instrument',default='BANKNIFTY');ap.add_argument('--threshold-bps',type=float,default=35.0);ap.add_argument('--zone-tolerance-bps',type=float,default=15.0);ap.add_argument('--zone-min-touches',type=int,default=2);ap.add_argument('--rolling-context-bars',type=int,default=12);ap.add_argument('--output-dir',default='research/evidence/market_structure_pattern_atlas_v1');a=ap.parse_args(argv)
 root=Path(a.repo_root).resolve();ip=Path(a.input);ip=ip if ip.is_absolute() else root/ip;od=root/a.output_dir;builder=load_module(root/'scripts/research/hypothesis_factory/build_market_structure_pattern_atlas_v1.py')
 res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'forward_profitability_labels_computed':False}
 try:
  rows=builder.load_rows(ip,a.instrument);piv=builder.classify_swings(builder.confirm_pivots(rows,a.threshold_bps),a.zone_tolerance_bps)
  for p in piv:p['session']=rows[p['confirmation_index']]['session']
  zones=builder.build_zones(piv,a.zone_tolerance_bps,a.zone_min_touches)
  motifs=[];motifs+=swing_motifs(piv,a.zone_tolerance_bps);motifs+=triangle_motifs(piv,a.zone_tolerance_bps);motifs+=zone_motifs(rows,zones,a.zone_tolerance_bps);motifs+=context_motifs(rows,builder.bar_descriptors,zones,a.zone_tolerance_bps,a.rolling_context_bars)
  motifs.sort(key=lambda x:(x['confirmation_timestamp'],x['motif'],x.get('zone_id','')))
  counts=Counter(x['motif'] for x in motifs);od.mkdir(parents=True,exist_ok=True);mp=od/f'{a.instrument}_motifs.jsonl';sp=od/f'{a.instrument}_motif_summary.json';mp.write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in motifs))
  res.update({'status':'MOTIF_ATLAS_BUILD_COMPLETE','instrument':a.instrument,'input_sha256':sha256(ip),'threshold_bps':a.threshold_bps,'confirmed_pivots':len(piv),'zones':len(zones),'motifs':len(motifs),'motif_counts':dict(sorted(counts.items())),'motifs_path':str(mp),'motifs_sha256':sha256(mp),'context_episode_collapsing':True,'interpretation':'Higher-level causal structural motifs only. Adjacent zone-context bars are collapsed into one episode. No outcome, expectancy, or profitability labels are computed.'})
 except Exception as e:res['error']=f'{type(e).__name__}:{e}'
 od.mkdir(parents=True,exist_ok=True);sp=od/f'{a.instrument}_motif_summary.json';sp.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n');print(json.dumps(res,indent=2));return 0 if res['status']=='MOTIF_ATLAS_BUILD_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
