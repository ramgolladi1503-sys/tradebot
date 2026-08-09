import importlib.util
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
P=ROOT/'scripts'/'research'/'hypothesis_factory'/'audit_registered_strategy_structure.py'
spec=importlib.util.spec_from_file_location('strategy_structural_audit',P)
m=importlib.util.module_from_spec(spec); assert spec and spec.loader; sys.modules[spec.name]=m; spec.loader.exec_module(m)


def result():
    return m.run(ROOT)


def test_registry_and_policy_cover_same_21_entries():
    r=result()
    assert r['registered_strategy_count']==21
    assert r['policy_count']==21
    ids={x['strategy_id'] for x in r['strategies']}
    assert ids==set(m.STRATEGY_POLICIES)
    assert r['runtime_authority']=='NONE'
    assert r['broker_actions_allowed'] is False


def test_registry_parser_preserves_mean_reversion_required_evidence():
    specs=m.load_registry_specs(ROOT)
    row=next(x for x in specs if x.strategy_id=='mean_reversion_extension')
    assert 'mean_reversion_anchor' in row.required_evidence_keys
    assert 'oscillator_confirmation' in row.required_evidence_keys


def test_semantic_matcher_does_not_treat_version_as_rsi():
    facts={'names':['strategy_version','price_structure_score'],'attributes':[],'calls':[],'string_literals':['v1','strategy_version']}
    assert m.semantic_evidence_consumed(facts, ('rsi',)) is False
    facts['names'].append('rsi_value')
    assert m.semantic_evidence_consumed(facts, ('rsi',)) is True


def test_repaired_high_risk_strategies_are_structurally_valid():
    r=result(); rows={x['strategy_id']:x for x in r['strategies']}
    for strategy_id in (
        'vwap_orb','pairs_arbitrage','mean_reversion_extension',
        'compression_breakout','failed_breakout_trap','exhaustion_reversal',
        'event_volatility_expansion','volatility_trend','zero_hero_expiry',
    ):
        assert rows[strategy_id]['verdict']=='STRUCTURALLY_VALID', (strategy_id, rows[strategy_id]['findings'])


def test_temporal_strategies_are_structurally_valid():
    r=result(); rows={x['strategy_id']:x for x in r['strategies']}
    for strategy_id in ('opening_range_retest','trend_pullback','vwap_reclaim_rejection','compression_breakout','failed_breakout_trap'):
        assert rows[strategy_id]['verdict']=='STRUCTURALLY_VALID', (strategy_id, rows[strategy_id]['findings'])


def test_meta_layers_are_provenance_only_and_valid():
    r=result(); rows={x['strategy_id']:x for x in r['strategies']}
    assert rows['ensemble']['verdict']=='STRUCTURALLY_VALID', rows['ensemble']['findings']
    assert rows['pro_strategy']['verdict']=='STRUCTURALLY_VALID', rows['pro_strategy']['findings']
    for strategy_id in ('ensemble','pro_strategy'):
        source=m.read_repo_text(ROOT, m.dotted_repo_path(rows[strategy_id]['module_path'])) or ''
        assert 'source_sha256' in source
        assert 'structural_status' in source
        assert 'contract_valid' in source
        assert 'freshness_valid' in source


def test_support_components_are_not_misclassified_as_alpha():
    r=result(); rows={x['strategy_id']:x for x in r['strategies']}
    assert rows['option_pressure_confirmation']['verdict']=='SUPPORT_COMPONENT_VALID'
    assert rows['no_trade_chop']['verdict']=='SUPPORT_COMPONENT_VALID'


def test_terminal_structural_gate_has_no_unresolved_verdicts():
    r=result()
    assert r['status']=='STRUCTURAL_GATE_PASS', [(x['strategy_id'],x['verdict'],x['findings']) for x in r['strategies'] if x['verdict'] not in m.PASS_VERDICTS]
    assert r['all_structurally_closed'] is True
    assert not ({'UNKNOWN','STRUCTURALLY_VALID_WITH_LIMITATIONS','STRUCTURAL_REPAIR_REQUIRED','NOT_IMPLEMENTING_CLAIMED_STRATEGY'} & set(r['verdict_counts']))
    assert sum(r['verdict_counts'].values())==21


def test_gate_never_grants_certification_or_runtime_authority():
    r=result()
    assert r['certification']=='NOT_CERTIFIED'
    assert r['runtime_authority']=='NONE'
    assert r['broker_actions_allowed'] is False
    for row in r['strategies']:
        assert row['runtime_authority']=='NONE'
        assert row['broker_actions_allowed'] is False
