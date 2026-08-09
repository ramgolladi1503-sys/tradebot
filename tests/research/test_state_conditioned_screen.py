import importlib.util, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
P=ROOT/'scripts'/'research'/'hypothesis_factory'/'run_state_conditioned_screen.py'
spec=importlib.util.spec_from_file_location('state_screen',P); m=importlib.util.module_from_spec(spec); assert spec and spec.loader; sys.modules[spec.name]=m; spec.loader.exec_module(m)


def row(ts,o,h,l,c):
    return {'timestamp':ts,'instrument':'BANKNIFTY','open':str(o),'high':str(h),'low':str(l),'close':str(c)}


def test_prior_state_uses_only_previous_session():
    a=[row('2026-01-01T09:15:00',100,102,99,101),row('2026-01-01T15:25:00',101,103,100,102)]
    b=[row('2026-01-02T09:15:00',110,111,109,110),row('2026-01-02T15:25:00',110,112,108,111)]
    states=m.prior_state([('2026-01-01',a),('2026-01-02',b)])
    assert '2026-01-01' not in states
    assert states['2026-01-02']['prior_close']==102


def test_signal_is_causal_under_future_mutation():
    s=[row('2026-01-02T09:15:00',100,101,99,100),row('2026-01-02T09:20:00',100,102,100,102),row('2026-01-02T09:25:00',102,104,101,104),row('2026-01-02T09:30:00',104,105,103,104)]
    h={'family':'opening_momentum','regime':'prior_up','direction':1,'threshold_bps':10,'hold_bars':2,'lookback':3}
    state={'prior_ret_bps':10,'prior_range_bps':100,'prior_close':99,'median_prior_range':50}
    before=m.signal(h,s,2,state)
    s[3]=row('2026-01-02T09:30:00',1,9999,1,9999)
    after=m.signal(h,s,2,state)
    assert before==after


def test_generation_has_state_conditioning_and_large_grid():
    hs=m.generate('BANKNIFTY')
    assert len(hs) >= 600
    assert {'prior_up','prior_down','prior_high_vol','prior_low_vol'} == {h['regime'] for h in hs}
    assert {'gap_follow','gap_fade','opening_momentum','intraday_breakout','intraday_reversion'} == {h['family'] for h in hs}


def test_missing_prior_state_fails_closed_without_exception():
    first=[
        row('2026-01-01T09:15:00',100,101,99,100),
        row('2026-01-01T09:20:00',100,102,99,101),
        row('2026-01-01T09:25:00',101,103,100,102),
        row('2026-01-01T09:30:00',102,104,101,103),
        row('2026-01-01T09:35:00',103,105,102,104),
    ]
    h={'id':'FIRST','family':'opening_momentum','regime':'prior_up','direction':1,'threshold_bps':10,'hold_bars':2,'lookback':3}
    result=m.evaluate(h,[('2026-01-01',first)],{},cost=8,min_trades=1)
    assert result['trades']==0
    assert result['sessions_traded']==0
    assert result['sessions_skipped_missing_prior_state']==1
    assert result['status']=='REJECTED'
    assert m.signal(h, first, 3, {}) is False
