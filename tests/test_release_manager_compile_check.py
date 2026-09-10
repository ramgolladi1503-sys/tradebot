import subprocess

from scripts.release_manager_compile_check import compile_check


def test_compile_check_reports_materialized_checkout(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "ok.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "ok.py"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "-m", "ok"],
        check=True,
    )

    result = compile_check(repo)

    assert result["whole_tree_compile_pass"] is True
    assert result["tracked_python_file_count"] == 1
    assert result["materialized_compile_file_count"] == 1
    assert result["compile_failure_count"] == 0


def test_compile_check_blocks_syntax_error(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "bad.py").write_text("def bad(:\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "bad.py"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "-m", "bad"],
        check=True,
    )

    result = compile_check(repo)

    assert result["whole_tree_compile_pass"] is False
    assert result["compile_failure_count"] == 1
    assert result["failures"][0]["path"] == "bad.py"
