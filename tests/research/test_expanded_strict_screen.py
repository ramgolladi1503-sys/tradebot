import csv, importlib.util, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
P=ROOT/'scripts'/'research'/'hypothesis_factory'/'run_expanded_strict_screen.py'
spec=importlib.util.spec_from_file_location('expanded_screen',P); m=importlib.util.module_from_spec(spec); assert spec and spec.loader; sys.modules[spec.name]=m; spec.loader.exec_module(m)


def row(ts,o,h,l,c):
    return {'timestamp':ts,'instrument':'BANKNIFTY','open':str(o),'high':str(h),'low':str(l),'close':str(c)}


def test_signal_is_causal_with_future_mutation():
    s=[
      row('2026-01-01T09:15:00',100,101,99,100),
      row('2026-01-01T09:20:00',100,102,100,102),
      row('2026-01-01T09:25:00',102,104,102,104),
      row('2026-01-01T09:30:00',104,106,103,106),
      row('2026-01-01T09:35:00',106,107,105,106.5),
    ]
    h={'family':'momentum_continuation','direction':1,'lookback':2,'threshold_bps':100,'hold_bars':2}
    before=m.signal(h,s,3)
    s[4]=row('2026-01-01T09:35:00',1,9999,1,9999)
    after=m.signal(h,s,3)
    assert before==after


def test_evaluation_never_overlaps_positions():
    s=[]
    price=100.0
    for i in range(20):
        ts=f'2026-01-01T09:{15+i*5:02d}:00' if 15+i*5<60 else f'2026-01-01T10:{(15+i*5)%60:02d}:00'
        s.append(row(ts,price,price+2,price-1,price+1.5)); price+=1.5
    h={'id':'X','family':'momentum_continuation','direction':1,'lookback':2,'threshold_bps':1,'hold_bars':3}
    r=m.evaluate(h,{'2026-01-01':s},cost=0,min_trades=1)
    assert r['overlapping_trades_allowed'] is False
    assert r['trades'] <= 5


def test_generation_is_materially_larger_than_baseline_supported_set():
    hs=m.generate('BANKNIFTY')
    assert len(hs) >= 500
    assert {'opening_drive','opening_pullback','compression_breakout','momentum_continuation','range_failure'} == {h['family'] for h in hs}
    assert all(h['hold_bars'] in {2,3,6,12} for h in hs)


def test_csv_export_handles_family_specific_fields(tmp_path):
    results=[
        {'family':'opening_drive','open_bars':3,'threshold_bps':25,'trades':100},
        {'family':'opening_pullback','open_bars':6,'retrace':0.5,'threshold_bps':40,'trades':120},
        {'family':'compression_breakout','lookback':6,'threshold_bps':35,'trades':150},
    ]
    path=tmp_path/'leaderboard.csv'
    m.write_results_csv(path,results)
    with path.open(newline='',encoding='utf-8') as h:
        rows=list(csv.DictReader(h))
    assert len(rows)==3
    assert 'retrace' in rows[0]
    assert 'open_bars' in rows[0]
    assert 'lookback' in rows[0]
