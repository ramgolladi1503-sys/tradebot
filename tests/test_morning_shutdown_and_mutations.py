from core.morning_shutdown import ShutdownContract, ShutdownState
from scripts.morning_mutation_campaign import run


def test_complete_shutdown_seals():
    result = ShutdownContract().request().quiesce(post_quiesce_enqueue_count=0).drain(queues_zero=True, unfinished_tasks_zero=True, workers_joined=True, locks_released=True, row_reconciliation_pass=True).seal()
    assert result.state is ShutdownState.SEALED


def test_enqueue_after_quiesce_fails_closed():
    result = ShutdownContract().request().quiesce(post_quiesce_enqueue_count=1)
    assert result.state is ShutdownState.FAILED


def test_mutation_campaign_passes():
    result = run()
    assert result["mutations_detected"] >= 8
    assert result["mutations_total"] == 18
