#!/usr/bin/env python3
"""Close a discovery domain only from native zero-survivor run manifests."""
from __future__ import annotations
import argparse, importlib.util, json, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
P=HERE/'bounded_research_lifecycle.py'
spec=importlib.util.spec_from_file_location('bounded_lifecycle',P); life=importlib.util.module_from_spec(spec); assert spec and spec.loader; sys.modules[spec.name]=life; spec.loader.exec_module(life)


def load_manifest(path:Path)->dict:
    if not path.exists(): raise ValueError(f'missing_manifest:{path}')
    x=json.loads(path.read_text(encoding='utf-8'))
    if int(x.get('promising_not_certified',-1)) != 0:
        raise ValueError(f'nonzero_survivors:{path}:{x.get("promising_not_certified")}')
    if int(x.get('hypotheses',0)) <= 0:
        raise ValueError(f'invalid_hypothesis_count:{path}')
    return x


def manifest_sha(m:dict)->str:
    return str(m.get('input_sha256') or m.get('cache_data_sha256') or '')


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--domain-id',required=True); p.add_argument('--information-set-id',required=True); p.add_argument('--dataset-sha256',required=True)
    p.add_argument('--manifest',action='append',required=True); p.add_argument('--output',required=True); a=p.parse_args(argv)
    gens=[]
    for raw in a.manifest:
        path=Path(raw); m=load_manifest(path); sha=manifest_sha(m)
        if sha and sha != a.dataset_sha256: raise ValueError(f'manifest_dataset_sha_mismatch:{path}:{sha}')
        gens.append({
            'generation_id':str(m.get('run_id') or path.parent.name),
            'schema_version':m.get('schema_version'),
            'hypotheses':int(m['hypotheses']),
            'admissible_candidates':0,
            'min_trades':m.get('min_trades'),
            'cost_bps':m.get('cost_bps'),
            'dataset_sha256':a.dataset_sha256,
            'manifest_path':str(path),
        })
    closure=life.close_search_domain(domain_id=a.domain_id,information_set_id=a.information_set_id,dataset_sha256=a.dataset_sha256,generations=gens)
    out=Path(a.output); life.write(out,closure); print(json.dumps(closure,indent=2)); return 0

if __name__=='__main__': raise SystemExit(main())
