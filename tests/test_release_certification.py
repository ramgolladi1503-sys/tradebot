from core.certified_release_store import ReleaseStore, ReleaseStoreError
from core.release_certification import certify, promote
from core.release_change_impact import DependencyEvidence


def evidence_graph():
    return DependencyEvidence(edges={}, critical_roots=frozenset(), bounded_roots=frozenset(), complete=True)


def test_candidate_requires_initialized_certified_release(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    import subprocess
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    assert certify(repo, "a" * 40, ReleaseStore(tmp_path / "state"), evidence_graph())["verdict"] == "BLOCKED"


def test_failed_certification_retains_prior_release(tmp_path):
    import subprocess
    repo = tmp_path / "repo"; repo.mkdir(); subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "x.py").write_text("x=1\n"); subprocess.run(["git", "-C", str(repo), "add", "x.py"], check=True); subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "-m", "x"], check=True)
    base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    (repo / "x.py").write_text("x=2\n"); subprocess.run(["git", "-C", str(repo), "add", "x.py"], check=True); subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "-m", "y"], check=True)
    candidate = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    store = ReleaseStore(tmp_path / "state")
    first = store.record_verified_selection(candidate_sha=base, evidence_sha256="e" * 64, expected_event=None)
    result = certify(repo, candidate, store, evidence_graph(), gate_runner=lambda _: False)
    assert result["verdict"] == "FAIL" and store.read()["certified_live_sha"] == base


def test_promotion_requires_pass(tmp_path):
    store = ReleaseStore(tmp_path / "state")
    store.record_verified_selection(candidate_sha="a" * 40, evidence_sha256="e" * 64, expected_event=None)
    try:
        promote({"verdict": "FAIL", "candidate_sha": "b" * 40}, store, b"evidence")
    except ReleaseStoreError as exc:
        assert str(exc) == "promotion_requires_certified_candidate"
    else:
        raise AssertionError("unsafe promotion accepted")


def test_promotion_requires_all_gates_passed_and_matching_base(tmp_path):
    store = ReleaseStore(tmp_path / "state")
    current = store.record_verified_selection(candidate_sha="a" * 40, evidence_sha256="e" * 64, expected_event=None)
    result = {
        "verdict": "PASS",
        "candidate_sha": "b" * 40,
        "base_sha": current["certified_live_sha"],
        "fallback_sha": current["certified_live_sha"],
        "required_gates": ["source_identity", "release_verifier"],
        "passed_gates": ["source_identity"],
        "failed_gates": [],
    }
    try:
        promote(result, store, b"evidence")
    except ReleaseStoreError as exc:
        assert str(exc) == "promotion_requires_all_gates_passed"
    else:
        raise AssertionError("partial gate certification promoted")
    assert store.read()["certified_live_sha"] == "a" * 40


def test_promotion_requires_fallback_to_current_certified_release(tmp_path):
    store = ReleaseStore(tmp_path / "state")
    current = store.record_verified_selection(candidate_sha="a" * 40, evidence_sha256="e" * 64, expected_event=None)
    result = {
        "verdict": "PASS",
        "candidate_sha": "b" * 40,
        "base_sha": current["certified_live_sha"],
        "fallback_sha": "c" * 40,
        "required_gates": ["source_identity"],
        "passed_gates": ["source_identity"],
        "failed_gates": [],
    }
    try:
        promote(result, store, b"evidence")
    except ReleaseStoreError as exc:
        assert str(exc) == "promotion_fallback_mismatch"
    else:
        raise AssertionError("invalid fallback promoted")
    assert store.read()["certified_live_sha"] == "a" * 40


def test_certification_blocks_dirty_candidate_tree(tmp_path):
    import subprocess
    repo = tmp_path / "repo"; repo.mkdir(); subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "x.py").write_text("x=1\n"); subprocess.run(["git", "-C", str(repo), "add", "x.py"], check=True); subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "-m", "x"], check=True)
    base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    (repo / "x.py").write_text("x=2\n"); subprocess.run(["git", "-C", str(repo), "add", "x.py"], check=True); subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "-m", "y"], check=True)
    candidate = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    (repo / "untracked.txt").write_text("dirty\n")
    store = ReleaseStore(tmp_path / "state")
    store.record_verified_selection(candidate_sha=base, evidence_sha256="e" * 64, expected_event=None)

    result = certify(repo, candidate, store, evidence_graph(), gate_runner=lambda _: True)

    assert result["verdict"] == "BLOCKED"
    assert result["blocker"] == "candidate_tree_dirty"
