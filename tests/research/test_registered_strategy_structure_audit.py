import importlib.util
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
P=ROOT/'scripts'/'research'/'hypothesis_factory'/'audit_registered_strategy_structure.py'
spec=importlib.util.spec_from_file_location('strategy_structural_audit',P)
m=importlib.util.module_from_spec(spec); assert spec and spec.loader; sys.modules[spec.name]=m; spec.loader.exec_module(m)


def test_audit_uses_canonical_strategy_registry():
    result=m.run(ROOT)
    assert result['registered_strategy_count'] > 0
    ids={x['strategy_id'] for x in result['strategies']}
    assert 'opening_range_retest' in ids
    assert 'trend_pullback' in ids
    assert 'mean_reversion_extension' in ids
    assert result['runtime_authority']=='NONE'
    assert result['broker_actions_allowed'] is False


def test_opening_range_retest_has_temporal_contract_markers():
    result=m.run(ROOT)
    row=next(x for x in result['strategies'] if x['strategy_id']=='opening_range_retest')
    majors=[x for x in row['findings'] if x['severity'] in {'MAJOR','CRITICAL'}]
    assert not [x for x in majors if x['code']=='TEMPORAL_CONTRACT_MARKER_MISSING']
    assert row['verdict'] in {'STRUCTURALLY_VALID_WITH_LIMITATIONS','STRUCTURALLY_VALID'}


def test_mean_reversion_missing_declared_oscillator_is_not_silently_passed():
    result=m.run(ROOT)
    row=next(x for x in result['strategies'] if x['strategy_id']=='mean_reversion_extension')
    details={(x['code'],x['detail']) for x in row['findings']}
    assert ('REQUIRED_EVIDENCE_NOT_CONSUMED','oscillator_confirmation') in details
    assert row['verdict']=='STRUCTURAL_REPAIR_REQUIRED'


def test_no_static_audit_grants_certification_or_runtime_authority():
    result=m.run(ROOT)
    assert result['certification']=='NOT_CERTIFIED'
    for row in result['strategies']:
        assert row['runtime_authority']=='NONE'
        assert row['broker_actions_allowed'] is False
