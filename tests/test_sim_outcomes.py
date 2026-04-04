from core.sim_outcomes import summarize_sim_outcome


def test_sim_outcome_tracks_mfe_and_mae():
    summary = summarize_sim_outcome(
        entry_price=100.0,
        side="BUY",
        future_prices=[101.0, 104.0, 98.0, 103.0],
        quantity=1,
    )

    assert summary.mfe == 4.0
    assert summary.mae == -2.0


def test_rejected_trade_can_be_marked_as_saved_loss():
    summary = summarize_sim_outcome(
        entry_price=100.0,
        side="BUY",
        future_prices=[99.0, 96.0, 95.0],
        rejected=True,
    )

    assert summary.rejection_saved_loss is True
    assert summary.rejection_missed_win is False


def test_rejected_trade_can_be_marked_as_missed_win():
    summary = summarize_sim_outcome(
        entry_price=100.0,
        side="BUY",
        future_prices=[101.0, 104.0, 107.0],
        rejected=True,
    )

    assert summary.rejection_saved_loss is False
    assert summary.rejection_missed_win is True


def test_simulated_exit_reason_is_preserved():
    summary = summarize_sim_outcome(
        entry_price=100.0,
        side="BUY",
        future_prices=[101.0, 106.0, 109.0],
        target=105.0,
    )

    assert summary.exit_reason == "TARGET_HIT"
    assert summary.would_have_worked is True
