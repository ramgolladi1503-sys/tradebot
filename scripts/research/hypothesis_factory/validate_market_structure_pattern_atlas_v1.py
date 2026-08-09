#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys
from pathlib import Path

def load_module(path:Path):
    spec=importlib.util.spec_from_file_location('pattern_atlas_v1',path)
    if spec is None or spec.loader is None:raise RuntimeError('module_load_failed')
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

def main():
    root=Path(__file__).resolve().parents[3]
    mod=load_module(root/'scripts/research/hypothesis_factory/build_market_structure_pattern_atlas_v1.py')
    def row(i,o,h,l,c):return {'timestamp':f'2026-01-01T09:{15+i:02d}:00','session':'2026-01-01','open':o,'high':h,'low':l,'close':c}
    # This fixture intentionally creates a confirmed swing HIGH at row 3 and
    # requires the confirmation to occur strictly later, at row 6, after a
    # >35 bps reversal. It then creates a later confirmed LOW.
    rows=[
      row(0,100.00,100.05,99.95,100.00),
      row(1,100.00,100.45,99.98,100.40),
      row(2,100.40,100.85,100.35,100.80),
      row(3,100.80,101.25,100.75,101.20),
      row(4,101.20,101.22,101.00,101.05),
      row(5,101.05,101.08,100.82,100.86),
      row(6,100.86,100.90,100.72,100.75),
      row(7,100.75,100.78,100.25,100.30),
      row(8,100.30,100.70,100.28,100.66),
    ]
    checks=[]
    piv=mod.confirm_pivots(rows,35.0)
    checks.append(('PIVOT_REQUIRES_LATER_CONFIRMATION',bool(piv) and all(p['confirmation_index']>p['pivot_index'] for p in piv)))
    if piv:
        first=piv[0];prefix=rows[:first['confirmation_index']+1];again=mod.confirm_pivots(prefix,35.0)
        checks.append(('CONFIRMED_PIVOT_REPRODUCIBLE_WITH_PREFIX_ONLY',bool(again) and again[0]['pivot_index']==first['pivot_index'] and again[0]['confirmation_index']==first['confirmation_index']))
    else:checks.append(('CONFIRMED_PIVOT_REPRODUCIBLE_WITH_PREFIX_ONLY',False))
    future=rows+[row(9,100.66,105.0,100.60,104.8),row(10,104.8,104.9,103.0,103.2)]
    fp=mod.confirm_pivots(future,35.0)
    checks.append(('FUTURE_EXTENSION_DOES_NOT_REWRITE_FIRST_CONFIRMED_PIVOT',bool(piv) and bool(fp) and fp[0]['pivot_index']==piv[0]['pivot_index'] and fp[0]['confirmation_index']==piv[0]['confirmation_index']))
    classified=mod.classify_swings([{'type':'LOW','price':100,'confirmation_timestamp':'a','pivot_timestamp':'a','confirmation_index':1,'pivot_index':0,'threshold_bps':35},{'type':'LOW','price':100.1,'confirmation_timestamp':'b','pivot_timestamp':'b','confirmation_index':3,'pivot_index':2,'threshold_bps':35}],15.0)
    checks.append(('DOUBLE_BOTTOM_USES_OBJECTIVE_TOLERANCE',classified[-1]['swing_labels']==['DOUBLE_BOTTOM_LIKE']))
    zones=mod.build_zones(classified,15.0,2)
    checks.append(('ZONE_REQUIRES_MINIMUM_CONFIRMED_TOUCHES',len(zones)==1 and zones[0]['touches']==2))
    result={'schema_version':1,'status':'PATTERN_ATLAS_V1_VALIDATION_PASS' if all(ok for _,ok in checks) else 'PATTERN_ATLAS_V1_VALIDATION_FAIL','checks_total':len(checks),'checks_passed':sum(ok for _,ok in checks),'checks':[{'check':n,'status':'PASS' if ok else 'FAIL'} for n,ok in checks],'runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False}
    print(json.dumps(result,indent=2));return 0 if result['status'].endswith('_PASS') else 2
if __name__=='__main__':raise SystemExit(main())
