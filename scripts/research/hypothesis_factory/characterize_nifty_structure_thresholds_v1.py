#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,importlib.util,json,math,sys
from collections import Counter
from pathlib import Path

THRESHOLDS=(20.0,35.0,50.0)

def sha256(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def load_module(name:str,path:Path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:raise RuntimeError('module_load_failed')
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def _finite(*xs):
    return all(math.isfinite(float(x)) for x in xs)

def load_nifty_matrix_rows(path:Path):
    with path.open(newline='',encoding='utf-8') as h:
        rows=list(csv.DictReader(h))
    if not rows:raise ValueError('empty_dataset')
    cols=set(rows[0].keys())
    candidates=[
        {'open':'nifty_open','high':'nifty_high','low':'nifty_low','close':'nifty_close'},
        {'open':'NIFTY_open','high':'NIFTY_high','low':'NIFTY_low','close':'NIFTY_close'},
        {'open':'NIFTY_OPEN','high':'NIFTY_HIGH','low':'NIFTY_LOW','close':'NIFTY_CLOSE'},
    ]
    omap=next((m for m in candidates if set(m.values()).issubset(cols)),None)
    if omap is None:
        raise ValueError('nifty_ohlc_schema_not_supported:'+','.join(sorted(cols)))
    out=[]
    for r in rows:
        ts=r.get('timestamp')
        if not ts:continue
        sess=r.get('session') or ts[:10]
        try:o,h,l,c=(float(r[omap[k]]) for k in ('open','high','low','close'))
        except Exception:continue
        if not _finite(o,h,l,c) or min(o,h,l,c)<=0 or h<l:continue
        out.append({'timestamp':ts,'session':sess,'open':o,'high':h,'low':l,'close':c})
    out.sort(key=lambda x:x['timestamp'])
    if not out:raise ValueError('no_valid_nifty_rows')
    return out,omap,sorted(cols)

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');ap.add_argument('--input',default='research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv');ap.add_argument('--output',default='research/evidence/market_structure_pattern_atlas_v1/NIFTY_threshold_characterization_v1.json');a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve();ip=root/a.input;op=root/a.output
    builder=load_module('atlas_builder',root/'scripts/research/hypothesis_factory/build_market_structure_pattern_atlas_v1.py')
    motif=load_module('motif_builder',root/'scripts/research/hypothesis_factory/build_market_structure_motif_atlas_v1.py')
    res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'forward_profitability_labels_computed':False}
    try:
        rows,omap,cols=load_nifty_matrix_rows(ip)
        by={}
        for th in THRESHOLDS:
            piv=builder.classify_swings(builder.confirm_pivots(rows,th),15.0)
            for p in piv:p['session']=rows[p['confirmation_index']]['session']
            zones=builder.build_zones(piv,15.0,2)
            motifs=[]
            motifs+=motif.swing_motifs(piv,15.0)
            motifs+=motif.triangle_motifs(piv,15.0)
            motifs+=motif.zone_motifs(rows,zones,15.0)
            motifs+=motif.context_motifs(rows,builder.bar_descriptors,zones,15.0,12)
            counts=Counter(x['motif'] for x in motifs)
            by[str(int(th))]={'threshold_bps':th,'confirmed_pivots':len(piv),'zones':len(zones),'motifs':len(motifs),'motif_counts':dict(sorted(counts.items()))}
        res.update({'status':'NIFTY_STRUCTURE_THRESHOLD_CHARACTERIZATION_COMPLETE','instrument':'NIFTY','dataset_sha256':sha256(ip),'rows':len(rows),'sessions':len({r['session'] for r in rows}),'nifty_ohlc_mapping':omap,'matrix_columns':cols,'thresholds_bps':list(THRESHOLDS),'by_threshold':by,'interpretation':'Descriptive NIFTY structural-scale characterization only. No forward outcomes, profitability, strategy selection, or edge claim.'})
    except Exception as e:res['error']=f'{type(e).__name__}:{e}'
    op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(res,indent=2));return 0 if res['status']=='NIFTY_STRUCTURE_THRESHOLD_CHARACTERIZATION_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
