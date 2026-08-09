#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,importlib.util,json,math,sys
from collections import Counter,defaultdict
from pathlib import Path
from statistics import mean,median

SCALE_ID='NIFTY_STRUCTURE_SCALE_V1'
EXPECTED_NIFTY_SHA='6a145d4d17f124f9dc8ee272c5a19ca98988873a14b294765f44a27284d8b7e8'
EXPECTED_CROSS_SHA='66ddbfead966388262b9a1e49937fb227b711ce32f70eaf715a93a5e32572b32'

def sha256(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def load_module(name:str,path:Path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:raise RuntimeError('module_load_failed')
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def load_csv(path:Path):
    with path.open(newline='',encoding='utf-8') as h:return list(csv.DictReader(h))

def finite(x):
    try:return math.isfinite(float(x))
    except:return False

def bps(a,b):return (b/a-1.0)*10000.0 if a and finite(a) and finite(b) and float(a)>0 else None

def summarize(vals):
    xs=[float(x) for x in vals if finite(x)]
    if not xs:return {'n':0,'mean':None,'median':None}
    return {'n':len(xs),'mean':mean(xs),'median':median(xs)}

def session_bucket(pos,total):
    if total<=1:return 'UNKNOWN'
    q=pos/max(total-1,1)
    if q<0.20:return 'OPENING'
    if q<0.50:return 'MORNING'
    if q<0.80:return 'MIDDAY'
    return 'LATE_SESSION'

def vol_state(x):
    if x is None:return 'UNKNOWN'
    if x<=0.65:return 'COMPRESSED'
    if x>=1.75:return 'EXPANDED'
    return 'NORMAL'

def sgn(x):return 1 if x>0 else -1 if x<0 else 0

def leader_state(bn,sx):
    if not finite(bn) or not finite(sx):return 'UNKNOWN'
    a,b=sgn(float(bn)),sgn(float(sx))
    if a==0 or b==0:return 'MIXED_OR_FLAT'
    if a==b:return 'LEADERS_AGREE_UP' if a>0 else 'LEADERS_AGREE_DOWN'
    return 'LEADERS_DISAGREE'

def ret_over(rows,i,n):
    if i is None or i-n<0:return None
    if rows[i-n]['session']!=rows[i]['session']:return None
    return bps(rows[i-n]['close'],rows[i]['close'])

def range_ratio(rows,i,lookback):
    if i is None:return None
    sess=rows[i]['session'];cur=rows[i]['high']-rows[i]['low'];prev=[]
    for j in range(max(0,i-lookback),i):
        if rows[j]['session']==sess:prev.append(rows[j]['high']-rows[j]['low'])
    if not prev or mean(prev)<=0:return None
    return cur/mean(prev)

def formation_start(m):
    piv=m.get('pivots') or []
    pts=[p.get('pivot_timestamp') for p in piv if p.get('pivot_timestamp')]
    if pts:return min(pts),'EARLIEST_PIVOT_EXTREME'
    if m.get('break_timestamp'):return m['break_timestamp'],'BREAK_BAR'
    if m.get('episode_start_timestamp'):return m['episode_start_timestamp'],'ZONE_INTERACTION_ENTRY'
    if m.get('start_confirmation_timestamp'):return m['start_confirmation_timestamp'],'FIRST_COMPONENT_CONFIRMATION'
    return m.get('confirmation_timestamp'),'CONFIRMATION_FALLBACK'

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve()
    scale_p=root/'research/strategy_certification/NIFTY_STRUCTURE_SCALE_V1.json'
    nifty_p=root/'research/hypotheses/historical_corpus/kite_nifty_cache_v2/canonical/NIFTY.csv'
    cross_p=root/'research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv'
    od=root/'research/evidence/market_structure_pattern_atlas_v1'
    motif_p=od/'NIFTY_motifs.jsonl';motif_summary_p=od/'NIFTY_motif_summary.json'
    ctx_p=od/'NIFTY_motif_context_episodes_v1.jsonl';ctx_summary_p=od/'NIFTY_motif_context_summary_v1.json'
    res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'forward_profitability_labels_computed':False}
    try:
        scale=json.loads(scale_p.read_text())
        if scale.get('scale_id')!=SCALE_ID:raise ValueError('scale_id_mismatch')
        if scale.get('forward_outcomes_permitted') is not False:raise ValueError('outcome_policy_invalid')
        if sha256(nifty_p)!=EXPECTED_NIFTY_SHA or scale.get('dataset_sha256')!=EXPECTED_NIFTY_SHA:raise ValueError('nifty_dataset_hash_mismatch')
        if sha256(cross_p)!=EXPECTED_CROSS_SHA:raise ValueError('cross_context_hash_mismatch')
        builder=load_module('atlas_builder_nifty',root/'scripts/research/hypothesis_factory/build_market_structure_pattern_atlas_v1.py')
        motif=load_module('motif_builder_nifty',root/'scripts/research/hypothesis_factory/build_market_structure_motif_atlas_v1.py')
        rows=builder.load_rows(nifty_p,'NIFTY')
        th=float(scale['pivot_threshold_bps']);tol=float(scale['zone_tolerance_bps']);mint=int(scale['zone_min_confirmed_touches']);look=int(scale['rolling_context_bars'])
        piv=builder.classify_swings(builder.confirm_pivots(rows,th),tol)
        for p in piv:p['session']=rows[p['confirmation_index']]['session']
        zones=builder.build_zones(piv,tol,mint)
        motifs=[];motifs+=motif.swing_motifs(piv,tol);motifs+=motif.triangle_motifs(piv,tol);motifs+=motif.zone_motifs(rows,zones,tol);motifs+=motif.context_motifs(rows,builder.bar_descriptors,zones,tol,look)
        motifs.sort(key=lambda x:(x['confirmation_timestamp'],x['motif'],x.get('zone_id','')))
        od.mkdir(parents=True,exist_ok=True);motif_p.write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in motifs),encoding='utf-8')
        mcounts=Counter(x['motif'] for x in motifs)
        motif_summary={'status':'NIFTY_MOTIF_ATLAS_BUILD_COMPLETE','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'forward_profitability_labels_computed':False,'instrument':'NIFTY','scale_id':SCALE_ID,'scale_sha256':sha256(scale_p),'dataset_sha256':sha256(nifty_p),'threshold_bps':th,'confirmed_pivots':len(piv),'zones':len(zones),'motifs':len(motifs),'motif_counts':dict(sorted(mcounts.items())),'motifs_sha256':sha256(motif_p),'interpretation':'Frozen-scale NIFTY structural motifs only. No forward outcome or profitability labels.'}
        motif_summary_p.write_text(json.dumps(motif_summary,indent=2,sort_keys=True)+'\n',encoding='utf-8')

        cross=load_csv(cross_p);cross_by_ts={r['timestamp']:r for r in cross}
        by_ts={r['timestamp']:i for i,r in enumerate(rows)};counts=Counter(r['session'] for r in rows);pos={};seen=Counter()
        for i,r in enumerate(rows):pos[i]=seen[r['session']];seen[r['session']]+=1
        def context(i):
            if i is None:return None
            r=rows[i];cr=cross_by_ts.get(r['timestamp'],{});rr=range_ratio(rows,i,look)
            bn=cr.get('banknifty_ret_1_bps');sx=cr.get('sensex_ret_1_bps')
            return {'timestamp':r['timestamp'],'bar_index_in_session':pos[i],'session_bars':counts[r['session']],'session_bucket':session_bucket(pos[i],counts[r['session']]),'nifty_ret_1_bps':ret_over(rows,i,1),'nifty_ret_3_bps':ret_over(rows,i,3),'nifty_ret_6_bps':ret_over(rows,i,6),'banknifty_ret_1_bps':float(bn) if finite(bn) else None,'sensex_ret_1_bps':float(sx) if finite(sx) else None,'leader_state':leader_state(bn,sx),'range_ratio_vs_prior12':rr,'volatility_state':vol_state(rr)}
        episodes=[];missing=0;pre_missing=0
        for m in motifs:
            ci=by_ts.get(m.get('confirmation_timestamp'))
            if ci is None:missing+=1;continue
            start_ts,kind=formation_start(m);si=by_ts.get(start_ts);pi=None
            if si is not None and si>0 and rows[si-1]['session']==rows[si]['session']:pi=si-1
            else:pre_missing+=1
            episodes.append({**m,'formation_start_timestamp':start_ts,'preformation_anchor_kind':kind,'preformation_context':context(pi),'confirmation_context':context(ci)})
        ctx_p.write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in episodes),encoding='utf-8')
        groups=defaultdict(list)
        for e in episodes:groups[e['motif']].append(e)
        summaries={}
        for name,es in sorted(groups.items()):
            pre=[e['preformation_context'] for e in es if e['preformation_context'] is not None];conf=[e['confirmation_context'] for e in es if e['confirmation_context'] is not None]
            def block(xs):
                return {'n':len(xs),'session_bucket_counts':dict(sorted(Counter(x['session_bucket'] for x in xs).items())),'leader_state_counts':dict(sorted(Counter(x['leader_state'] for x in xs).items())),'volatility_state_counts':dict(sorted(Counter(x['volatility_state'] for x in xs).items())),'nifty_ret_3_bps':summarize([x['nifty_ret_3_bps'] for x in xs]),'nifty_ret_6_bps':summarize([x['nifty_ret_6_bps'] for x in xs]),'range_ratio_vs_prior12':summarize([x['range_ratio_vs_prior12'] for x in xs])}
            summaries[name]={'episodes':len(es),'preformation_context':block(pre),'confirmation_context':block(conf),'preformation_anchor_kinds':dict(sorted(Counter(e['preformation_anchor_kind'] for e in es).items()))}
        ctx_summary={'status':'NIFTY_MOTIF_CONTEXT_ANALYSIS_COMPLETE','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'forward_profitability_labels_computed':False,'instrument':'NIFTY','scale_id':SCALE_ID,'scale_sha256':sha256(scale_p),'dataset_sha256':sha256(nifty_p),'cross_context_sha256':sha256(cross_p),'motifs_sha256':sha256(motif_p),'motifs_received':len(motifs),'motifs_mapped':len(episodes),'motifs_missing_timestamp_match':missing,'preformation_context_unavailable':pre_missing,'motif_summaries':summaries,'context_episodes_sha256':sha256(ctx_p),'interpretation':'Preformation context ends strictly before motif formation begins; confirmation context is measured when the motif becomes observable. BANKNIFTY/SENSEX are contemporaneous context only. No post-confirmation outcomes are computed.'}
        ctx_summary_p.write_text(json.dumps(ctx_summary,indent=2,sort_keys=True)+'\n',encoding='utf-8')
        res.update({'status':'NIFTY_STRUCTURE_MOTIF_CONTEXT_COMPLETE','scale_sha256':sha256(scale_p),'dataset_sha256':sha256(nifty_p),'cross_context_sha256':sha256(cross_p),'rows':len(rows),'sessions':len(counts),'confirmed_pivots':len(piv),'zones':len(zones),'motifs':len(motifs),'motif_counts':dict(sorted(mcounts.items())),'motifs_sha256':sha256(motif_p),'context_episodes_sha256':sha256(ctx_p),'preformation_context_unavailable':pre_missing,'motifs_missing_timestamp_match':missing,'motif_summary_path':str(motif_summary_p),'context_summary_path':str(ctx_summary_p)})
    except Exception as e:res['error']=f'{type(e).__name__}:{e}'
    print(json.dumps(res,indent=2));return 0 if res['status']=='NIFTY_STRUCTURE_MOTIF_CONTEXT_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
