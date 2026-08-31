from core.kite_read_only_observation_runtime import run_observation


def test_observation_source_contains_pipeline_identity_preservation():
    source = __import__("inspect").getsource(run_observation)
    assert 'pipeline_sha=str(launch_plan.get("pipeline_sha") or producer_commit)' in source
    assert 'include_instrument_authority=False' in source
