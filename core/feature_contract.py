from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Mapping, Sequence, Tuple

import pandas as pd


@dataclass
class FeatureContract:
    required_features: List[str] = field(default_factory=list)
    allow_extra_features: bool = True

    @classmethod
    def from_model_metadata(
        cls,
        model_features: Sequence[str] | None = None,
        fallback_features: Sequence[str] | None = None,
    ) -> "FeatureContract":
        required = list(model_features or fallback_features or [])
        return cls(required_features=required)

    def validate(self, features) -> Tuple[bool, str]:
        if features is None:
            return False, "MODEL_FEATURE_MISMATCH:missing=ALL"

        row, columns = self._normalize(features)
        if not self.required_features:
            return True, "ok"

        missing = [name for name in self.required_features if name not in columns]
        if missing:
            return False, f"MODEL_FEATURE_MISMATCH:missing={','.join(missing)}"

        if not self.allow_extra_features:
            extra = sorted([name for name in columns if name not in self.required_features])
            if extra:
                return False, f"MODEL_FEATURE_MISMATCH:extra={','.join(extra)}"

        for feature_name in self.required_features:
            value = row.get(feature_name)
            if pd.isna(value):
                return False, f"FEATURE_NAN_PRESENT:{feature_name}"

        return True, "ok"

    def _normalize(self, features) -> Tuple[Mapping[str, object], List[str]]:
        if isinstance(features, pd.DataFrame):
            if features.empty:
                return {}, list(features.columns)
            row = features.iloc[0].to_dict()
            return row, list(features.columns)
        if isinstance(features, pd.Series):
            return features.to_dict(), list(features.index)
        if isinstance(features, Mapping):
            return dict(features), list(features.keys())
        if isinstance(features, Iterable):
            data = dict(features)
            return data, list(data.keys())
        return {}, []
