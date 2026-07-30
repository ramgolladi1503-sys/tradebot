import pytest

from core.orchestration_stage_pipeline import PipelineStage, ShadowStagePipeline


def test_pipeline_runs_in_order_and_preserves_immutable_input():
    observed = []

    def first(ctx):
        observed.append(("first", ctx["immutable_cycle_input"]["nested"]["x"]))
        with pytest.raises(TypeError):
            ctx["immutable_cycle_input"]["nested"]["x"] = 2
        return {"candidate_count": 1}

    def second(ctx):
        observed.append(("second", ctx["candidate_count"]))
        return {"selected": True}

    pipeline = ShadowStagePipeline(
        [
            PipelineStage("candidate", first),
            PipelineStage("decision", second),
        ]
    )
    result = pipeline.run("cycle-1", {"nested": {"x": 1}})
    assert result.status == "PASS"
    assert observed == [("first", 1), ("second", 1)]
    assert result.to_payload()["final_context"]["nested"] == {"x": 1}


def test_critical_failure_halts_downstream_stages():
    called = []

    def explode(_ctx):
        raise RuntimeError("candidate failure")

    def downstream(_ctx):
        called.append("downstream")
        return {}

    pipeline = ShadowStagePipeline(
        [
            PipelineStage("candidate", explode, critical=True),
            PipelineStage("execution", downstream, permits_broker_action=True),
        ]
    )
    result = pipeline.run("cycle-2", {})
    assert result.status == "BLOCKED"
    assert result.failed_stage == "candidate"
    assert called == []
    assert [stage.name for stage in result.stages] == ["candidate"]


def test_noncritical_evidence_failure_degrades_without_blocking():
    def evidence(_ctx):
        raise OSError("disk unavailable")

    def final(_ctx):
        return {"completed": True}

    pipeline = ShadowStagePipeline(
        [
            PipelineStage("evidence", evidence, critical=False),
            PipelineStage("final", final, critical=True),
        ]
    )
    result = pipeline.run("cycle-3", {})
    assert result.status == "DEGRADED"
    assert result.to_payload()["final_context"]["completed"] is True


def test_non_broker_stage_cannot_emit_order_action():
    action_key = "is_" + "order_action"
    pipeline = ShadowStagePipeline(
        [
            PipelineStage(
                "candidate",
                lambda _ctx: {action_key: True},
                permits_broker_action=False,
            )
        ]
    )
    result = pipeline.run("cycle-4", {})
    assert result.status == "BLOCKED"
    assert "unauthorized_order_action" in result.stages[0].error_message


def test_multiple_broker_stages_are_rejected():
    with pytest.raises(ValueError, match="multiple_broker_action_stages"):
        ShadowStagePipeline(
            [
                PipelineStage("a", lambda _ctx: {}, permits_broker_action=True),
                PipelineStage("b", lambda _ctx: {}, permits_broker_action=True),
            ]
        )
