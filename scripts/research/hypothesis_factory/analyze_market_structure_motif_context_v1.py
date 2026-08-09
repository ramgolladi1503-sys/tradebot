#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,json,math
from collections import Counter,defaultdict
from pathlib import Path
from statistics import mean,median

def sha256(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def f(r,k):
    try:return float(r[k])
    except:return float('nan')
def finite(*xs):return all(math.isfinite(x) for x in xs)
def bps(a,b):return (b/a-1.0)*10000.0 if finite(a,b) and a>0 else float('nan')
def sgn(x):return 1 if x>0 else -1 if x<0 else 0

def load_matrix(path:Path):
    with path.open(newline='',encoding='utf-8') as h:rows=list(csv.DictReader(h))
    req={'timestamp','session','banknifty_open','banknifty_high','banknifty_low','banknifty_close','nifty_ret_1_bps','sensex_ret_1_bps'}
    if not rows or not req.issubset(rows[0]):raise ValueError('dataset_schema_mismatch')
    return rows

def load_jsonl(path:Path):
    out=[]
    with path.open(encoding='utf-8') as h:
        for line in h:
            if line.strip():out.append(json.loads(line))
    return out

def session_positions(rows):
    pos={};counts=defaultdict(int)
    for i,r in enumerate(rows):
        pos[i]=counts[r['session']];counts[r['session']]+=1
    return pos,counts

def ret_over(rows,i,n):
    if i is None or i-n<0:return None
    if rows[i-n]['session']!=rows[i]['session']:return None
    a=f(rows[i-n],'banknifty_close');b=f(rows[i],'banknifty_close')
    x=bps(a,b)
    return x if math.isfinite(x) else None

def avg_range_ratio(rows,i,lookback=12):
    if i is None or i<1:return None
    sess=rows[i]['session'];o=f(rows[i],'banknifty_open');h=f(rows[i],'banknifty_high');l=f(rows[i],'banknifty_low')
    if not finite(o,h,l) or o<=0:return None
    cur=h-l;prev=[]
    for j in range(max(0,i-lookback),i):
        if rows[j]['session']!=sess:continue
        ph=f(rows[j],'banknifty_high');pl=f(rows[j],'banknifty_low')
        if finite(ph,pl):prev.append(ph-pl)
    if not prev or mean(prev)<=0:return None
    return cur/mean(prev)

def session_bucket(bar_i,total):
    if total<=1:return 'UNKNOWN'
    q=bar_i/max(total-1,1)
    if q<0.20:return 'OPENING'
    if q<0.50:return 'MORNING'
    if q<0.80:return 'MIDDAY'
    return 'LATE_SESSION'

def vol_state(x):
    if x is None:return 'UNKNOWN'
    if x<=0.65:return 'COMPRESSED'
    if x>=1.75:return 'EXPANDED'
    return 'NORMAL'

def leader_state(n,s):
    if not finite(n,s):return 'UNKNOWN'
    sn,ss=sgn(n),sgn(s)
    if sn==0 or ss==0:return 'MIXED_OR_FLAT'
    if sn==ss:return 'LEADERS_AGREE_UP' if sn>0 else 'LEADERS_AGREE_DOWN'
    return 'LEADERS_DISAGREE'

def summarize(vals):
    xs=[x for x in vals if x is not None and math.isfinite(x)]
    if not xs:return {'n':0,'mean':None,'median':None}
    return {'n':len(xs),'mean':mean(xs),'median':median(xs)}

def context_at(rows,i,pos,counts):
    if i is None:return None
    r=rows[i];n=f(r,'nifty_ret_1_bps');s=f(r,'sensex_ret_1_bps');rr=avg_range_ratio(rows,i,12)
    return {
      'timestamp':r['timestamp'],
      'bar_index_in_session':pos[i],
      'session_bars':counts[r['session']],
      'session_bucket':session_bucket(pos[i],counts[r['session']]),
      'banknifty_ret_1_bps':ret_over(rows,i,1),
      'banknifty_ret_3_bps':ret_over(rows,i,3),
      'banknifty_ret_6_bps':ret_over(rows,i,6),
      'nifty_ret_1_bps':n if math.isfinite(n) else None,
      'sensex_ret_1_bps':s if math.isfinite(s) else None,
      'leader_state':leader_state(n,s),
      'range_ratio_vs_prior12':rr,
      'volatility_state':vol_state(rr)
    }

def formation_start_timestamp(m):
    piv=m.get('pivots') or []
    pts=[p.get('pivot_timestamp') for p in piv if p.get('pivot_timestamp')]
    if pts:return min(pts),'EARLIEST_PIVOT_EXTREME'
    if m.get('break_timestamp'):return m['break_timestamp'],'BREAK_BAR'
    if m.get('episode_start_timestamp'):return m['episode_start_timestamp'],'ZONE_INTERACTION_ENTRY'
    if m.get('start_confirmation_timestamp'):return m['start_confirmation_timestamp'],'FIRST_COMPONENT_CONFIRMATION'
    return m.get('confirmation_timestamp'),'CONFIRMATION_FALLBACK'

def preformation_index(rows,by_ts,m):
    ts,kind=formation_start_timestamp(m);matches=by_ts.get(ts,[])
    if not matches:return None,kind,ts
    start_i=matches[0];pre_i=start_i-1
    if pre_i<0 or rows[pre_i]['session']!=rows[start_i]['session']:return None,kind,ts
    return pre_i,kind,ts

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');ap.add_argument('--input',default='research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv');ap.add_argument('--motifs',default='research/evidence/market_structure_pattern_atlas_v1/BANKNIFTY_motifs.jsonl');ap.add_argument('--output-dir',default='research/evidence/market_structure_pattern_atlas_v1');a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve();ip=root/a.input;mp=root/a.motifs;od=root/a.output_dir
    res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'forward_profitability_labels_computed':False}
    try:
        rows=load_matrix(ip);motifs=load_jsonl(mp);by_ts=defaultdict(list)
        for i,r in enumerate(rows):by_ts[r['timestamp']].append(i)
        pos,counts=session_positions(rows);episodes=[];missing=0;pre_missing=0
        for m in motifs:
            ts=m['confirmation_timestamp'];matches=by_ts.get(ts,[])
            if not matches:missing+=1;continue
            ci=matches[0]
            pi,anchor_kind,formation_ts=preformation_index(rows,by_ts,m)
            if pi is None:pre_missing+=1
            episode={**m,
              'formation_start_timestamp':formation_ts,
              'preformation_anchor_kind':anchor_kind,
              'preformation_context':context_at(rows,pi,pos,counts),
              'confirmation_context':context_at(rows,ci,pos,counts)
            }
            episodes.append(episode)
        groups=defaultdict(list)
        for e in episodes:groups[e['motif']].append(e)
        summaries={}
        for motif,es in sorted(groups.items()):
            pre=[e['preformation_context'] for e in es if e['preformation_context'] is not None]
            conf=[e['confirmation_context'] for e in es if e['confirmation_context'] is not None]
            def block(ctxs):
                buckets=Counter(x['session_bucket'] for x in ctxs);leaders=Counter(x['leader_state'] for x in ctxs);vols=Counter(x['volatility_state'] for x in ctxs)
                return {'n':len(ctxs),'session_bucket_counts':dict(sorted(buckets.items())),'leader_state_counts':dict(sorted(leaders.items())),'volatility_state_counts':dict(sorted(vols.items())),'banknifty_ret_3_bps':summarize([x['banknifty_ret_3_bps'] for x in ctxs]),'banknifty_ret_6_bps':summarize([x['banknifty_ret_6_bps'] for x in ctxs]),'range_ratio_vs_prior12':summarize([x['range_ratio_vs_prior12'] for x in ctxs])}
            summaries[motif]={'episodes':len(es),'preformation_context':block(pre),'confirmation_context':block(conf),'preformation_anchor_kinds':dict(sorted(Counter(e['preformation_anchor_kind'] for e in es).items()))}
        od.mkdir(parents=True,exist_ok=True);ep=od/'BANKNIFTY_motif_context_episodes.jsonl';sp=od/'BANKNIFTY_motif_context_summary.json';ep.write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in episodes),encoding='utf-8')
        res.update({'status':'MOTIF_CONTEXT_ANALYSIS_COMPLETE','input_sha256':sha256(ip),'motifs_sha256':sha256(mp),'motifs_received':len(motifs),'motifs_mapped':len(episodes),'motifs_missing_timestamp_match':missing,'preformation_context_unavailable':pre_missing,'motif_summaries':summaries,'context_episodes_path':str(ep),'context_episodes_sha256':sha256(ep),'interpretation':'Two causal clocks are reported separately: preformation context ends strictly before the motif begins forming; confirmation context describes the state when the motif becomes observable. No post-confirmation returns, outcomes, expectancy, or profitability are computed.'})
    except Exception as e:res['error']=f'{type(e).__name__}:{e}'
    od.mkdir(parents=True,exist_ok=True);sp=od/'BANKNIFTY_motif_context_summary.json';sp.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(res,indent=2));return 0 if res['status']=='MOTIF_CONTEXT_ANALYSIS_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
