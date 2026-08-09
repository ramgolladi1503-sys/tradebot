import importlib.util, json, sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
P=ROOT/'scripts'/'research'/'hypothesis_factory'/'close_search_domain_from_manifests.py'
spec=importlib.util.spec_from_file_location('close_domain',P); m=importlib.util.module_from_spec(spec); assert spec and spec.loader; sys.modules[spec.name]=m; spec.loader.exec_module(m)


def write(path, **updates):
    x={'schema_version':'screen-v1','run_id':'R1','input_sha256':'sha','hypotheses':100,'promising_not_certified':0,'min_trades':100,'cost_bps':8}
    x.update(updates); path.write_text(json.dumps(x),encoding='utf-8')


def test_load_manifest_requires_zero_survivors(tmp_path):
    p=tmp_path/'m.json'; write(p,promising_not_certified=1)
    with pytest.raises(ValueError,match='nonzero_survivors'):
        m.load_manifest(p)


def test_manifest_sha_supports_cache_manifest_shape(tmp_path):
    p=tmp_path/'m.json'; write(p,input_sha256=None,cache_data_sha256='cache-sha')
    x=m.load_manifest(p)
    assert m.manifest_sha(x)=='cache-sha'


def test_missing_manifest_fails_closed(tmp_path):
    with pytest.raises(ValueError,match='missing_manifest'):
        m.load_manifest(tmp_path/'missing.json')
