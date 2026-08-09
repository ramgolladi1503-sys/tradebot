import csv, importlib.util, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
P=ROOT/'scripts'/'research'/'hypothesis_factory'/'build_cross_market_matrix.py'
spec=importlib.util.spec_from_file_location('cross_matrix',P); m=importlib.util.module_from_spec(spec); assert spec and spec.loader; sys.modules[spec.name]=m; spec.loader.exec_module(m)


def write(path, instrument, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as h:
        w=csv.DictWriter(h, fieldnames=['timestamp','instrument','open','high','low','close']); w.writeheader()
        for ts,o,c in rows: w.writerow({'timestamp':ts,'instrument':instrument,'open':o,'high':max(o,c)+1,'low':min(o,c)-1,'close':c})


def test_exact_timestamp_intersection_and_causal_returns(tmp_path):
    b=tmp_path/'b.csv'; n=tmp_path/'n.csv'; s=tmp_path/'s.csv'; out=tmp_path/'matrix.csv'
    common=[('2026-01-01T09:15:00',100,101),('2026-01-01T09:20:00',101,102)]
    write(b,'BANKNIFTY',common)
    write(n,'NIFTY',[('2026-01-01T09:15:00',200,201),('2026-01-01T09:20:00',201,202),('2026-01-01T09:25:00',202,999)])
    write(s,'SENSEX',common)
    r=m.build(b,n,s,out)
    assert r['rows']==2
    rows=list(csv.DictReader(out.open()))
    assert rows[0]['banknifty_ret_1_bps']=='0.0'
    assert float(rows[1]['nifty_ret_1_bps'])>0
    assert all(x['timestamp']!='2026-01-01T09:25:00' for x in rows)
    assert r['feature_timing']=='CURRENT_OR_PRIOR_ONLY'
    assert r['runtime_authority']=='NONE'


def test_future_mutation_does_not_change_earlier_feature(tmp_path):
    b=tmp_path/'b.csv'; n=tmp_path/'n.csv'; s=tmp_path/'s.csv'; o1=tmp_path/'m1.csv'; o2=tmp_path/'m2.csv'
    base=[('2026-01-01T09:15:00',100,101),('2026-01-01T09:20:00',101,102),('2026-01-01T09:25:00',102,103)]
    write(b,'BANKNIFTY',base); write(n,'NIFTY',base); write(s,'SENSEX',base)
    m.build(b,n,s,o1)
    altered=base[:-1]+[('2026-01-01T09:25:00',102,9999)]
    write(n,'NIFTY',altered); m.build(b,n,s,o2)
    r1=list(csv.DictReader(o1.open())); r2=list(csv.DictReader(o2.open()))
    assert r1[1]==r2[1]
