import json

from scripts.release_manager import _gate_result


def test_gate_result_accepts_evidence_backed_gate(tmp_path):
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")
    import hashlib

    gates = tmp_path / "gates.json"
    gates.write_text(
        json.dumps(
            {
                "gates": {
                    "source_identity": {
                        "pass": True,
                        "evidence_path": str(evidence),
                        "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert _gate_result(gates) == {"source_identity": True}


def test_gate_result_rejects_evidence_hash_mismatch(tmp_path):
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")
    gates = tmp_path / "gates.json"
    gates.write_text(
        json.dumps(
            {
                "gates": {
                    "source_identity": {
                        "pass": True,
                        "evidence_path": str(evidence),
                        "evidence_sha256": "0" * 64,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert _gate_result(gates) == {"source_identity": False}
