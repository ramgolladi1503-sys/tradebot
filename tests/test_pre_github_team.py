import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import subprocess
import sys

from tools.pre_github_team import ROLES, run_team, _load_work_item, _validate_response

ITEM = {"work_item_id": "TB-1", "title": "Example", "business_goal": "Find issues",
        "acceptance_criteria": ["Output verifiable result"], "allowed_paths": ["docs/**"],
        "forbidden_paths": ["core/broker/**"]}


class TeamTests(unittest.TestCase):
    def test_eight_separate_invocations(self):
        calls = []
        def fake(role, prompt, root, timeout):
            calls.append((role, prompt))
            return {"verdict": "PASS", "summary": "reviewed", "evidence_refs": ["docs/a.md"], "findings": []}, {"provider": "fake", "exit_code": 0}
        report = run_team(ITEM, "sha", Path("."), runner=fake)
        self.assertEqual(len(report["roles"]), 8)
        self.assertEqual([r["role"] for r in report["roles"]], list(ROLES))
        self.assertEqual(len({r["invocation_id"] for r in report["roles"]}), 8)
        self.assertEqual(report["team_status"], "REVIEWS_COLLECTED_UNVERIFIED")
        self.assertIn("No code was changed", report["limitations"])
        self.assertNotIn("git push", str(calls))

    def test_block_stops_dependent_roles(self):
        calls = []
        def fake(role, prompt, root, timeout):
            calls.append(role)
            return {"verdict": "BLOCK" if role == "GRILL_ME" else "PASS", "summary": "reviewed", "evidence_refs": ["docs/a.md"], "findings": []}, {}
        report = run_team(ITEM, "sha", Path("."), runner=fake)
        self.assertEqual(calls, ["BUSINESS_ANALYST", "PRODUCT_OWNER", "GRILL_ME"])
        self.assertEqual(report["team_status"], "UNSATISFIED")

    def test_fake_pass_without_evidence_rejected(self):
        def fake(role, prompt, root, timeout):
            return {"verdict": "PASS", "summary": "all good", "evidence_refs": [], "findings": []}, {}
        report = run_team(ITEM, "sha", Path("."), runner=fake)
        self.assertEqual(len(report["roles"]), 1)
        self.assertEqual(report["roles"][0]["verdict"], "UNSATISFIED")

    def test_na_needs_reason(self):
        with self.assertRaises(ValueError):
            _validate_response({"verdict": "NOT_APPLICABLE", "summary": "skip", "evidence_refs": [], "findings": []})

    def test_committed_file_required(self):
        with TemporaryDirectory() as root:
            path = Path(root)
            subprocess.run(["git", "init", "-q", str(path)], check=True)
            target = path / "governance/evidence/work_items/TB-1.json"
            target.parent.mkdir(parents=True)
            import json
            target.write_text(json.dumps(ITEM), encoding="utf-8")
            with self.assertRaises(ValueError):
                _load_work_item(path, "governance/evidence/work_items/TB-1.json")
            subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(path), "-c", "user.name=Test", "-c", "user.email=t@example.invalid", "commit", "-qm", "fixture"], check=True)
            data, sha = _load_work_item(path, "governance/evidence/work_items/TB-1.json")
            self.assertEqual(data["work_item_id"], "TB-1")
            target.write_text(json.dumps({**ITEM, "title": "altered"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                _load_work_item(path, "governance/evidence/work_items/TB-1.json")


if __name__ == "__main__":
    unittest.main()
