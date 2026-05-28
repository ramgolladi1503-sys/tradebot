from __future__ import annotations

from tools.code_excellence.daedalus import PRLoopInput, detect_pr_loop_risk


def test_claimed_blocker_fix_without_test_or_evidence_changes_is_blocked():
    report = detect_pr_loop_risk(
        PRLoopInput(
            changed_files=("tools/code_excellence/daedalus/pr_loop_detector.py",),
            claims_fix_blocker=True,
            blocker_count_before=1,
            blocker_count_after=1,
            done_means=("detector added",),
            acceptance_proof=(),
        )
    )

    assert report.verdict == "BLOCK"
    assert "code_change_without_tests" in report.blockers
    assert "blocker_not_reduced" in report.blockers
    assert "acceptance_proof_absent" in report.blockers


def test_explicit_documentation_only_pr_can_pass():
    report = detect_pr_loop_risk(
        PRLoopInput(
            changed_files=("docs/agent_reviews/AGENT_ELITE_12_DAEDALUS_ANTI_LOOP.md",),
            claims_fix_blocker=False,
            documentation_scoped=True,
            done_means=("documentation scope recorded",),
            acceptance_proof=("doc-only acceptance proof",),
        )
    )

    assert report.verdict == "PASS"
    assert report.allowed is True
    assert report.documentation_only is True
    assert report.blockers == ()
    assert report.risks == ("documentation_only_explicit",)


def test_follow_up_work_without_current_scope_reduction_blocks_code_pr():
    report = detect_pr_loop_risk(
        PRLoopInput(
            changed_files=("tools/code_excellence/daedalus/pr_loop_detector.py", "tests/test_daedalus_pr_loop_detector.py"),
            claims_fix_blocker=True,
            blocker_count_before=3,
            blocker_count_after=3,
            done_means=("report exists",),
            acceptance_proof=("unit tests cover behavior",),
            next_steps=("follow up with many PRs later",),
        )
    )

    assert report.verdict == "BLOCK"
    assert "blocker_not_reduced" in report.blockers
    assert "follow_up_without_current_scope_reduction" in report.blockers
    assert "vague_next_steps" in report.warnings
    assert "broad_follow_up_chain" in report.warnings


def test_follow_up_work_warns_when_not_claiming_blocker_fix():
    report = detect_pr_loop_risk(
        PRLoopInput(
            changed_files=("docs/notes.md",),
            claims_fix_blocker=False,
            documentation_scoped=True,
            done_means=("note captured",),
            acceptance_proof=("note reviewed",),
            next_steps=("future review",),
        )
    )

    assert report.verdict == "WARN"
    assert report.blockers == ()
    assert "vague_next_steps" in report.warnings
    assert "follow_up_without_current_scope_reduction" in report.warnings


def test_pr_with_done_means_and_proof_passes():
    report = detect_pr_loop_risk(
        PRLoopInput(
            changed_files=("tools/code_excellence/daedalus/pr_loop_detector.py", "tests/test_daedalus_pr_loop_detector.py"),
            claims_fix_blocker=True,
            blocker_count_before=2,
            blocker_count_after=1,
            done_means=("risk report exists",),
            acceptance_proof=("tests prove loop risk detection",),
            current_scope_reduced=True,
        )
    )

    assert report.verdict == "PASS"
    assert report.allowed is True
    assert report.blocker_reduced is True
    assert report.blockers == ()
    assert report.warnings == ()
