import importlib.util, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
P=ROOT/'scripts'/'research'/'hypothesis_factory'/'run_cross_market_screen.py'
spec=importlib.util.spec_from_file_location('cross_screen',P); m=importlib.util.module_from_spec(spec); assert spec and spec.loader; sys.modules[spec.name]=m; spec.loader.exec_module(m)


def row(ts,b,n,s):
    return {'timestamp':ts,'banknifty_close':str(b),'nifty_close':str(n),'sensex_close':str(s)}


def test_signal_is_causal_under_future_mutation():
    s=[row('2026-01-01T09:15:00',100,100,100),row('2026-01-01T09:20:00',100,102,102),row('2026-01-01T09:25:00',101,104,104),row('2026-01-01T09:30:00',101,105,105)]
    h={'family':'leader_consensus','direction':1,'threshold_bps':50,'lookback':2,'hold_bars':2}
    before=m.signal(h,s,2)
    s[3]=row('2026-01-01T09:30:00',9999,1,1)
    after=m.signal(h,s,2)
    assert before==after


def test_generation_has_all_cross_market_families_and_material_grid():
    hs=m.generate()
    assert len(hs)==800
    assert {'leader_consensus','nifty_lead','sensex_lead','relative_strength','cross_market_divergence'} == {h['family'] for h in hs}


def test_evaluation_non_overlap_and_research_only():
    s=[]
    for i in range(20):
        minute=15+i*5
        hh=9+minute//60; mm=minute%60
        s.append(row(f'2026-01-01T{hh:02d}:{mm:02d}:00',100+i*0.2,100+i*1.0,100+i*1.0))
    h={'id':'X','family':'leader_consensus','direction':1,'threshold_bps':1,'hold_bars':3,'lookback':1}
    r=m.evaluate(h,{'2026-01-01':s},0,1)
    assert r['overlapping_trades_allowed'] is False
    assert r['trades'] <= 5
    assert r['certification']=='NOT_CERTIFIED'
    assert r['runtime_authority']=='NONE'
    assert r['broker_actions_allowed'] is False
