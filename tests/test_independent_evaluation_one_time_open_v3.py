from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_independent_underlying_evaluation_v3 import immutable_run_id, write_open_record


def test_second_open_rejected_for_different_run(tmp_path, monkeypatch):
    import scripts.run_independent_underlying_evaluation_v3 as runner

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    write_open_record("first", allow_resume=False)
    with pytest.raises(RuntimeError):
        write_open_record("second", allow_resume=False)


def test_same_run_resume_allowed(tmp_path, monkeypatch):
    import scripts.run_independent_underlying_evaluation_v3 as runner

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    write_open_record("first", allow_resume=False)
    write_open_record("first", allow_resume=True)
    assert json.loads((Path(tmp_path) / "epoch_open_record.json").read_text())["run_id"] == "first"


def test_run_id_is_derived_from_frozen_inputs():
    assert immutable_run_id() == immutable_run_id()

