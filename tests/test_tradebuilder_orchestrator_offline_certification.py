from scripts.evaluate_tradebuilder_orchestrator_offline_certification import evaluate


def test_only_live_validation_remains_when_all_offline_gates_pass() -> None:
    architecture = {
        "verdict": {
            "corpus_present": True,
            "helper_parity": True,
            "shadow_parity": True,
            "ranking_execution_authority_proven": True,
        }
    }
    ticks = {
        "verdict": {
            "market_input_replay_usable": True,
            "candidate_lifecycle_present": False,
            "execution_authority_present": False,
            "scope": "market_input_reconstruction_only",
        }
    }

    report = evaluate(architecture, ticks)

    assert report["offline_complete"] is True
    assert report["live_validation_pending"] is True
    assert report["verdict"] == "OFFLINE_VALIDATION_COMPLETE_LIVE_ONLY_PENDING"
    assert report["live_validation_requirements"]


def test_missing_candidate_corpus_keeps_offline_validation_open() -> None:
    architecture = {
        "verdict": {
            "corpus_present": False,
            "helper_parity": False,
            "shadow_parity": False,
            "ranking_execution_authority_proven": True,
        }
    }
    ticks = {
        "verdict": {
            "market_input_replay_usable": True,
            "candidate_lifecycle_present": False,
            "execution_authority_present": False,
            "scope": "market_input_reconstruction_only",
        }
    }

    report = evaluate(architecture, ticks)

    assert report["offline_complete"] is False
    assert report["live_validation_pending"] is False
    assert report["verdict"] == "OFFLINE_VALIDATION_INCOMPLETE"
    assert report["gates"]["candidate_corpus_present"] is False


def test_raw_ticks_cannot_be_claimed_as_candidate_lifecycle() -> None:
    architecture = {
        "verdict": {
            "corpus_present": True,
            "helper_parity": True,
            "shadow_parity": True,
            "ranking_execution_authority_proven": True,
        }
    }
    ticks = {
        "verdict": {
            "market_input_replay_usable": True,
            "candidate_lifecycle_present": True,
            "execution_authority_present": False,
            "scope": "market_input_reconstruction_only",
        }
    }

    report = evaluate(architecture, ticks)

    assert report["offline_complete"] is False
    assert report["gates"]["raw_tick_data_not_misrepresented_as_lifecycle"] is False
