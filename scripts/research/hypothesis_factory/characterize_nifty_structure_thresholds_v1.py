#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from collections import Counter
from pathlib import Path

THRESHOLDS=(20.0,35.0,50.0)

def sha256(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def load_module(name:str,path:Path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:raise RuntimeError('module_load_failed')
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');ap.add_argument('--input',default='research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv');ap.add_argument('--output',default='research/evidence/market_structure_pattern_atlas_v1/NIFTY_threshold_characterization_v1.json');a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve();ip=root/a.input;op=root/a.output
    builder=load_module('atlas_builder',root/'scripts/research/hypothesis_factory/build_market_structure_pattern_atlas_v1.py')
    motif=load_module('motif_builder',root/'scripts/research/hypothesis_factory/build_market_structure_motif_atlas_v1.py')
    res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'forward_profitability_labels_computed':False}
    try:
        rows=builder.load_rows(ip,'NIFTY')
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
        res.update({'status':'NIFTY_STRUCTURE_THRESHOLD_CHARACTERIZATION_COMPLETE','instrument':'NIFTY','dataset_sha256':sha256(ip),'rows':len(rows),'sessions':len({r['session'] for r in rows}),'thresholds_bps':list(THRESHOLDS),'by_threshold':by,'interpretation':'Descriptive NIFTY structural-scale characterization only. No forward outcomes, profitability, strategy selection, or edge claim.'})
    except Exception as e:res['error']=f'{type(e).__name__}:{e}'
    op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(res,indent=2));return 0 if res['status']=='NIFTY_STRUCTURE_THRESHOLD_CHARACTERIZATION_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
