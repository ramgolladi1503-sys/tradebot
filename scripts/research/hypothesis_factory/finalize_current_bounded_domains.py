#!/usr/bin/env python3
"""Finalize the current BANKNIFTY discovery domains from exact native run IDs.

This script is intentionally narrow. It closes only the exact discovery generations
already executed for the frozen BANKNIFTY target and the exact cross-market matrix.
It does not search for new hypotheses and cannot reopen a closed domain.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
P = HERE / 'close_search_domain_from_manifests.py'
spec = importlib.util.spec_from_file_location('close_domains', P)
closer = importlib.util.module_from_spec(spec); assert spec and spec.loader; sys.modules[spec.name] = closer; spec.loader.exec_module(closer)

TARGET_SHA = 'ff5474cb0662e9f4bc0642dab6e00a2648cfe2da16161ab174c9324c0f22ef50'
CROSS_SHA = '66ddbfead966388262b9a1e49937fb227b711ce32f70eaf715a93a5e32572b32'
TARGET_RUNS = [
    ('research/hypotheses/kite_banknifty_screen_runs', 'CACHED-STRICT-20260809T055327Z'),
    ('research/hypotheses/kite_banknifty_expanded_runs', 'EXPANDED-STRICT-20260809T061940Z'),
    ('research/hypotheses/kite_banknifty_state_runs', 'STATE-STRICT-20260809T071422Z'),
]
CROSS_RUNS = [
    ('research/hypotheses/cross_market_screen_runs', 'CROSS-STRICT-20260809T072418Z'),
]


def manifest_for(root: Path, run_id: str) -> Path:
    p = root / run_id / 'run_manifest.json'
    if not p.exists():
        raise ValueError(f'missing_exact_run_manifest:{run_id}:{p}')
    m = closer.load_manifest(p)
    if str(m.get('run_id')) != run_id:
        raise ValueError(f'run_id_mismatch:{p}')
    return p


def build_closure(domain_id: str, info_id: str, sha: str, manifests: list[Path]) -> dict:
    gens=[]
    for p in manifests:
        m=closer.load_manifest(p); observed=closer.manifest_sha(m)
        if observed and observed != sha:
            raise ValueError(f'manifest_dataset_sha_mismatch:{p}:{observed}')
        gens.append({
            'generation_id':m['run_id'],
            'schema_version':m.get('schema_version'),
            'hypotheses':int(m['hypotheses']),
            'admissible_candidates':0,
            'min_trades':m.get('min_trades'),
            'cost_bps':m.get('cost_bps'),
            'dataset_sha256':sha,
            'manifest_path':str(p),
        })
    return closer.life.close_search_domain(domain_id=domain_id, information_set_id=info_id, dataset_sha256=sha, generations=gens)


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo-root', default='.')
    p.add_argument('--output-dir', default='research/hypotheses/domain_closures')
    a=p.parse_args(argv)
    root=Path(a.repo_root).resolve(); out=root/a.output_dir; out.mkdir(parents=True,exist_ok=True)
    target=[manifest_for(root/rel,run) for rel,run in TARGET_RUNS]
    cross=[manifest_for(root/rel,run) for rel,run in CROSS_RUNS]
    c1=build_closure('BANKNIFTY_5M_PRICE_ONLY_V1','BANKNIFTY_5M_TARGET_PRICE_V1',TARGET_SHA,target)
    c2=build_closure('BANKNIFTY_CROSS_MARKET_5M_PRICE_ONLY_V1','BANKNIFTY_NIFTY_SENSEX_5M_PRICE_V1',CROSS_SHA,cross)
    closer.life.write(out/'BANKNIFTY_5M_PRICE_ONLY_V1.json',c1)
    closer.life.write(out/'BANKNIFTY_CROSS_MARKET_5M_PRICE_ONLY_V1.json',c2)
    summary={
        'schema_version':'tradebot-bounded-discovery-finalization-v1',
        'status':'DISCOVERY_DOMAINS_CLOSED_NO_CANDIDATE',
        'closures':[c1,c2],
        'candidate_of_record':None,
        'next_legal_action':'OPEN_NEW_PREDECLARED_INFORMATION_SET_OR_STOP_DISCOVERY',
        'certification_engine_status':'SEPARATE_TRUTH_CONTRACT_REQUIRED',
        'runtime_authority':'NONE','broker_actions_allowed':False,
    }
    closer.life.write(out/'FINALIZATION_SUMMARY.json',summary)
    print(json.dumps(summary,indent=2)); return 0

if __name__=='__main__': raise SystemExit(main())
