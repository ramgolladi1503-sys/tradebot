#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys
from pathlib import Path

def load_module(path:Path):
    spec=importlib.util.spec_from_file_location('pattern_atlas_v1',path)
    if spec is None or spec.loader is None:raise RuntimeError('module_load_failed')
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

def main():
    root=Path(__file__).resolve().parents[3];mod=load_module(root/'scripts/research/hypothesis_factory/build_market_structure_pattern_atlas_v1.py')
    def row(i,o,h,l,c,session='2026-01-01'):return {'timestamp':f'{session}T09:{15+i:02d}:00','session':session,'open':o,'high':h,'low':l,'close':c}
    rows=[row(0,100.00,100.05,99.95,100.00),row(1,100.00,100.45,99.98,100.40),row(2,100.40,100.85,100.35,100.80),row(3,100.80,101.25,100.75,101.20),row(4,101.20,101.22,101.00,101.05),row(5,101.05,101.08,100.82,100.86),row(6,100.86,100.90,100.72,100.75),row(7,100.75,100.78,100.25,100.30),row(8,100.30,100.70,100.28,100.66)]
    checks=[]
    def ck(name,ok,detail=None):checks.append({'check':name,'status':'PASS' if ok else 'FAIL','detail':detail})
    piv=mod.confirm_pivots(rows,35.0)
    ck('PIVOT_REQUIRES_LATER_CONFIRMATION',bool(piv) and piv[0]['confirmation_index']>piv[0]['pivot_index'] and piv[0]['confirmation_timestamp']>piv[0]['pivot_timestamp'])
    ck('PIVOT_CARRIES_SESSION',bool(piv) and all(p.get('session')=='2026-01-01' for p in piv))
    if piv:
        first=piv[0];again=mod.confirm_pivots(rows[:first['confirmation_index']+1],35.0);ck('CONFIRMED_PIVOT_REPRODUCIBLE_WITH_PREFIX_ONLY',bool(again) and again[0]['pivot_index']==first['pivot_index'] and again[0]['confirmation_index']==first['confirmation_index'])
    else:ck('CONFIRMED_PIVOT_REPRODUCIBLE_WITH_PREFIX_ONLY',False)
    future=rows+[row(9,100.66,105.0,100.60,104.8),row(10,104.8,104.9,103.0,103.2)];fp=mod.confirm_pivots(future,35.0);ck('FUTURE_EXTENSION_DOES_NOT_REWRITE_FIRST_CONFIRMED_PIVOT',bool(piv) and bool(fp) and fp[0]['pivot_index']==piv[0]['pivot_index'] and fp[0]['confirmation_index']==piv[0]['confirmation_index'])

    base=[{'type':'LOW','price':100.0,'confirmation_timestamp':'2026-01-01T10:00:00','pivot_timestamp':'2026-01-01T09:55:00','confirmation_index':1,'pivot_index':0,'threshold_bps':35,'session':'2026-01-01'},{'type':'LOW','price':100.1,'confirmation_timestamp':'2026-01-01T10:05:00','pivot_timestamp':'2026-01-01T10:00:00','confirmation_index':3,'pivot_index':2,'threshold_bps':35,'session':'2026-01-01'}]
    classified=mod.classify_swings(base,15.0);ck('DOUBLE_BOTTOM_USES_OBJECTIVE_TOLERANCE',classified[-1]['swing_labels']==['DOUBLE_BOTTOM_LIKE'])
    cross=mod.classify_swings([base[0],{**base[1],'session':'2026-01-02','confirmation_timestamp':'2026-01-02T10:05:00','pivot_timestamp':'2026-01-02T10:00:00'}],15.0);ck('SWING_LABEL_RESETS_AT_SESSION_BOUNDARY',cross[-1]['swing_labels']==[])

    one=mod.build_zones(classified[:1],15.0,2);ck('ZONE_NOT_ACTIVE_AFTER_ONE_TOUCH',len(one)==0)
    zones=mod.build_zones(classified,15.0,2);expected_center=(100.0+100.1)/2
    ck('ZONE_REQUIRES_MINIMUM_CONFIRMED_TOUCHES',len(zones)==1 and zones[0]['touches']==2)
    ck('ZONE_ACTIVATES_ON_REQUIRED_TOUCH',len(zones)==1 and zones[0]['first_confirmation_timestamp']=='2026-01-01T10:05:00' and zones[0]['activation_touch_count']==2)
    ck('ZONE_CENTER_FROZEN_AT_ACTIVATION',len(zones)==1 and abs(zones[0]['center']-expected_center)<1e-12 and zones[0]['center_frozen_at_activation'] is True)
    third={**base[1],'price':100.12,'confirmation_timestamp':'2026-01-01T10:10:00','pivot_timestamp':'2026-01-01T10:05:00','confirmation_index':5,'pivot_index':4}
    extended=mod.build_zones(mod.classify_swings(base+[third],15.0),15.0,2)
    ck('FUTURE_TOUCH_DOES_NOT_REWRITE_ZONE_CENTER',len(extended)==1 and abs(extended[0]['center']-expected_center)<1e-12 and extended[0]['first_confirmation_timestamp']=='2026-01-01T10:05:00')

    failed=[x['check'] for x in checks if x['status']!='PASS'];result={'schema_version':2,'status':'PATTERN_ATLAS_V1_VALIDATION_PASS' if not failed else 'PATTERN_ATLAS_V1_VALIDATION_FAIL','checks_total':len(checks),'checks_passed':len(checks)-len(failed),'checks_failed':len(failed),'failed_checks':failed,'checks':checks,'runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False}
    print(json.dumps(result,indent=2));return 0 if not failed else 2
if __name__=='__main__':raise SystemExit(main())
