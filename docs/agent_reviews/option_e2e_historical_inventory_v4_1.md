# Option E2E Historical Inventory v4.1

candidate_id: option_e2e_historical_inventory_v4_1
decision: HISTORICAL_STRATEGY_INVENTORY_V4_1_REPAIRED
mode: OFFLINE_INVENTORY_NO_ECONOMIC_REPLAY
reason: Historical inventory separates counted strategies from support, aggregate and fixture entities while mapping all required historical research families.
timestamp: 2026-07-24T00:21:23+05:30
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
append: false
source: Subagent A1 commit e6f92961245a2934efb9411e3112e73e5aa53469
source_head: `c0a3498424744b623257845068528ccf528396df`
inventory_sha256: `25b369552dd1ea7b891edb4bca844f8f32d1a27f21ce99e120430d6cc58098bc`

## Scope

This repair inventories historical strategy and strategy-adjacent entities only. It does not run economic replay, broker APIs, resolver logic, replay engine changes, WFA, production files, `core/**`, or `strategies/**` edits.

## Counts

- Strategy files scanned: 31
- Entities total: 33
- Counted strategies: 18
- Non-strategy support entities excluded from strategy count: 12
- Aggregate/registry entities: 3
- Evidence files with family or verdict hits: 372
- Required families with evidence: 16 / 16
- Durable verdict labels mapped: 154

## Entity Separation

The following ids are explicitly not counted as strategies: `BANKNIFTY_INTRADAY`, `NIFTY_INTRADAY`, `POSITION_SIZER`, `PRO_DECISION_ADAPTER`, `RISK_MANAGER`, `SENSEX_INTRADAY`, `SOFT_SIGNAL`, `TEST_STRAT`, `TRADE_BUILDER`, `_INIT_`, `_UTILS`.

## Counted Strategy Entities

- `COMPRESSION_BREAKOUT`: `strategies/movement/compression_breakout.py`; families=['COMPRESSION', 'ORB_RETEST_DRIVE', 'VWAP_VARIANTS']; sha256=`c32ef22b278ad883e577ab90aac2f6e84b546eefda0f43e56e55ef0ccb00b0e7`
- `EVENT_VOLATILITY_EXPANSION`: `strategies/movement/event_volatility_expansion.py`; families=['VWAP_VARIANTS']; sha256=`530a270aab16fe9155ccb0fb1ce48cf13cb5b58ef3dec33010f3c6fbcad2f159`
- `EXHAUSTION_REVERSAL`: `strategies/movement/exhaustion_reversal.py`; families=['EXHAUSTION', 'TREND', 'VWAP_VARIANTS']; sha256=`c11d74395e48fa0f00786d5d3ddeb1c5ea480d2dd4c82ccdb04df62fde3a2312`
- `FAILED_BREAKOUT_TRAP`: `strategies/movement/failed_breakout_trap.py`; families=['ORB_RETEST_DRIVE', 'VWAP_VARIANTS']; sha256=`353ec47ad43e16ea54aa6a3fbeb0c81a24dcb8fdc0d75dab9c165fc6fee9d427`
- `LATE_DAY_MOMENTUM`: `strategies/movement/late_day_momentum.py`; families=['TREND', 'VWAP_VARIANTS']; sha256=`792d03df8df539f3484b1f0e5e0d4f501e34873c7958afc23281b1e6b0c539ef`
- `MEAN_REVERSION_EXTENSION`: `strategies/movement/mean_reversion_extension.py`; families=['MRE', 'TREND', 'VWAP_VARIANTS']; sha256=`d61e3e68ea550e0facdaee5438bf2deea749c9d15f26a4bbdff3c52124d49b4b`
- `NO_TRADE_CHOP`: `strategies/movement/no_trade_chop.py`; families=[]; sha256=`29c914466488eb38b95dcf980c010419b4abad0917fbdb6b36f47adf0ed9d52e`
- `OPENING_DRIVE`: `strategies/movement/opening_drive.py`; families=['ORB_RETEST_DRIVE', 'VWAP_VARIANTS']; sha256=`e0dcac5aeba30696dbdb734a2ffc7e78efe0c59e4c3ebf2bb5997774b3797632`
- `OPENING_RANGE_BREAKOUT`: `strategies/movement/opening_range_breakout.py`; families=['ORB_RETEST_DRIVE', 'VWAP_VARIANTS']; sha256=`06be67cf8bac5b4d4901929b77e638c726a6b4910f646d20780e584327144b2e`
- `OPTION_PRESSURE`: `strategies/movement/option_pressure.py`; families=[]; sha256=`408bf0e7bd6fa4baa842cded3e4427fd05196bedb7154adbeb3283f15dc25f85`
- `TREND_PULLBACK`: `strategies/movement/trend_pullback.py`; families=['TREND', 'VWAP_VARIANTS']; sha256=`36a86be053398daaf72b885a9d214f3545df97d5a25d2ca3b3dd7a5aad8b51e1`
- `VWAP_RECLAIM`: `strategies/movement/vwap_reclaim.py`; families=['VWAP_VARIANTS']; sha256=`7a30df420d2b70b4533c96e07bcccf784fbfe9e28e504cc2af7ff0aaa89566fc`
- `PAIRS_ARBITRAGE`: `strategies/pairs_arbitrage.py`; families=[]; sha256=`454af4eac37766666f5354c275c6c2255e713e5726fe32a1146d51195ec1600d`
- `SIMPLE_ORB`: `strategies/simple_orb.py`; families=['ORB_RETEST_DRIVE']; sha256=`89feacc9f28c8614ee3c102fea6399628a40fecc7ab9e4b14b81c415c12ee1f5`
- `VOLATILITY_TREND`: `strategies/volatility_trend.py`; families=['TREND', 'VWAP_VARIANTS']; sha256=`d2de9d9e2efd71cbad9cd4d485e13c2300ef7ba4304ab8324f428ad5d30fb3bd`
- `VWAP_ORB`: `strategies/vwap_orb.py`; families=['ORB_RETEST_DRIVE', 'VWAP_VARIANTS']; sha256=`69e6c6a28e88e910093b50cecc2f92dc53bc123c7230f957fd10165bd542738b`
- `ZERO_HERO`: `strategies/zero_hero.py`; families=['TREND', 'VWAP_VARIANTS', 'ZERO_HERO']; sha256=`38d8101ab60bbda56501f8ce9db12bf43b71afb2818e71dea7bee4e52be703f4`
- `HTF_OPENING_DRIVE_CONT`: `strategies/htf_opening_drive_cont.py`; families=['HTF']; sha256=`None`

## Non-Strategy / Aggregate Entities

