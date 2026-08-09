#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys
from pathlib import Path


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:raise RuntimeError(f'module_load_failed:{name}')
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m


def main():
    root=Path(__file__).resolve().parents[3]
    atlas=load('session_scope_atlas',root/'scripts/research/hypothesis_factory/build_market_structure_pattern_atlas_v1.py')
    motif=load('session_scope_motif',root/'scripts/research/hypothesis_factory/build_market_structure_motif_atlas_v1.py')
    checks=[]
    def check(name,ok,detail=None):checks.append({'check':name,'status':'PASS' if ok else 'FAIL','detail':detail})

    # Swing labels must not inherit a prior session's same-type pivot.
    labels=atlas.classify_swings([
        {'type':'HIGH','price':100.0,'session':'S1'},
        {'type':'LOW','price':95.0,'session':'S1'},
        {'type':'HIGH','price':110.0,'session':'S2'},
    ],15.0)
    check('SWING_LABEL_STATE_RESETS_AT_SESSION_BOUNDARY',labels[-1]['swing_labels']==[],labels[-1])

    # Same-session comparison must still work after the reset repair.
    labels2=atlas.classify_swings([
        {'type':'HIGH','price':100.0,'session':'S1'},
        {'type':'LOW','price':95.0,'session':'S1'},
        {'type':'HIGH','price':101.0,'session':'S1'},
    ],15.0)
    check('SAME_SESSION_SWING_LABEL_PRESERVED',labels2[-1]['swing_labels']==['HIGHER_HIGH'],labels2[-1])

    same=[
        {'type':'HIGH','price':100.0,'session':'S1','confirmation_timestamp':'1','pivot_timestamp':'0','swing_labels':[]},
        {'type':'LOW','price':95.0,'session':'S1','confirmation_timestamp':'2','pivot_timestamp':'1','swing_labels':['HIGHER_LOW']},
        {'type':'HIGH','price':102.0,'session':'S1','confirmation_timestamp':'3','pivot_timestamp':'2','swing_labels':['HIGHER_HIGH']},
    ]
    sm=motif.swing_motifs(same,15.0)
    check('SAME_SESSION_SWING_MOTIF_PRESERVED',len(sm)==1 and sm[0]['motif']=='UPTREND_CONTINUATION_SWING',sm)

    cross=[dict(x) for x in same];cross[-1]['session']='S2'
    cm=motif.swing_motifs(cross,15.0)
    check('CROSS_SESSION_SWING_MOTIF_REJECTED',cm==[],cm)

    tri=[
        {'type':'HIGH','price':110.0,'session':'S1','confirmation_timestamp':'1','pivot_timestamp':'0'},
        {'type':'LOW','price':90.0,'session':'S1','confirmation_timestamp':'2','pivot_timestamp':'1'},
        {'type':'HIGH','price':108.0,'session':'S1','confirmation_timestamp':'3','pivot_timestamp':'2'},
        {'type':'LOW','price':92.0,'session':'S1','confirmation_timestamp':'4','pivot_timestamp':'3'},
        {'type':'HIGH','price':106.0,'session':'S1','confirmation_timestamp':'5','pivot_timestamp':'4'},
    ]
    tm=motif.triangle_motifs(tri,15.0)
    check('SAME_SESSION_TRIANGLE_PRESERVED',len(tm)==1,tm)
    tri_cross=[dict(x) for x in tri];tri_cross[-1]['session']='S2'
    tcm=motif.triangle_motifs(tri_cross,15.0)
    check('CROSS_SESSION_TRIANGLE_REJECTED',tcm==[],tcm)

    # Pivot creation must carry session provenance.
    rows=[
        {'timestamp':'2026-01-01T09:15:00','session':'S1','open':100.0,'high':100.0,'low':100.0,'close':100.0},
        {'timestamp':'2026-01-01T09:20:00','session':'S1','open':100.0,'high':101.0,'low':99.9,'close':100.8},
        {'timestamp':'2026-01-01T09:25:00','session':'S1','open':100.8,'high':101.1,'low':99.0,'close':99.2},
    ]
    pv=atlas.confirm_pivots(rows,50.0)
    check('CONFIRMED_PIVOT_CARRIES_SESSION',bool(pv) and all(p.get('session')=='S1' for p in pv),pv)

    failed=[x['check'] for x in checks if x['status']!='PASS']
    out={
        'schema_version':1,
        'status':'MARKET_STRUCTURE_SESSION_SCOPE_PASS' if not failed else 'MARKET_STRUCTURE_SESSION_SCOPE_FAIL',
        'checks_total':len(checks),'checks_passed':len(checks)-len(failed),'checks_failed':len(failed),
        'failed_checks':failed,'checks':checks,
        'runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,
    }
    print(json.dumps(out,indent=2))
    return 0 if not failed else 2


if __name__=='__main__':raise SystemExit(main())
