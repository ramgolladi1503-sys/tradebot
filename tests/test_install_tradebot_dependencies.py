from __future__ import annotations

from pathlib import Path

import pytest

from scripts import install_tradebot_dependencies as installer


def test_base_requirements_reject_direct_broker_dependencies(tmp_path: Path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "pytest\nKiteConnect==5.2.0\nautobahn[twisted]>=25.10.2\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="forbidden entries: kiteconnect@2, autobahn@3"):
        installer.validate_base_requirements(requirements)


def test_repository_base_requirements_use_verified_installer_boundary():
    requirements = Path(__file__).resolve().parents[1] / "requirements.txt"
    installer.validate_base_requirements(requirements)


def test_installer_runs_fail_closed_dependency_sequence(monkeypatch, tmp_path: Path):
    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "build_secure_kiteconnect_wheel.py").write_text("# fixture\n", encoding="utf-8")
    requirements = repo_root / "requirements.txt"
    requirements.write_text("pytest\n", encoding="utf-8")
    download_cache = repo_root / ".runtime" / "downloads"
    wheel_dir = repo_root / ".runtime" / "wheels"
    wheel_dir.mkdir(parents=True)
    (wheel_dir / installer.PATCHED_WHEEL_NAME).write_bytes(b"fixture")

    commands: list[list[str]] = []

    def fake_run(args, *, cwd):
        assert cwd == repo_root
        commands.append([str(part) for part in args])

    expected = {
        "kiteconnect_version": installer.EXPECTED_KITECONNECT_VERSION,
        "autobahn_version": "25.10.2",
        "patch_provenance": {"fixture": True},
    }
    monkeypatch.setattr(installer, "_run", fake_run)
    monkeypatch.setattr(installer, "verify_installed_broker_sdk", lambda: expected)

    result = installer.install(
        repo_root=repo_root,
        requirements=requirements,
        download_cache=download_cache,
        wheel_dir=wheel_dir,
        skip_base=False,
    )

    assert result == expected
    assert commands[0][-4:] == ["uninstall", "-y", "kiteconnect", "autobahn"]
    assert commands[1][-3:] == ["install", "-r", str(requirements)]
    assert commands[2][1].endswith("scripts/build_secure_kiteconnect_wheel.py")
    assert commands[3][-2:] == ["--force-reinstall", str(wheel_dir / installer.PATCHED_WHEEL_NAME)]
    assert commands[4][-2:] == ["pip", "check"]


def test_skip_base_still_replaces_and_verifies_broker_graph(monkeypatch, tmp_path: Path):
    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "build_secure_kiteconnect_wheel.py").write_text("# fixture\n", encoding="utf-8")
    requirements = repo_root / "requirements.txt"
    requirements.write_text("pytest\n", encoding="utf-8")
    wheel_dir = repo_root / "wheels"
    wheel_dir.mkdir()
    (wheel_dir / installer.PATCHED_WHEEL_NAME).write_bytes(b"fixture")

    commands: list[list[str]] = []
    monkeypatch.setattr(
        installer,
        "_run",
        lambda args, *, cwd: commands.append([str(part) for part in args]),
    )
    monkeypatch.setattr(installer, "verify_installed_broker_sdk", lambda: {"status": "verified"})

    result = installer.install(
        repo_root=repo_root,
        requirements=requirements,
        download_cache=repo_root / "downloads",
        wheel_dir=wheel_dir,
        skip_base=True,
    )

    assert result == {"status": "verified"}
    assert not any("-r" in command for command in commands)
    assert commands[0][-4:] == ["uninstall", "-y", "kiteconnect", "autobahn"]
    assert commands[-1][-2:] == ["pip", "check"]
