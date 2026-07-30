from pathlib import Path

from scripts.audit_runtime_shims import audit_sitecustomize, build_report


def test_detects_install_hooks_and_attribute_replacement(tmp_path):
    sitecustomize = tmp_path / "sitecustomize.py"
    sitecustomize.write_text(
        """
import pandas as _pd
from core import ci_compat_contracts as _ci

_ci.install()
_pd.date_range = object()
""",
        encoding="utf-8",
    )

    patches = audit_sitecustomize(sitecustomize)

    assert len(patches) == 2
    assert {patch.mechanism for patch in patches} == {
        "install_hook",
        "attribute_replacement",
    }
    assert {patch.owner for patch in patches} == {
        "core.ci_compat_contracts",
        "pandas",
    }


def test_clean_sitecustomize_is_certification_ready(tmp_path):
    sitecustomize = tmp_path / "sitecustomize.py"
    sitecustomize.write_text(
        "\"\"\"No automatic behavior patches.\"\"\"\n",
        encoding="utf-8",
    )

    report = build_report(sitecustomize)

    assert report["active_patch_count"] == 0
    assert report["active_patch_owners"] == []
    assert report["certification_ready"] is True


def test_multiple_hooks_from_same_owner_remain_individually_traceable(tmp_path):
    sitecustomize = tmp_path / "sitecustomize.py"
    sitecustomize.write_text(
        """
from core import contract_a as _a

_a.install()
_a.install()
""",
        encoding="utf-8",
    )

    report = build_report(sitecustomize)

    assert report["active_patch_count"] == 2
    assert report["active_patch_owners"] == ["core.contract_a"]
    assert report["certification_ready"] is False
