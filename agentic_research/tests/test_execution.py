import pytest

from agentic_research.contracts import ToolResult
from agentic_research.execution import IdempotentToolExecutor, TraceRecorder
from agentic_research.storage import ArtifactStore


def test_executor_reuses_completed_result(tmp_path):
    count = {"calls": 0}
    executor = IdempotentToolExecutor(tmp_path / "state.sqlite", TraceRecorder(ArtifactStore(tmp_path / "runs")))

    def operation():
        count["calls"] += 1
        return ToolResult(tool="x", status="SUCCESS", payload={"value": 1}).with_hash()

    first = executor.execute(research_id="r1", tool_name="x", arguments={"a": 1}, operation=operation)
    second = executor.execute(research_id="r1", tool_name="x", arguments={"a": 1}, operation=operation)
    assert first == second
    assert count["calls"] == 1
    assert executor.attempts("r1", "x") == 1


def test_failed_operation_can_retry(tmp_path):
    count = {"calls": 0}
    executor = IdempotentToolExecutor(tmp_path / "state.sqlite", TraceRecorder(ArtifactStore(tmp_path / "runs")))

    def operation():
        count["calls"] += 1
        if count["calls"] == 1:
            raise RuntimeError("transient")
        return ToolResult(tool="x", status="SUCCESS").with_hash()

    with pytest.raises(RuntimeError, match="transient"):
        executor.execute(research_id="r1", tool_name="x", arguments={}, operation=operation)
    result = executor.execute(research_id="r1", tool_name="x", arguments={}, operation=operation)
    assert result.status == "SUCCESS"
    assert count["calls"] == 2
    assert executor.attempts("r1", "x") == 2
