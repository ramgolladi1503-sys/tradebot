import pytest

from core.frozen_global_context_v1 import (
    FROZEN_GLOBAL_CONTEXT_V1_SHA256,
    FROZEN_GLOBAL_CONTEXT_V1_VERSION,
    binding_from_metadata,
)


FEATURES = ("prior_close", "global_context_score", "prediction_cutoff_ist")


def metadata(**overrides):
    value = {
        "model_sha256": FROZEN_GLOBAL_CONTEXT_V1_SHA256,
        "model_version": FROZEN_GLOBAL_CONTEXT_V1_VERSION,
        "feature_names": list(FEATURES),
        "refit": False,
    }
    value.update(overrides)
    return value


def test_frozen_binding_accepts_exact_immutable_contract():
    binding_from_metadata(metadata()).validate(expected_features=FEATURES)


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"model_sha256": "0" * 64}, "FROZEN_MODEL_SHA256_MISMATCH"),
        ({"model_version": "GLOBAL_CONTEXT_V2"}, "FROZEN_MODEL_VERSION_MISMATCH"),
        ({"refit": True}, "FROZEN_MODEL_REFIT_FORBIDDEN"),
        ({"feature_names": ["prior_close", "future_close", "prediction_cutoff_ist"]}, "FROZEN_MODEL_FEATURE_DRIFT"),
    ],
)
def test_frozen_binding_rejects_mutation_or_refit(overrides, error):
    with pytest.raises(ValueError, match=error):
        binding_from_metadata(metadata(**overrides)).validate(expected_features=FEATURES)


def test_frozen_binding_rejects_missing_metadata_instead_of_defaulting():
    with pytest.raises(ValueError, match="FROZEN_MODEL_FEATURES_REQUIRED"):
        binding_from_metadata({"model_sha256": FROZEN_GLOBAL_CONTEXT_V1_SHA256})
