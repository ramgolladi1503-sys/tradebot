from __future__ import annotations

import json

from core.ai_certification import (
    EvidenceCertification,
    StrategyVerdict,
    certify_bundle,
)


def test_qa_source_001_required_control_source_role_cannot_be_omitted(
    qa_bundle_factory,
    qa_rehash_manifest,
):
    bundle = qa_bundle_factory()
    index_path = bundle / "source_index.json"
    source_index = json.loads(index_path.read_text(encoding="utf-8"))
    source_index["copied_files"] = [
        row
        for row in source_index["copied_files"]
        if row.get("role") != "controls_input"
    ]
    index_path.write_text(json.dumps(source_index, sort_keys=True), encoding="utf-8")
    qa_rehash_manifest(bundle)

    report = certify_bundle(bundle)

    assert report.evidence_certification is EvidenceCertification.REJECTED
    assert report.strategy_verdict is StrategyVerdict.INVALID_DUE_TO_DATA
    assert (
        report.to_dict()["gates"]["source_artifact_provenance"]["reason_code"]
        == "SOURCE_ROLE_MISSING:controls_input"
    )


def test_qa_source_002_raw_and_normalized_controls_must_match(
    qa_bundle_factory,
):
    bundle = qa_bundle_factory(
        artifact_overrides={
            "source/negative_controls_input.json": {
                "controls": {"timing_shift": False}
            }
        }
    )

    report = certify_bundle(bundle)

    assert report.evidence_certification is EvidenceCertification.REJECTED
    assert report.strategy_verdict is StrategyVerdict.INVALID_DUE_TO_DATA
    assert (
        report.to_dict()["gates"]["source_artifact_provenance"]["reason_code"]
        == "SOURCE_CONTROLS_MISMATCH"
    )