- `_INIT_`: entity_type=`non_strategy_support`; path=`strategies/__init__.py`; sha256=`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- `BANKNIFTY_INTRADAY`: entity_type=`non_strategy_support`; path=`strategies/banknifty_intraday.py`; sha256=`945f53c68ab33933f21ef692a335581e78df2f12f9433edcc7515597b5fd252b`
- `ENSEMBLE`: entity_type=`aggregate_or_deferred_strategy`; path=`strategies/ensemble.py`; sha256=`1b333724385cdedbe50144cdf40a778b13f66b9f061565e5b6b99905ec4adc1e`
- `_INIT_`: entity_type=`non_strategy_support`; path=`strategies/movement/__init__.py`; sha256=`719f9c94dd5ae1af7e29c7975ab4cac67f0f6cacbb2750ccd5c91b95b0046d85`
- `_UTILS`: entity_type=`non_strategy_support`; path=`strategies/movement/_utils.py`; sha256=`f02a0858fba8f6b186be272cfbb6c48a3b07458987d46df5db542d52e6239924`
- `NIFTY_INTRADAY`: entity_type=`non_strategy_support`; path=`strategies/nifty_intraday.py`; sha256=`86f0aff6e0e893cb6e39886502a74c7abb23796264a52da01e134abdac11a31e`
- `POSITION_SIZER`: entity_type=`non_strategy_support`; path=`strategies/position_sizer.py`; sha256=`a3d49538f326e1c70dc20018c6bdb91e7890d36f367954532c13ca3deaaadd18`
- `PRO_DECISION_ADAPTER`: entity_type=`non_strategy_support`; path=`strategies/pro_layer/pro_decision_adapter.py`; sha256=`28ecba1172eb2abf9613db600e5da5c3575953e0941307bb2f408bc77cf00118`
- `PRO_STRATEGY_ENGINE`: entity_type=`aggregate_engine`; path=`strategies/pro_layer/pro_strategy_engine.py`; sha256=`66b3e499f605edcb83e0eb4616f86643c0430bf95a0c910b70c9e5d0698e8eb0`
- `RISK_MANAGER`: entity_type=`non_strategy_support`; path=`strategies/risk_manager.py`; sha256=`7c006ad0e8a35b384c4694bf0e3a375ee2d21c5fabeaa1b3161bb25143f18294`
- `SENSEX_INTRADAY`: entity_type=`non_strategy_support`; path=`strategies/sensex_intraday.py`; sha256=`188152c9990675d0cb9d2ae712096a276df4786f06ef1db386bbee4bac4a69d0`
- `SOFT_SIGNAL`: entity_type=`non_strategy_support`; path=`strategies/soft_signal.py`; sha256=`9b10b8b247bcbf4bc3f7d86e65f2482645edd061fa4c71cefae4b3f4a92c3411`
- `STRATEGY_REGISTRY`: entity_type=`registry`; path=`strategies/strategy_registry.py`; sha256=`6cf25db0fb7fb4156570751bfbc7edcf20ecfca154414c08c2473864d86e1323`
- `TRADE_BUILDER`: entity_type=`non_strategy_support`; path=`strategies/trade_builder.py`; sha256=`aba803f6ca5954e63342c218682694f0efe70f6c140e029b6c3d23521b042e3a`
- `TEST_STRAT`: entity_type=`non_strategy_support`; path=`strategies/test_strat.py`; sha256=`None`

## Required Family Evidence Map

### RESIDUAL_MEAN_REVERSION
- `research/option_e2e_recertification_v4/inventory/historical_claim_map_v4.json`; sha256=`505890ec246a66d94b2653e857d0cbebccccffcbd1bc12a829db46124eb85ac7`; verdicts=`MENTION_ONLY`
- `git:fb4bacd8efe8aec6133134fadfcfbdb5dbb42fb6`; sha256=`fb4bacd8efe8aec6133134fadfcfbdb5dbb42fb6`; verdicts=`GIT_HISTORY_MENTION`
- `git:199ae72c8ccaa76d3de54647fb6feaa0e66dda3f`; sha256=`199ae72c8ccaa76d3de54647fb6feaa0e66dda3f`; verdicts=`GIT_HISTORY_MENTION`
- `git:11e3241d1f78305726e4a9c35c8c23b059f6132b`; sha256=`11e3241d1f78305726e4a9c35c8c23b059f6132b`; verdicts=`GIT_HISTORY_MENTION`
- `git:c862b058d96ceeeae7fbf5ed6901374bda22d2d0`; sha256=`c862b058d96ceeeae7fbf5ed6901374bda22d2d0`; verdicts=`GIT_HISTORY_MENTION`
- `git:d1da799954e296f4672d51d2c6801d9b08f44cb4`; sha256=`d1da799954e296f4672d51d2c6801d9b08f44cb4`; verdicts=`GIT_HISTORY_MENTION`
- `git:6d98f3ddcf564b46e4bf7a479f964a17dc2fb6d7`; sha256=`6d98f3ddcf564b46e4bf7a479f964a17dc2fb6d7`; verdicts=`GIT_HISTORY_MENTION`
- `git:128ee309968489c51170fe0ad459ba89788bbeef`; sha256=`128ee309968489c51170fe0ad459ba89788bbeef`; verdicts=`GIT_HISTORY_MENTION`
- `git:e3aa9855b3ad1257b2f09c151042d26722d75b96`; sha256=`e3aa9855b3ad1257b2f09c151042d26722d75b96`; verdicts=`GIT_HISTORY_MENTION`
- `git:7da8c83bb68b4abe860b0e8e6fdb16cd87e41d28`; sha256=`7da8c83bb68b4abe860b0e8e6fdb16cd87e41d28`; verdicts=`GIT_HISTORY_MENTION`

### OPENING_STATE_MOMENTUM
- `tests/test_governed_strategy_research.py`; sha256=`e70c759a90e3f6504bbfd3bcddffb5ad5836b8ad209ddbcc3011bd3fb7b6dbff`; verdicts=`VALIDATION_FAILED`

### CONSTITUENT_LEAD_LAG_WEIGHTED
- `docs/agent_reviews/four_strategy_contract_bundle_v1.json`; sha256=`8b7df7e030306b9699347f9b3ed1c421fd8dfc302c7902a178e8111cb177d8c2`; verdicts=`ALREADY_EMITTED`, `CANDIDATE_IDENTITY_PROVEN`, `FAIL_CLOSED`, `INVALIDATED`, `OPTIONAL_PROVENANCE_ONLY`
- `tests/test_candidate_ranking.py`; sha256=`c7d7ccc57b8cb1af2a72be4e70865d40076de4e884d06bb31855950d8e0d06de`; verdicts=`SUBSCRIPTION_FAILED`
- `tests/test_candidate_ranking_contract_snapshots.py`; sha256=`bb90f2e92300bbb1fd5bc1db369e3896c9f7f837a474ed1af24cf4728ccbbe5d`; verdicts=`MENTION_ONLY`
- `tests/test_candidate_ranking_profile_metadata.py`; sha256=`0bbd1e9a6529320eba8cbe904d965a3879454dfa789f94aa3ff3d2a412c1f6e6`; verdicts=`MENTION_ONLY`
- `tests/test_strategy_regime_policy.py`; sha256=`cd07033ce2bbab1935da9f1b5ce50e9db856262dd57fc770fe10946dcbc8a3ac`; verdicts=`MENTION_ONLY`
- `git:8ffdc6c5e46366caf4defd70ce4374e9fc8de748`; sha256=`8ffdc6c5e46366caf4defd70ce4374e9fc8de748`; verdicts=`GIT_HISTORY_MENTION`
- `git:db86b6600e7f853cd45477d125d3f493f8910543`; sha256=`db86b6600e7f853cd45477d125d3f493f8910543`; verdicts=`GIT_HISTORY_MENTION`
- `git:b55906748273cd5272842c8b081ddcb3120667a9`; sha256=`b55906748273cd5272842c8b081ddcb3120667a9`; verdicts=`GIT_HISTORY_MENTION`
- `git:b64c0c354d5a5d4b532f8fcd4433a5cdf1608fbb`; sha256=`b64c0c354d5a5d4b532f8fcd4433a5cdf1608fbb`; verdicts=`GIT_HISTORY_MENTION`
- `git:e076385ebbe7f0c39aab5b692fc59d22799cd55d`; sha256=`e076385ebbe7f0c39aab5b692fc59d22799cd55d`; verdicts=`GIT_HISTORY_MENTION`

### CONSTITUENT_BREADTH_UNWEIGHTED
- `docs/agent_reviews/pr278_trade_builder_candidate_breadth_expiry.md`; sha256=`0fbdcce2d3ebffc45d657ffbaee15b487041d20a754e3e4e1d8cce8c77017921`; verdicts=`MENTION_ONLY`
- `docs/agent_reviews/real-candidate-supply-contract.md`; sha256=`65ce22db33575b995c3a8337bf3d0cb7c2af3bc68bea9cdb248d3ccd0dd27385`; verdicts=`MENTION_ONLY`
- `docs/real_candidate_supply_contract.md`; sha256=`207b18e01dc66f0acf72349e521a2708eebd5f30760ffd394b839caa2c5508b8`; verdicts=`MENTION_ONLY`
- `docs/strategy_registry/03_strategy_heuristic_inventory.md`; sha256=`d038371f5a0f9fa5c6c3f4949fed11a220d1ed6b091bdd8b9f62c55d2e0d4daa`; verdicts=`MIN_FAILED_BREAK_DISTANCE_PCT`
- `tests/test_edge_65_strategy_spec_registry.py`; sha256=`d569720926b1d2095bd7b499aa74bcd3405f9cf2398b041fa8f2afeaaef4b056`; verdicts=`MENTION_ONLY`
- `tests/test_edge_66_strategy_quality_audit.py`; sha256=`55f79ad9123144902d598108224f698432615174099caad070e52ddbd60a8f07`; verdicts=`STRATEGY_QUALITY_UNSAFE_REGIME_NOT_BLOCKED`
- `tests/test_edge_67_strategy_hypothesis_contracts.py`; sha256=`89dd0e1b3a20340de003aaadff445d386628269b55742dd7114753390d5466e5`; verdicts=`MENTION_ONLY`
- `tests/test_edge_68_strategy_eligibility.py`; sha256=`72ff6f3179eae145b9129b266c04c20eac56d12217d3b0417d2624f0c0196e46`; verdicts=`ELIGIBILITY_STATUS_REJECTED`
- `tests/test_edge_69_strategy_candidate_pool.py`; sha256=`c330db5130a156aa0bcf3e8035cd4a4183ef26394af72e8ec5c5edeac80fdcda`; verdicts=`MENTION_ONLY`
- `tests/test_edge_70_candidate_normalization_dedup.py`; sha256=`86f13afe2dc4d112d0dcbf8cb3d38f54cf1363f5ad848943f418bc322d82ce79`; verdicts=`NORMALIZATION_STATUS_DUPLICATE_REJECTED`

### RSI2
- `research/option_e2e_recertification_v4/inventory/historical_claim_map_v4.json`; sha256=`505890ec246a66d94b2653e857d0cbebccccffcbd1bc12a829db46124eb85ac7`; verdicts=`MENTION_ONLY`
- `git:b1bdb86b988d35789cfbb3d4b43ca6c521b8982a`; sha256=`b1bdb86b988d35789cfbb3d4b43ca6c521b8982a`; verdicts=`GIT_HISTORY_MENTION`
- `git:a71c545911d499e8f729e285f7db4a50a388ed08`; sha256=`a71c545911d499e8f729e285f7db4a50a388ed08`; verdicts=`GIT_HISTORY_MENTION`
- `git:e2055d07f18232cac43bc1810560a487d8c34bb7`; sha256=`e2055d07f18232cac43bc1810560a487d8c34bb7`; verdicts=`GIT_HISTORY_MENTION`
- `git:f5e8f59a707bc296827694acc48260bc4c623252`; sha256=`f5e8f59a707bc296827694acc48260bc4c623252`; verdicts=`GIT_HISTORY_MENTION`
- `git:f806c02917152b5f2bac44521d14530a9d470f4b`; sha256=`f806c02917152b5f2bac44521d14530a9d470f4b`; verdicts=`GIT_HISTORY_MENTION`
- `git:98c8f13fe7e23ef8c5ec6159ea93af4beebaf47c`; sha256=`98c8f13fe7e23ef8c5ec6159ea93af4beebaf47c`; verdicts=`GIT_HISTORY_MENTION`

### ORB_RETEST_DRIVE
- `docs/BOOK_2_BUILD_AND_STRATEGY_MANUAL.md`; sha256=`24c1acd843ca132285b8cc23c0f911234feed9b05cdb33c095d62625447afe01`; verdicts=`MENTION_ONLY`
- `docs/EDGE_69_CANDIDATE_INTENT_CONTRACT.md`; sha256=`cebf8c812ee56239c473724611627a8bb4917ed4475c719b9f1f6910efae4f9d`; verdicts=`MENTION_ONLY`
- `docs/EDGE_70_CANDIDATE_INTENT_POOL_VALIDATOR.md`; sha256=`52cb8260b33bb31bd75c2ee24ae6506735d9040ee118a8e7f483b8801ed45808`; verdicts=`MENTION_ONLY`
- `docs/EDGE_72_BREAKOUT_STRATEGY_REBUILD.md`; sha256=`21db2281f0720715ce03e90e37c125b7bc13eb455ced223bf8c532d6894fa12c`; verdicts=`MENTION_ONLY`
- `docs/agent_handoffs/canonical-strategy-input-truth-repair-codex.md`; sha256=`32b7211d9efbc8cc37a11cd3d2586a4f3c6d4a0c73120cb373675eb090dc4d9f`; verdicts=`MENTION_ONLY`
- `docs/agent_handoffs/orb-candle-validation-codex.md`; sha256=`f34a4f62c3f0db9a8eeabe77d9896f2749e9ec9f9492741a91251803c3126dfe`; verdicts=`MENTION_ONLY`
- `docs/agent_reviews/458-trace-phase2-candidate-starvation-after-indicators.md`; sha256=`efac8e60c1db142dfb0048a91b1b53b4c88dc6a823c5d5f3a1c09c68a00c91b1`; verdicts=`MENTION_ONLY`
- `docs/agent_reviews/ORB_CANDLE_NEGATIVE_RESULT.md`; sha256=`bf3cafec4d28bee496836d1f75b4ad5dfbd0426b02f46246f0b035a5927204c4`; verdicts=`MENTION_ONLY`
- `docs/agent_reviews/PR-5_strategy_certification.md`; sha256=`caff8828675c1cb307c5eedd601d6244ea23e04cca6209df37c377d2103a6818`; verdicts=`MENTION_ONLY`
- `docs/agent_reviews/all_strategy_available_data_backtest_20260629.md`; sha256=`56fbc7c4b40609be3ddbcd9e288f1d671e56c84e1ff393a717141e2a3172a290`; verdicts=`MENTION_ONLY`

### VWAP_VARIANTS
- `docs/BOOK_2_BUILD_AND_STRATEGY_MANUAL.md`; sha256=`24c1acd843ca132285b8cc23c0f911234feed9b05cdb33c095d62625447afe01`; verdicts=`MENTION_ONLY`
- `docs/EDGE_71_CANDIDATE_CLASSIFICATION_LAYER.md`; sha256=`f61e1d1940fa26668b8c0b9ce22072b910a66c706de99ee385a53e05b0050c21`; verdicts=`MENTION_ONLY`
- `docs/EDGE_72_BREAKOUT_STRATEGY_REBUILD.md`; sha256=`21db2281f0720715ce03e90e37c125b7bc13eb455ced223bf8c532d6894fa12c`; verdicts=`MENTION_ONLY`
- `docs/EDGE_73_VWAP_STRATEGY_REBUILD.md`; sha256=`1109c750f93014ef6c4e1d2e4bfe90c6c95900b58b682d661484048ebe2d4edf`; verdicts=`MENTION_ONLY`
- `docs/EDGE_74_MEAN_REVERSION_STRATEGY_REBUILD.md`; sha256=`1856b50106e7c3e3c8a5c430bcfc82568f6cf26a2bf24b7559a3c0b9736a5fa0`; verdicts=`MENTION_ONLY`
- `docs/EDGE_75_ZERO_HERO_EXPIRY_STRATEGY_REBUILD.md`; sha256=`584733af943c20ed9485d17c25ad4017959fd5016d3bec611a301224d3fc227c`; verdicts=`MENTION_ONLY`
- `docs/EDGE_77_STRATEGY_SPECIFIC_EXIT_MODELS.md`; sha256=`2c11beb8173eb3154643678ccc017eec340c3f29247e1aa5613657a67c5685a5`; verdicts=`MENTION_ONLY`
- `docs/EDGE_78_STRATEGY_PARAMETER_ROBUSTNESS_TESTS.md`; sha256=`56696140847fd455eb1f378f3cb3fe9a5c857e1ab29fb4c2063e74f999a58382`; verdicts=`MENTION_ONLY`
- `docs/agent_handoffs/canonical-strategy-input-truth-antigravity.md`; sha256=`cd93b7eec7ab14cedf3ea5d2df242c55fdf286adac2f26a6fd008a3be4653ddb`; verdicts=`MENTION_ONLY`
- `docs/agent_reviews/EDGE_78_STRATEGY_PARAMETER_ROBUSTNESS_TESTS.md`; sha256=`a413d71e88d73bbf5dc3164d7a4e00b9be79f36908a4bca0d161da5840c0d13f`; verdicts=`MENTION_ONLY`

### COMPRESSION
- `docs/agent_reviews/four_strategy_contract_bundle_v1.json`; sha256=`8b7df7e030306b9699347f9b3ed1c421fd8dfc302c7902a178e8111cb177d8c2`; verdicts=`ALREADY_EMITTED`, `CANDIDATE_IDENTITY_PROVEN`, `FAIL_CLOSED`, `INVALIDATED`, `OPTIONAL_PROVENANCE_ONLY`
- `docs/agent_reviews/four_strategy_data_suitability_v2.md`; sha256=`658ae0c0caaf45981dedbdf001bfa26d6ca610644468816aab421849537907ef`; verdicts=`COMPOSITE_SIGNAL_DATA_READY_WITH_PROVENANCE_LIMITATIONS`, `FETCH_FAILED_HTTP`, `FETCH_FAILED_NO_CANDLES`, `UPSTOX_CAPTURE_AUTH_FAILED`
- `docs/agent_reviews/four_strategy_dataset_manifest_v1.json`; sha256=`ff0441fa4518e40881fdc00ed1873c61af142e7f4079e0ac343f3cab91253bf4`; verdicts=`MENTION_ONLY`
- `docs/agent_reviews/option_e2e_historical_inventory_v4.md`; sha256=`ec0ecef5ff81cdf29cbd5e87d895d117e61da1c4ab674098c73e0cca5473e270`; verdicts=`MENTION_ONLY`
- `docs/agent_reviews/tb_edge_candidate_unblock_stabilization.md`; sha256=`f522ade9aff4480df32de3ab5d54de39d104ae13ad2c0fedb6565ed83910ca88`; verdicts=`MENTION_ONLY`
- `docs/audits/profitable_edge_strategy_matrix_20260629.md`; sha256=`e41c8300e40e04be3f3216b7440cc7213de289625a0dcfdbfda2ec9df332ae8c`; verdicts=`MENTION_ONLY`
- `docs/audits/strategy_contract_and_edge_readiness_audit.md`; sha256=`0ef369853894a94aea5041f17c109cc252f667c8b22eebc61c53c8fe290eaa2c`; verdicts=`MIN_FAILED_BREAK_DISTANCE_PCT`
- `docs/research/all_strategy_option_e2e_recertification_v4.md`; sha256=`f1173f7cfaea643859ef4ed2e1885ce9bd742a91092e30f2ed9e64e97bc9eaae`; verdicts=`MENTION_ONLY`
- `docs/research/strategy_backtesting_engine_audit.md`; sha256=`d1c73242529f6857a9e3c362a45069bf35acc3983bb73fa7bf1bcd89c30c18c0`; verdicts=`BACKTEST_ENGINE_CONDITIONALLY_READY`
- `docs/strategy_module_taxonomy.md`; sha256=`02adae5d5063e5f366236220ab23677331593afeadc4f01ae1327b8cf21653f0`; verdicts=`MENTION_ONLY`

### TREND
- `docs/BOOK_2_BUILD_AND_STRATEGY_MANUAL.md`; sha256=`24c1acd843ca132285b8cc23c0f911234feed9b05cdb33c095d62625447afe01`; verdicts=`MENTION_ONLY`
- `docs/EDGE_70_CANDIDATE_NORMALIZATION_DEDUP.md`; sha256=`d10b016bbee6d3315711d7461ffa6b0d0b36ec551e1b48bf539539aeaba3bfda`; verdicts=`MENTION_ONLY`
- `docs/EDGE_71_CANDIDATE_CLASSIFICATION_LAYER.md`; sha256=`f61e1d1940fa26668b8c0b9ce22072b910a66c706de99ee385a53e05b0050c21`; verdicts=`MENTION_ONLY`
- `docs/EDGE_73_VWAP_STRATEGY_REBUILD.md`; sha256=`1109c750f93014ef6c4e1d2e4bfe90c6c95900b58b682d661484048ebe2d4edf`; verdicts=`MENTION_ONLY`
- `docs/agent_reviews/edge_73_vwap_strategy_rebuild.md`; sha256=`4b583ea7e53189809c2e885d3fc3fdf6afa80686c86411578b2ec2fdfd24ac97`; verdicts=`MENTION_ONLY`
- `docs/agent_reviews/four_strategy_contract_bundle_v1.json`; sha256=`8b7df7e030306b9699347f9b3ed1c421fd8dfc302c7902a178e8111cb177d8c2`; verdicts=`ALREADY_EMITTED`, `CANDIDATE_IDENTITY_PROVEN`, `FAIL_CLOSED`, `INVALIDATED`, `OPTIONAL_PROVENANCE_ONLY`
- `docs/agent_reviews/four_strategy_data_suitability_v2.md`; sha256=`658ae0c0caaf45981dedbdf001bfa26d6ca610644468816aab421849537907ef`; verdicts=`COMPOSITE_SIGNAL_DATA_READY_WITH_PROVENANCE_LIMITATIONS`, `FETCH_FAILED_HTTP`, `FETCH_FAILED_NO_CANDLES`, `UPSTOX_CAPTURE_AUTH_FAILED`
- `docs/agent_reviews/four_strategy_dataset_manifest_v1.json`; sha256=`ff0441fa4518e40881fdc00ed1873c61af142e7f4079e0ac343f3cab91253bf4`; verdicts=`MENTION_ONLY`
- `docs/agent_reviews/option_e2e_historical_inventory_v4.md`; sha256=`ec0ecef5ff81cdf29cbd5e87d895d117e61da1c4ab674098c73e0cca5473e270`; verdicts=`MENTION_ONLY`
- `docs/agent_reviews/strategy_replay_foundation.md`; sha256=`e59c2b317e05e22ed3bf990b11432bfb9927dd254411e1f2ab60b57b7cc45cc4`; verdicts=`STRATEGY_REPLAY_FOUNDATION_READY`

### MRE
- `docs/agent_reviews/option_e2e_historical_inventory_v4.md`; sha256=`ec0ecef5ff81cdf29cbd5e87d895d117e61da1c4ab674098c73e0cca5473e270`; verdicts=`MENTION_ONLY`
- `docs/audits/profitable_edge_strategy_matrix_20260629.md`; sha256=`e41c8300e40e04be3f3216b7440cc7213de289625a0dcfdbfda2ec9df332ae8c`; verdicts=`MENTION_ONLY`
- `docs/audits/strategy_contract_and_edge_readiness_audit.md`; sha256=`0ef369853894a94aea5041f17c109cc252f667c8b22eebc61c53c8fe290eaa2c`; verdicts=`MIN_FAILED_BREAK_DISTANCE_PCT`
- `docs/research/all_strategy_option_e2e_recertification_v4.md`; sha256=`f1173f7cfaea643859ef4ed2e1885ce9bd742a91092e30f2ed9e64e97bc9eaae`; verdicts=`MENTION_ONLY`
- `docs/research/strategy_backtesting_engine_audit.md`; sha256=`d1c73242529f6857a9e3c362a45069bf35acc3983bb73fa7bf1bcd89c30c18c0`; verdicts=`BACKTEST_ENGINE_CONDITIONALLY_READY`
- `docs/strategy_design/MEAN_REVERSION_EXTENSION_V2_DESIGN.md`; sha256=`4121be7b485c09ce1cecb50be7d63a1079c7fc8faf865bcb105aaac367c20658`; verdicts=`MENTION_ONLY`
- `docs/strategy_module_taxonomy.md`; sha256=`02adae5d5063e5f366236220ab23677331593afeadc4f01ae1327b8cf21653f0`; verdicts=`MENTION_ONLY`
- `docs/strategy_registry/03_strategy_heuristic_inventory.md`; sha256=`d038371f5a0f9fa5c6c3f4949fed11a220d1ed6b091bdd8b9f62c55d2e0d4daa`; verdicts=`MIN_FAILED_BREAK_DISTANCE_PCT`
- `docs/strategy_validation/MEAN_REVERSION_EXTENSION_V1_FAILED_BASELINE.md`; sha256=`59750a058af4a4437b09e0a1e98ae24b2b8d687bd16b9e668de78f491c831e50`; verdicts=`MRE_V1_PARAMETER_SPACE_FAILED`
- `docs/strategy_validation/MEAN_REVERSION_EXTENSION_V2_FAILED_BASELINE.md`; sha256=`6f27142cb88ba8ed6ca0b5c717c34d9753a67906b506597d408785b71097284d`; verdicts=`MRE_V2_PARAMETER_SPACE_FAILED`

### EXHAUSTION
- `docs/agent_reviews/four_strategy_data_suitability_v2.md`; sha256=`658ae0c0caaf45981dedbdf001bfa26d6ca610644468816aab421849537907ef`; verdicts=`COMPOSITE_SIGNAL_DATA_READY_WITH_PROVENANCE_LIMITATIONS`, `FETCH_FAILED_HTTP`, `FETCH_FAILED_NO_CANDLES`, `UPSTOX_CAPTURE_AUTH_FAILED`
- `docs/agent_reviews/option_e2e_historical_inventory_v4.md`; sha256=`ec0ecef5ff81cdf29cbd5e87d895d117e61da1c4ab674098c73e0cca5473e270`; verdicts=`MENTION_ONLY`
- `docs/audits/profitable_edge_strategy_matrix_20260629.md`; sha256=`e41c8300e40e04be3f3216b7440cc7213de289625a0dcfdbfda2ec9df332ae8c`; verdicts=`MENTION_ONLY`
- `docs/audits/strategy_contract_and_edge_readiness_audit.md`; sha256=`0ef369853894a94aea5041f17c109cc252f667c8b22eebc61c53c8fe290eaa2c`; verdicts=`MIN_FAILED_BREAK_DISTANCE_PCT`
- `docs/research/all_strategy_option_e2e_recertification_v4.md`; sha256=`f1173f7cfaea643859ef4ed2e1885ce9bd742a91092e30f2ed9e64e97bc9eaae`; verdicts=`MENTION_ONLY`
- `docs/research/strategy_backtesting_engine_audit.md`; sha256=`d1c73242529f6857a9e3c362a45069bf35acc3983bb73fa7bf1bcd89c30c18c0`; verdicts=`BACKTEST_ENGINE_CONDITIONALLY_READY`
- `docs/strategy_design/MEAN_REVERSION_EXTENSION_V2_DESIGN.md`; sha256=`4121be7b485c09ce1cecb50be7d63a1079c7fc8faf865bcb105aaac367c20658`; verdicts=`MENTION_ONLY`
- `docs/strategy_module_taxonomy.md`; sha256=`02adae5d5063e5f366236220ab23677331593afeadc4f01ae1327b8cf21653f0`; verdicts=`MENTION_ONLY`
- `docs/strategy_registry/03_strategy_heuristic_inventory.md`; sha256=`d038371f5a0f9fa5c6c3f4949fed11a220d1ed6b091bdd8b9f62c55d2e0d4daa`; verdicts=`MIN_FAILED_BREAK_DISTANCE_PCT`
- `docs/superpowers/specs/2026-05-06-pro-strategy-elite-design.md`; sha256=`429b3304c6b3d6cc6847c81c9c424cbb079427def8f2be6ae16b8a30b8282ac8`; verdicts=`MENTION_ONLY`

### HTF
- `docs/agent_reviews/option_e2e_historical_inventory_v4.md`; sha256=`ec0ecef5ff81cdf29cbd5e87d895d117e61da1c4ab674098c73e0cca5473e270`; verdicts=`MENTION_ONLY`
- `docs/agent_reviews/qa_full_implemented_strategy_truth_audit.md`; sha256=`789ae220b1b3574264477a23eda315d4901c3e615d11149a848c54393568ceae`; verdicts=`PIPELINE_MUTATION_FOUND`
- `docs/research/all_strategy_option_e2e_recertification_v4.md`; sha256=`f1173f7cfaea643859ef4ed2e1885ce9bd742a91092e30f2ed9e64e97bc9eaae`; verdicts=`MENTION_ONLY`
- `docs/research/htf_range_expansion_strategy_spec.md`; sha256=`9b7bde3d8053b5b624d34e889678535af2e2310f45be592c1570cc9ff6ec9f3e`; verdicts=`MENTION_ONLY`
- `docs/research/strategy_deepdive_checklist.md`; sha256=`e75f35ee03f3fb1ee95ade901f9ec590d7660a7d524315ca8c06a313d7d0997f`; verdicts=`MENTION_ONLY`
- `docs/research/strategy_research_index.md`; sha256=`c73407748683e0e917e7e72a086700014ea05ea67e0f7c26d8c5b1bb7485c723`; verdicts=`HTF_FAILED_BREAKOUT_REVERSAL`
- `docs/research/strategy_research_playbook.md`; sha256=`dbbf89263ffcee6f30fe8b53129d19f7957bca0fe0ff91a7086b4afe7c2e77c4`; verdicts=`MENTION_ONLY`
- `docs/strategy_design/MEAN_REVERSION_EXTENSION_V2_DESIGN.md`; sha256=`4121be7b485c09ce1cecb50be7d63a1079c7fc8faf865bcb105aaac367c20658`; verdicts=`MENTION_ONLY`
- `docs/strategy_research/htf_cost_sensitivity.csv`; sha256=`62446496df72b42c7f731dc0fff336926a805b2c2a494610fa10213a868cd18f`; verdicts=`MENTION_ONLY`
- `docs/strategy_research/htf_edge_retest_report.md`; sha256=`0eb577c003026835a23c826b9adbe7dcc426f977813f56fc319c2ad36272ace5`; verdicts=`HTF_FAILED_BREAKOUT_REVERSAL`

### CANDIDATE_INTENT
- `docs/EDGE_65_STRATEGY_SPEC_REGISTRY.md`; sha256=`45825801dfcbf12258c3aa48b4fb2c10ed12bf3e4ff79b23f0f62d08b831c10a`; verdicts=`MENTION_ONLY`
- `docs/EDGE_69_CANDIDATE_INTENT_CONTRACT.md`; sha256=`cebf8c812ee56239c473724611627a8bb4917ed4475c719b9f1f6910efae4f9d`; verdicts=`MENTION_ONLY`
- `docs/EDGE_70_CANDIDATE_INTENT_POOL_VALIDATOR.md`; sha256=`52cb8260b33bb31bd75c2ee24ae6506735d9040ee118a8e7f483b8801ed45808`; verdicts=`MENTION_ONLY`
- `docs/EDGE_71_STRATEGY_CANDIDATE_GENERATORS.md`; sha256=`7a56cf51d141f6e7f07f32f48fc5bf8edd0510c057f9adee301048910fcee960`; verdicts=`MENTION_ONLY`
- `docs/EDGE_72_BREAKOUT_STRATEGY_REBUILD.md`; sha256=`21db2281f0720715ce03e90e37c125b7bc13eb455ced223bf8c532d6894fa12c`; verdicts=`MENTION_ONLY`
- `docs/EDGE_73_VWAP_STRATEGY_REBUILD.md`; sha256=`1109c750f93014ef6c4e1d2e4bfe90c6c95900b58b682d661484048ebe2d4edf`; verdicts=`MENTION_ONLY`
- `docs/EDGE_74_MEAN_REVERSION_STRATEGY_REBUILD.md`; sha256=`1856b50106e7c3e3c8a5c430bcfc82568f6cf26a2bf24b7559a3c0b9736a5fa0`; verdicts=`MENTION_ONLY`
- `docs/EDGE_75_ZERO_HERO_EXPIRY_STRATEGY_REBUILD.md`; sha256=`584733af943c20ed9485d17c25ad4017959fd5016d3bec611a301224d3fc227c`; verdicts=`MENTION_ONLY`
- `docs/EDGE_77_STRATEGY_SPECIFIC_EXIT_MODELS.md`; sha256=`2c11beb8173eb3154643678ccc017eec340c3f29247e1aa5613657a67c5685a5`; verdicts=`MENTION_ONLY`
- `docs/EDGE_79_STRATEGY_CONFLICT_CONSENSUS_ENGINE.md`; sha256=`395a7f970d95265b5eaac737ef174c3353f738e6a29b9cfb537e5c8abf611b50`; verdicts=`MENTION_ONLY`

### ZERO_HERO
- `docs/EDGE_74_MEAN_REVERSION_STRATEGY_REBUILD.md`; sha256=`1856b50106e7c3e3c8a5c430bcfc82568f6cf26a2bf24b7559a3c0b9736a5fa0`; verdicts=`MENTION_ONLY`
- `docs/EDGE_75_ZERO_HERO_EXPIRY_STRATEGY_REBUILD.md`; sha256=`584733af943c20ed9485d17c25ad4017959fd5016d3bec611a301224d3fc227c`; verdicts=`MENTION_ONLY`
- `docs/EDGE_77_STRATEGY_SPECIFIC_EXIT_MODELS.md`; sha256=`2c11beb8173eb3154643678ccc017eec340c3f29247e1aa5613657a67c5685a5`; verdicts=`MENTION_ONLY`
- `docs/EDGE_78_STRATEGY_PARAMETER_ROBUSTNESS_TESTS.md`; sha256=`56696140847fd455eb1f378f3cb3fe9a5c857e1ab29fb4c2063e74f999a58382`; verdicts=`MENTION_ONLY`
- `docs/agent_reviews/EDGE_78_STRATEGY_PARAMETER_ROBUSTNESS_TESTS.md`; sha256=`a413d71e88d73bbf5dc3164d7a4e00b9be79f36908a4bca0d161da5840c0d13f`; verdicts=`MENTION_ONLY`
- `docs/agent_reviews/edge_75_zero_hero_expiry_strategy_rebuild.md`; sha256=`0a85e191f533f761ed2e273d51b44a0801fedaed36c673bcc1ae8c6c42b1aa10`; verdicts=`MENTION_ONLY`
- `docs/agent_reviews/option_e2e_historical_inventory_v4.md`; sha256=`ec0ecef5ff81cdf29cbd5e87d895d117e61da1c4ab674098c73e0cca5473e270`; verdicts=`MENTION_ONLY`
- `docs/research/all_strategy_option_e2e_recertification_v4.md`; sha256=`f1173f7cfaea643859ef4ed2e1885ce9bd742a91092e30f2ed9e64e97bc9eaae`; verdicts=`MENTION_ONLY`
- `docs/strategy_module_taxonomy.md`; sha256=`02adae5d5063e5f366236220ab23677331593afeadc4f01ae1327b8cf21653f0`; verdicts=`MENTION_ONLY`
- `docs/strategy_registry/03_strategy_heuristic_inventory.md`; sha256=`d038371f5a0f9fa5c6c3f4949fed11a220d1ed6b091bdd8b9f62c55d2e0d4daa`; verdicts=`MIN_FAILED_BREAK_DISTANCE_PCT`

### ML_DISCOVERY
- `docs/agent_reviews/ml_strategy_discovery_core_implementation.md`; sha256=`7409a4495f253e8b7aabd66332e90195071d5c9bc3595ff4151ecac3579df507`; verdicts=`ML_DISCOVERY_CORE_AND_CERTIFIED_SOURCE_ADAPTER`
- `docs/agent_reviews/ml_strategy_discovery_real_run_audit_v1.md`; sha256=`8fef28cb5133be722b71544d66f665cf7aa0ce65016646b1fc2eef2435b559bf`; verdicts=`NO_STRUCTURAL_EDGE_OR_OPTION_PROFITABILITY_PROVEN`
- `docs/research/ml_strategy_discovery_repository_inventory.md`; sha256=`37aa8c6b60788d65e2454158d83b5d8f17a8eb85035879a63019cfa6ad647b55`; verdicts=`MENTION_ONLY`
- `research/ml_strategy_discovery/README.md`; sha256=`5e2ff4267e55f46f4cf7eb01cf2cb619d8fe7e304d67798122cf6289cfbadaa7`; verdicts=`MENTION_ONLY`
- `research/ml_strategy_discovery/__init__.py`; sha256=`838f811d6489bed1c7d245d6dfd1e4c57ca49fb73dd4a6056d80beb5944befff`; verdicts=`MENTION_ONLY`
- `research/ml_strategy_discovery/audit.py`; sha256=`c6c13b7f79dbae2f8faaaef53661f5d77af2f73e07faed9f84c63a71af5fb9d7`; verdicts=`MENTION_ONLY`
- `research/ml_strategy_discovery/contracts.py`; sha256=`7e1c71cdb0ac9d4ecb0abbd8e19a46c3188fb89e92a0a0f0463e3e411415bd90`; verdicts=`MENTION_ONLY`
- `research/ml_strategy_discovery/dataset.py`; sha256=`fe6f2bec2b372991ebefb84cf283c7f65814c82ed88ee72072b5abda82338353`; verdicts=`MENTION_ONLY`
- `research/ml_strategy_discovery/evaluation.py`; sha256=`de0a57eb6b2248ecb85812b7f5a2fc8aae7a0f4be3babd7218109893634ec40d`; verdicts=`MENTION_ONLY`
- `research/ml_strategy_discovery/features.py`; sha256=`ce328e64b0517531c12adf01f3b493790b1458c09780c706c1e0a6475258cc5c`; verdicts=`MENTION_ONLY`

### GOVERNED_FIVE_MINUTE_DISCOVERY
- `/Users/madhuram/tradebot-kite-five-minute-governed-discovery-v1`; sha256=`a8fa0cf218df4b4b7a575ff36f344774ba1fff9d`; verdicts=`WORKTREE_MENTION`

## Durable Verdict Labels

- `ADAPTER_BLOCKED_STRESS_REPLAY_DATA_MISSING`: 1 evidence path(s) retained in JSON sample
- `ALREADY_EMITTED`: 2 evidence path(s) retained in JSON sample
- `AUDIT_COMMAND_FAILED`: 1 evidence path(s) retained in JSON sample
- `BACKTEST_ENGINE_CONDITIONALLY_READY`: 1 evidence path(s) retained in JSON sample
- `BLOCKED_NO_CANDIDATE_EVENT_FOUND`: 2 evidence path(s) retained in JSON sample
- `BLOCKED_RANKING_REJECTED`: 4 evidence path(s) retained in JSON sample
- `CANDIDATE_GENERATOR_CONTRACT_FAILED`: 1 evidence path(s) retained in JSON sample
- `CANDIDATE_IDENTITY_PROVEN`: 2 evidence path(s) retained in JSON sample
- `CANDIDATE_INTENT_POOL_REJECTED_INTENTS_PRESENT`: 1 evidence path(s) retained in JSON sample
- `CANDIDATE_INTENT_POOL_STATUS_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `CANDIDATE_PROVENANCE_HASH_MISMATCH`: 1 evidence path(s) retained in JSON sample
- `CANDIDATE_PROVENANCE_INCOMPLETE`: 1 evidence path(s) retained in JSON sample
- `CANDIDATE_READY`: 2 evidence path(s) retained in JSON sample
- `CANDIDATE_REPLAY_DATA_BLOCKED`: 4 evidence path(s) retained in JSON sample
- `CANDIDATE_REPLAY_FAILED`: 3 evidence path(s) retained in JSON sample
- `CANONICAL_STRATEGY_CONTRACT_VERIFIED`: 3 evidence path(s) retained in JSON sample
- `CAPACITY_ACCOUNTING_INVARIANT_FAILED`: 2 evidence path(s) retained in JSON sample
- `CAUSAL_SIGNAL_VERIFIED`: 1 evidence path(s) retained in JSON sample
- `CERTIFICATION_FAILED`: 1 evidence path(s) retained in JSON sample
- `COMPOSITE_EXECUTION_DATA_READY`: 1 evidence path(s) retained in JSON sample
- `COMPOSITE_SIGNAL_DATA_READY`: 1 evidence path(s) retained in JSON sample
- `COMPOSITE_SIGNAL_DATA_READY_WITH_PROVENANCE_LIMITATIONS`: 3 evidence path(s) retained in JSON sample
- `CONSENSUS_STATUS_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `CONSENSUS_STATUS_READY`: 1 evidence path(s) retained in JSON sample
- `DATA_BLOCKED_`: 1 evidence path(s) retained in JSON sample
- `DATA_BLOCKED_OPTION_OHLC_NO_SPREAD_TRUTH`: 4 evidence path(s) retained in JSON sample
- `DATA_BLOCKED_REAL_OPTION_LTP_MISSING`: 2 evidence path(s) retained in JSON sample
- `DATA_BLOCKED_STRESS_REPLAY_UNSUPPORTED_BY_DATA_CAPABILITY`: 3 evidence path(s) retained in JSON sample
- `DATA_BLOCKED_UNDERLYING_ONLY_NO_OPTION_TRUTH`: 4 evidence path(s) retained in JSON sample
- `DATA_BLOCKED_UNSUPPORTED_PROVIDER`: 1 evidence path(s) retained in JSON sample
- `DATA_BLOCKED_UPSTOX_FETCH_FAILED`: 2 evidence path(s) retained in JSON sample
- `DATA_BLOCKED_UPSTOX_NO_TICK_OR_SPREAD_TRUTH`: 2 evidence path(s) retained in JSON sample
- `DATA_BLOCKED_UPSTOX_TOKEN_MISSING`: 2 evidence path(s) retained in JSON sample
- `DATA_BLOCKED_UPSTOX_UNAVAILABLE`: 2 evidence path(s) retained in JSON sample
- `DEBUG_REJECTED`: 1 evidence path(s) retained in JSON sample
- `DECLARED_BUT_NOT_FOUND`: 2 evidence path(s) retained in JSON sample
- `DEFERRED_UNTIL_CHILD_STRATEGIES_CERTIFIED`: 1 evidence path(s) retained in JSON sample
- `DIRECTION_MAPPING_VERIFIED`: 1 evidence path(s) retained in JSON sample
- `DOWNGRADE_DECISION_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `DOWNGRADE_DECISION_CANDIDATE_READY`: 1 evidence path(s) retained in JSON sample
- `ELIGIBILITY_STATUS_REJECTED`: 1 evidence path(s) retained in JSON sample
- `EXECUTION_BLOCKED_STATUS`: 1 evidence path(s) retained in JSON sample
- `EXECUTION_DATA_BLOCKED`: 2 evidence path(s) retained in JSON sample
- `EXIT_MODEL_OPTION_CONFIRMATION_NOT_READY`: 1 evidence path(s) retained in JSON sample
- `FAIL_CLOSED`: 2 evidence path(s) retained in JSON sample
- `FEED_TRUTH_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `FETCH_FAILED_HTTP`: 2 evidence path(s) retained in JSON sample
- `FETCH_FAILED_NO_CANDLES`: 2 evidence path(s) retained in JSON sample
- `FROZEN_HYPOTHESIS_VERIFIED`: 2 evidence path(s) retained in JSON sample
- `FULLY_PROVEN_FROM_PERSISTED_RUNTIME_ARTIFACTS`: 2 evidence path(s) retained in JSON sample
- `FULLY_PROVEN_FROM_REPLAY_INPUT`: 1 evidence path(s) retained in JSON sample
- `G15_EVIDENCE_AUDIT_FAILED`: 1 evidence path(s) retained in JSON sample
- `HISTORICAL_DATA_CAPABILITY_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `HOLDOUT_AUDIT_FAILED`: 1 evidence path(s) retained in JSON sample
- `HTF_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `HTF_FAILED_BREAKOUT_REVERSAL`: 10 evidence path(s) retained in JSON sample
- `HYGIENE_STATUS_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `HYPOTHETICAL_REJECTED_CANDIDATE`: 1 evidence path(s) retained in JSON sample
- `IMPLEMENTATION_BUG_FOUND`: 5 evidence path(s) retained in JSON sample
- `IMPLEMENTATION_NOT_VERIFIED`: 2 evidence path(s) retained in JSON sample
- `IMPLEMENTATION_VERIFIED`: 8 evidence path(s) retained in JSON sample
- `IMPLEMENTATION_VERIFIED_NEEDS_EDGE_RETEST`: 3 evidence path(s) retained in JSON sample
- `INPUT_CANDIDATE_LEDGER_PROVENANCE_HASH`: 1 evidence path(s) retained in JSON sample
- `INVALIDATED`: 2 evidence path(s) retained in JSON sample
- `LEDGER_COMMAND_FAILED`: 1 evidence path(s) retained in JSON sample
- `MARKET_CLOSED_NO_TRADE`: 1 evidence path(s) retained in JSON sample
- `MEAN_REVERSION_FAILURE_ATTRIBUTION_BLOCKED_LEDGER_MISSING`: 2 evidence path(s) retained in JSON sample
- `MEAN_REVERSION_FAILURE_ATTRIBUTION_STRATEGY_EDGE_NOT_FOUND`: 1 evidence path(s) retained in JSON sample
- `MEAN_REVERSION_HISTORICAL_CATALOG_BLOCKED`: 2 evidence path(s) retained in JSON sample
- `MEAN_REVERSION_HISTORICAL_CATALOG_READY`: 1 evidence path(s) retained in JSON sample
- `MIN_FAILED_BREAK_DISTANCE_PCT`: 2 evidence path(s) retained in JSON sample
- `ML_DISCOVERY_CORE_AND_CERTIFIED_SOURCE_ADAPTER`: 1 evidence path(s) retained in JSON sample
- `MRE_V1_OVERFIT_REGION_FAILED`: 2 evidence path(s) retained in JSON sample
- `MRE_V1_PARAMETER_SPACE_FAILED`: 3 evidence path(s) retained in JSON sample
- `MRE_V2_PARAMETER_SPACE_FAILED`: 1 evidence path(s) retained in JSON sample
- `NEXT_OPEN_COST_HURDLE_FAILED`: 1 evidence path(s) retained in JSON sample
- `NORMALIZATION_STATUS_DUPLICATE_REJECTED`: 1 evidence path(s) retained in JSON sample
- `NOT_CERTIFIED`: 1 evidence path(s) retained in JSON sample
- `NOT_CURRENTLY_PROVEN`: 1 evidence path(s) retained in JSON sample
- `NOT_PHASE6_READY`: 2 evidence path(s) retained in JSON sample
- `NOT_PROVEN`: 1 evidence path(s) retained in JSON sample
- `NOT_PROVEN_CURRENT_ENGINE_IS_FIXED_SYMBOL_CANDLE_ROW_DRIVEN`: 1 evidence path(s) retained in JSON sample
- `NOT_PROVEN_CURRENT_FIXED_SYMBOL_ENGINE_ONLY`: 1 evidence path(s) retained in JSON sample
- `NOT_PROVEN_GENERIC_COST_CONFIG_STILL_IN_USE`: 1 evidence path(s) retained in JSON sample
- `NO_EDGE_FOUND`: 1 evidence path(s) retained in JSON sample
- `NO_HISTORICAL_SETUPS_FOUND_IN_WINDOW`: 1 evidence path(s) retained in JSON sample
- `NO_STRUCTURAL_EDGE_OR_OPTION_PROFITABILITY_PROVEN`: 2 evidence path(s) retained in JSON sample
- `NO_VALID_SOURCE_FOUND`: 1 evidence path(s) retained in JSON sample
- `OPENING_DRIVE_OVERFIT_REGION_FAILED`: 1 evidence path(s) retained in JSON sample
- `OPENING_DRIVE_PARAMETER_SPACE_FAILED`: 1 evidence path(s) retained in JSON sample
- `OPENING_DRIVE_SELECTIVITY_NOT_PROVEN`: 1 evidence path(s) retained in JSON sample
- `OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY`: 1 evidence path(s) retained in JSON sample
- `OPTIONAL_PROVENANCE_ONLY`: 1 evidence path(s) retained in JSON sample
- `ORB_PHASE1_V2_CANDIDATE_LEDGER_CERTIFIED`: 2 evidence path(s) retained in JSON sample
- `ORB_PHASE1_V2_CANDIDATE_LEDGER_NOT_CERTIFIED`: 1 evidence path(s) retained in JSON sample
- `PAPER_EXPECTANCY_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `PAPER_SLIPPAGE_COST_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `PARTIALLY_PROVEN_FROM_EXISTING_RUNTIME_HANDOFF`: 1 evidence path(s) retained in JSON sample
- `PARTIALLY_VERIFIED`: 2 evidence path(s) retained in JSON sample
- `PENDING_SIGNAL_INVALIDATED_BY_ACTIVE_TRADE`: 1 evidence path(s) retained in JSON sample
- `PERF_STATUS_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `PHASE6_SHADOW_CANDIDATES_READY`: 1 evidence path(s) retained in JSON sample
- `PHASE6_SHADOW_CANDIDATE_READY`: 1 evidence path(s) retained in JSON sample
- `PHASE_6_DATA_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `PHASE_6_FAILED_VIOLATION`: 2 evidence path(s) retained in JSON sample
- `PHASE_6_SCAFFOLD_READY`: 1 evidence path(s) retained in JSON sample
- `PIPELINE_MUTATION_FOUND`: 4 evidence path(s) retained in JSON sample
- `POINT_IN_TIME_UNIVERSE_VERIFIED`: 1 evidence path(s) retained in JSON sample
- `POSITION_ALREADY_OPEN`: 1 evidence path(s) retained in JSON sample
- `PROMOTION_DECISION_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `READINESS_STATE_BLOCKED`: 2 evidence path(s) retained in JSON sample
- `READINESS_STATE_READY`: 2 evidence path(s) retained in JSON sample
- `RECOVERY_BLOCKED`: 3 evidence path(s) retained in JSON sample
- `REGISTRY_STAGE_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `RESEARCH_STAGE_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `RETIRE_CANDIDATE_RULE_READY_REASON`: 1 evidence path(s) retained in JSON sample
- `RULE_REPRODUCTION_FAILED`: 2 evidence path(s) retained in JSON sample
- `S3_JOIN_PROVENANCE_SESSION_MISMATCH`: 1 evidence path(s) retained in JSON sample
- `S3_JOIN_PROVENANCE_SYMBOL_MISMATCH`: 1 evidence path(s) retained in JSON sample
- `S4_FUTURE_MUTATION_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `S4_READYNESS_MALFORMED_TIMESTAMP`: 1 evidence path(s) retained in JSON sample
- `S4_READYNESS_OUTSIDE_SESSION`: 1 evidence path(s) retained in JSON sample
- `SIMPLE_ORB_PHASE_EVIDENCE_FOUND_PARTIAL`: 2 evidence path(s) retained in JSON sample
- `SOURCE_PROVENANCE_INVALID`: 2 evidence path(s) retained in JSON sample
- `SOURCE_PROVENANCE_MISMATCH`: 1 evidence path(s) retained in JSON sample
- `SOURCE_VALIDATION_FAILED`: 1 evidence path(s) retained in JSON sample
- `STALE_CANDIDATE_HYGIENE_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `STALE_DOCUMENTED_RESULT_WITHOUT_REPRODUCIBLE_PROVENANCE`: 2 evidence path(s) retained in JSON sample
- `STALE_OPTION_LTP_PROVENANCE`: 1 evidence path(s) retained in JSON sample
- `STRATEGY_EXIT_MODEL_STATUS_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `STRATEGY_EXIT_MODEL_STATUS_READY`: 1 evidence path(s) retained in JSON sample
- `STRATEGY_FAMILY_REPORT_BLOCKED`: 3 evidence path(s) retained in JSON sample
- `STRATEGY_LIFECYCLE_BLOCKED`: 3 evidence path(s) retained in JSON sample
- `STRATEGY_PERF_SHADOW_FALLBACK_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `STRATEGY_PROMOTION_GATE_BLOCKED`: 2 evidence path(s) retained in JSON sample
- `STRATEGY_QUALITY_UNSAFE_REGIME_NOT_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `STRATEGY_REPLAY_FOUNDATION_READY`: 1 evidence path(s) retained in JSON sample
- `STRATEGY_REPLAY_PROOF_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `STRATEGY_SUSPENSION_RETIREMENT_BLOCKED`: 2 evidence path(s) retained in JSON sample
- `SUBSCRIPTION_FAILED`: 3 evidence path(s) retained in JSON sample
- `SUITABLE_WITH_PROVENANCE_LIMITATIONS`: 2 evidence path(s) retained in JSON sample
- `SUPERVISOR_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `SUSPEND_CANDIDATE_RULE_READY_REASON`: 1 evidence path(s) retained in JSON sample
- `TB_RANKED_COUNT_BLOCKED`: 1 evidence path(s) retained in JSON sample
- `TB_TOP_BLOCKED_CANDIDATE`: 4 evidence path(s) retained in JSON sample
- `TRADE_LEDGER_AUDIT_FAILED`: 2 evidence path(s) retained in JSON sample
- `TRUTH_STAGE_BLOCKED`: 2 evidence path(s) retained in JSON sample
- `UPSTOX_CANDIDATE_REPLAY_DATA_PREFLIGHT_BLOCKED`: 2 evidence path(s) retained in JSON sample
- `UPSTOX_CANDIDATE_REPLAY_DATA_PREFLIGHT_READY`: 1 evidence path(s) retained in JSON sample
- `UPSTOX_CAPTURE_AUTH_FAILED`: 1 evidence path(s) retained in JSON sample
- `UPSTOX_FETCH_FAILED_HTTP_ERROR`: 1 evidence path(s) retained in JSON sample
- `UPSTOX_FETCH_FAILED_NO_CANDLES`: 1 evidence path(s) retained in JSON sample
- `VALIDATION_FAILED`: 1 evidence path(s) retained in JSON sample
- `WFA_NOT_EVALUATED_BECAUSE_PHASE4_BLOCKED`: 1 evidence path(s) retained in JSON sample

