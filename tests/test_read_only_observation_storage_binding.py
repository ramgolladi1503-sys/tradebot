import os
from types import SimpleNamespace

from core import kite_read_only_observation_runtime as observation_runtime


def test_storage_environment_is_bound_before_depth_store_import(monkeypatch, tmp_path):
    observed = {}
    configured = {}
    monkeypatch.setattr(observation_runtime.os, "environ", dict(os.environ))
    stale_storage_root = tmp_path / "stale-runtime.sqlite"
    observation_runtime.os.environ["TRADE_DB_PATH"] = str(stale_storage_root)
    fake_depth_store = SimpleNamespace(
        depth_store=SimpleNamespace(
            configure_rejection_provenance=lambda path, *, session_id, producer_sha: configured.update(
                path=path, session_id=session_id, producer_sha=producer_sha
            )
        )
    )
    def import_hook(name):
        if name == "core.depth_store":
            observed["storage_root"] = os.environ.get("TRADE_DB_PATH")
            return fake_depth_store

    monkeypatch.setattr(observation_runtime.importlib, "import_module", import_hook)
    output_root = tmp_path / "observation"
    returned = observation_runtime._bind_storage_environment_and_depth_store(
        env={"TRADE_DB_PATH": str(tmp_path / "runtime.sqlite")},
        output_root=output_root,
        launch_plan={"run_id": "fixture-run", "commit_sha": "a" * 40},
    )

    assert returned is fake_depth_store
    assert observed["storage_root"] == str(tmp_path / "runtime.sqlite")
    assert observed["storage_root"] != str(stale_storage_root)
    assert configured == {
        "path": output_root / "depth_rejections.jsonl",
        "session_id": "fixture-run",
        "producer_sha": "a" * 40,
    }
