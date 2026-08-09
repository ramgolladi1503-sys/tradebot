#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys
from pathlib import Path

def load_module(name:str,path:Path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:raise RuntimeError(f'module_load_failed:{path}')
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod

def main()->int:
    root=Path(__file__).resolve().parents[3]
    states_mod=load_module('behavior_states_v1',root/'scripts/research/hypothesis_factory/build_behavior_states_v1.py')
    graph_mod=load_module('behavior_graph_v1',root/'scripts/research/hypothesis_factory/build_behavior_episode_graph_v1.py')
    miner_mod=load_module('behavior_miner_v1',root/'scripts/research/hypothesis_factory/mine_behavior_sequences_v1.py')
    compiler_mod=load_module('behavior_compiler_v1',root/'scripts/research/hypothesis_factory/compile_behavior_hypotheses_v1.py')
    checks=[]
    def ck(name,ok,detail=None):checks.append({'check':name,'status':'PASS' if ok else 'FAIL','detail':detail})
    def row(i,o,h,l,c,session='2026-01-01'):
        return {'timestamp':f'{session}T09:{15+i:02d}:00','session':session,'open':o,'high':h,'low':l,'close':c}
    rows=[row(0,100.00,100.10,99.95,100.00),row(1,100.00,100.12,99.98,100.05),row(2,100.05,100.16,100.00,100.10),row(3,100.10,100.18,100.02,100.12),row(4,100.12,100.20,100.05,100.11),row(5,100.11,100.22,100.06,100.12),row(6,100.12,100.25,100.08,100.13),row(7,100.13,100.27,100.09,100.14),row(8,100.14,100.30,99.70,100.26),row(9,100.26,100.85,100.20,100.80),row(10,100.80,101.30,100.76,101.22),row(11,101.22,101.25,100.50,100.56),row(0,200.00,200.10,199.95,200.00,'2026-01-02'),row(1,200.00,200.12,199.98,200.04,'2026-01-02'),row(2,200.04,200.15,199.97,200.02,'2026-01-02'),row(3,200.02,200.08,199.00,199.80,'2026-01-02')]
    cfg={'rolling_range_lookback':4,'rolling_return_lookback':3,'recent_extreme_lookback':4,'compression_ratio_max':0.75,'expansion_ratio_min':1.50,'strong_body_fraction_min':0.62,'rejection_wick_fraction_min':0.35,'escape_threshold_bps':8.0,'recovery_threshold_bps':3.0,'acceleration_ratio_min':1.40,'deceleration_ratio_max':0.65}
    states=states_mod.build_states(rows,cfg)
    prefix_len=10;prefix_states=states_mod.build_states(rows[:prefix_len],cfg);full_prefix=[s for s in states if int(s['row_index'])<prefix_len]
    ck('PREFIX_REPRODUCIBILITY',prefix_states==full_prefix,{'prefix':len(prefix_states),'full_projection':len(full_prefix)})
    extended=rows+[row(4,199.80,210.0,199.70,209.0,'2026-01-02')]
    ext_states=states_mod.build_states(extended,cfg);ext_projection=[s for s in ext_states if int(s['row_index'])<len(rows)]
    ck('FUTURE_EXTENSION_INVARIANCE',ext_projection==states,{'base':len(states),'extended_projection':len(ext_projection)})
    ck('CONFIRMATION_TIMESTAMP_CAUSALITY',all(s['confirmation_timestamp']==s['timestamp'] for s in states))
    first_s2=next(s for s in states if s['session']=='2026-01-02' and int(s['row_index'])==12)
    f=first_s2.get('features',{})
    ck('SESSION_BOUNDARY_ISOLATION',f.get('prior_high') is None and f.get('prior_low') is None and f.get('range_ratio') is None and f.get('close_to_close_return_bps') is None)
    forbidden=('forward','future','pnl','profit','outcome','target','label')
    dumped=json.dumps(states).lower()
    ck('NO_OUTCOME_COLUMNS_IN_STATES',not any(tok in dumped for tok in forbidden),[tok for tok in forbidden if tok in dumped])
    ck('DETERMINISTIC_STATE_GENERATION',states_mod.build_states(rows,cfg)==states)
    episodes=graph_mod.build_episodes(states,max_gap_bars=1)
    ck('EPISODE_DEDUP_AND_COLLAPSE',bool(episodes) and all(len(e['state_sequence'])>=1 and len(e['state_sets'])<=e['duration_bars'] for e in episodes),{'episodes':len(episodes)})
    ck('EPISODE_SESSION_BOUNDARY_ISOLATION',all('::' in e['episode_id'] and e['session'] in {'2026-01-01','2026-01-02'} for e in episodes))
    ck('DETERMINISTIC_EPISODE_GRAPH',graph_mod.build_episodes(states,max_gap_bars=1)==episodes)
    base_seq=['COMPRESSION','FAILED_DOWNSIDE_ESCAPE','LOWER_REJECTION','EXPANSION'];alt_seq=['COMPRESSION','UPSIDE_ESCAPE','EXPANSION']
    synthetic=[]
    for i in range(8):synthetic.append({'episode_id':f'S{i}','session':f'2026-02-{i+1:02d}','state_sequence':base_seq})
    for i in range(3):synthetic.append({'episode_id':f'A{i}','session':f'2026-03-{i+1:02d}','state_sequence':alt_seq})
    seqs=miner_mod.mine_sequences(synthetic,min_len=2,max_len=4,min_support=5,min_sessions=5)
    ck('SEQUENCE_MINER_FINDS_RECURRENT_NON_OUTCOME_SEQUENCE',any(r['state_sequence']==base_seq for r in seqs),{'sequence_records':len(seqs)})
    ck('SEQUENCE_MINER_OMITS_LOW_SUPPORT_SEQUENCE',not any(r['state_sequence']==alt_seq for r in seqs))
    ck('DETERMINISTIC_SEQUENCE_MINING',miner_mod.mine_sequences(synthetic,min_len=2,max_len=4,min_support=5,min_sessions=5)==seqs)
    passports=compiler_mod.compile_passports(seqs,'a'*64,'b'*64,'TEST_FAMILY',max_candidates=5)
    ck('PASSPORTS_FREEZE_UNKNOWN_DIRECTION_AND_NO_ENTRY_EXIT',bool(passports) and all(p['direction']=='UNKNOWN' and p['entry_concept']=='NONE' and p['exit_concept']=='NONE' for p in passports))
    ck('STABLE_CANDIDATE_PASSPORT_HASHING',compiler_mod.compile_passports(seqs,'a'*64,'b'*64,'TEST_FAMILY',max_candidates=5)==passports)
    ck('PASSPORTS_DO_NOT_CLAIM_EDGE',all(p['edge_claimed'] is False and p['forward_outcomes_used'] is False and p['locked_outcomes_accessed'] is False for p in passports))
    failed=[c['check'] for c in checks if c['status']!='PASS']
    result={'schema_version':1,'status':'BEHAVIOR_DISCOVERY_IMPLEMENTATION_VALID' if not failed else 'BEHAVIOR_DISCOVERY_IMPLEMENTATION_INVALID','checks_total':len(checks),'checks_passed':len(checks)-len(failed),'checks_failed':len(failed),'failed_checks':failed,'checks':checks,'runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'forward_outcomes_used':False,'locked_outcomes_accessed':False,'interpretation':'Synthetic adversarial validation of causality, determinism, episode collapse, recurrence mining, and passport freezing. This does not prove a structural edge.'}
    print(json.dumps(result,indent=2,sort_keys=True));return 0 if not failed else 2
if __name__=='__main__':raise SystemExit(main())
