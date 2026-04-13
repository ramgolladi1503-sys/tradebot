from core.playbook_selector import select_playbook


def test_select_playbook_prefers_profile_rejection_in_range():
    playbook = select_playbook(
        {
            "regime": "RANGE",
            "profile_rejection_detected": True,
            "breakout_detected": True,
            "profile_rejection_setup_score": 0.65,
            "breakout_setup_score": 0.75,
        }
    )
    assert playbook == "profile_rejection"


def test_select_playbook_prefers_breakout_in_trend():
    playbook = select_playbook(
        {
            "regime": "TREND",
            "profile_rejection_detected": True,
            "breakout_detected": True,
            "profile_rejection_setup_score": 0.75,
            "breakout_setup_score": 0.65,
        }
    )
    assert playbook == "breakout_continuation"


def test_select_playbook_returns_none_when_no_setup_detected():
    playbook = select_playbook(
        {
            "regime": "TREND",
            "profile_rejection_detected": False,
            "breakout_detected": False,
        }
    )
    assert playbook == "none"

