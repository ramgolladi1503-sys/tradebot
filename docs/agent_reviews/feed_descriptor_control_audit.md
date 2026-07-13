# Feed descriptor control audit

This note summarizes the clean 10k A/B control for the latest-main feed descriptor diagnosis worktree.

Current HEAD:

`0758ce72dc46f763e63e78df3e724774466bc359`

Dirty files at note time:

- `core/feed_robustness_evidence.py`
- `core/kite_depth_ws.py`
- `scripts/run_feed_robustness_replay.py`
- `tests/test_feed_robustness_replay_runner.py`
- `tests/test_kite_depth_ws_stability.py`
- `docs/agent_reviews/feed_descriptor_control_audit.md`

Git diff checksum:

`df50ed420dbf52ccaec9adbf626fa33cc9e1c421e0429beaf971d85a20cb2e4f`

Artifact paths:

- `.runtime/feed_robustness_audit/main-sync-10k-normal-baseline-v6`
- `.runtime/feed_robustness_audit/main-sync-10k-normal-traced-v6`

Artifact file checksums:

- Baseline `checksums.json`: `a8205a100c8a416870f908cd84bf59625134d161a43e2ce23750493baa6686a2`
- Traced `checksums.json`: `5334214d0bbacc20dffe9b5a63eb3585b050321f248111dcaa1261e0e2c8e897`
- Baseline `feed_verdict.json`: `b699df99876be8a9755847cccce3a08975b56308222d09cba89513b49a7f6e5d`
- Traced `feed_verdict.json`: `b699df99876be8a9755847cccce3a08975b56308222d09cba89513b49a7f6e5d`
- Baseline `run_manifest.json`: `bd4016afeb2c53bd44469b609b3b0e2962e7bf81eb4f91fbe3dca3979bf4d7a6`
- Traced `run_manifest.json`: `d29b2df46bf764a94d4e9cdcd27a72efc0cfeae2f6026e8207597b413e3281d2`

Deterministic hashes:

- `input_source_order_sha256`: `0e9b838554106bb5d5ce9fba0a2eafafd6e7abcaff84da1c01a5424f27149a77`
- `callback_order_sha256`: `0e9b838554106bb5d5ce9fba0a2eafafd6e7abcaff84da1c01a5424f27149a77`
- `normalization_order_sha256`: `0e9b838554106bb5d5ce9fba0a2eafafd6e7abcaff84da1c01a5424f27149a77`
- `persistence_order_sha256`: `0e9b838554106bb5d5ce9fba0a2eafafd6e7abcaff84da1c01a5424f27149a77`
- `canonical_semantic_output_sha256`: `8e4e94bb76ea84a179cc7765c211bcab06bf599bf9fd5e028de6466a9b1accd1`
- `final_per_token_state_sha256`: `ce8313a1e8fd96c9b33c05fd53ccbacfefa6fe7cc9e0a86cb391cb1305d49073`

Reconciliation:

- `decoded = normalized + rejected`: pass
- `normalized = published + explicitly_dropped`: pass
- `published = persisted + pending_at_shutdown`: pass
- first semantic difference: `null`
- timestamp fidelity: pass

Runtime comparison:

- baseline replay duration: `10.596904750000249` sec
- traced replay duration: `39.83776233300159` sec
- runtime ratio: `3.76x`

Descriptor evidence in traced run:

- `baseline_fd`: `8`
- `high_water_fd`: `83`
- `callback_exit_fd_min`: `17`
- `callback_exit_fd_max`: `72`
- `callback_exit_fd_count`: `99`
- `post_replay_shutdown_fd`: `8`
- `post_worker_shutdown_fd`: `null`
- `final_fd`: `8`
- `exit_code`: `0`
- `hard_failures`: `[]`
- `worker_started`: `0`
- `worker_failures`: `0`
- `worker_terminated`: `null`
- `queue_depth_at_shutdown`: `null`
- `pending_writes_at_shutdown`: `0`

Classification:

- clean 10k control: `CONTROL_PASS_BOUNDED_BURST`
- earlier interrupted run: `CONTROL_INCONCLUSIVE`
- traced feed performance numbers: not valid for feed performance inference