## PR Metadata

- gh_available: `True`
- pr: `710` `All-strategy NIFTY option E2E recertification v4`
- url: https://github.com/ramgolladi1503-sys/tradebot/pull/710
- commits_seen: `7`
- files_seen: `42`

## Commands

```bash
python -m research.option_e2e_recertification_v4.inventory_v4_1.build_inventory_v4_1
pytest -q tests/research/option_e2e/test_inventory_v4_1.py
git status --short --branch
```

## Claim Boundary

This proves only an offline, hash-addressed historical inventory repair. It does not prove profitability, paper readiness, live readiness, option PnL correctness, broker execution readiness, or Phase 2 integration.

## Agent Work Contract

source_agent: Subagent A1. action: historical inventory repair. scope: research-only inventory builder, generated inventory artifacts, focused tests, and this review doc. forbidden_paths: broker, order, live, risk, feed, strategy threshold, credential and production execution paths.

## Scope Guard

This inventory counts and classifies strategy and strategy-adjacent entities only. It does not run replay, change strategy code, or certify economics.

## Grill Me Review

The v4.1 count supersedes the earlier over-broad 29-entry framing by excluding helpers, fixtures, adapters, registries and aggregate/deferred entities from counted strategies.

## Hermes Review

The inventory model separates canonical strategy entities, non-strategy support, aggregate/registry entities, and historical research family evidence.

## GSD Review

The implementation is isolated to `inventory_v4_1` and focused tests, with generated hashes for reproducibility.

## QA / Safety Review

Safety fields are explicit: `is_order_action=false` and `broker_api_called=false`. No broker, live feed, order, risk, runtime or strategy threshold changes were made.

## Acceptance Proof

`python -m research.option_e2e_recertification_v4.inventory_v4_1.build_inventory_v4_1` regenerated the artifacts and `pytest -q tests/research/option_e2e/test_inventory_v4_1.py` passed with four focused tests.

## Runtime Proof Required After Merge

No runtime proof is required because this is offline inventory evidence only. Any runtime usage requires separate approved wiring.

## What This PR Does Not Prove

This does not prove profitability, option PnL correctness, paper readiness, live readiness, historical contract authority, or Phase 2 integration.

## Human Approval

Human approval is required before using this inventory to alter runtime strategy selection, risk policy, broker routing, or paper/live eligibility.
