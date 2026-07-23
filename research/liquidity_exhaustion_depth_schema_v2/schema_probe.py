from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd


JSON_PREFIXES = ("{", "[")


def normalize_depth_value(value: Any) -> Any:
    """Convert parquet/Arrow/numpy depth values into deterministic Python objects."""
    if hasattr(value, "as_py") and callable(value.as_py):
        value = value.as_py()
    if isinstance(value, np.generic):
        value = value.item()
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(JSON_PREFIXES):
            try:
                return normalize_depth_value(json.loads(stripped))
            except json.JSONDecodeError:
                return stripped
        return stripped
    if isinstance(value, Mapping):
        return {
            str(key): normalize_depth_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, np.ndarray):
        return [normalize_depth_value(item) for item in value.tolist()]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [normalize_depth_value(item) for item in value]
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (bool, int, float)):
        return value
    return str(value)


def scalar_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Mapping):
        return "mapping"
    if isinstance(value, list):
        return "sequence"
    return type(value).__name__


def shape_signature(value: Any, *, max_depth: int = 6) -> str:
    normalized = normalize_depth_value(value)

    def walk(item: Any, depth: int) -> str:
        if depth >= max_depth:
            return scalar_type_name(item)
        if isinstance(item, Mapping):
            parts = [f"{key}:{walk(child, depth + 1)}" for key, child in item.items()]
            return "map{" + ",".join(parts) + "}"
        if isinstance(item, list):
            signatures: list[str] = []
            for child in item[:5]:
                signature = walk(child, depth + 1)
                if signature not in signatures:
                    signatures.append(signature)
            return "seq[" + "|".join(signatures) + "]"
        return scalar_type_name(item)

    return walk(normalized, 0)


def collect_path_types(value: Any, *, max_depth: int = 8) -> Counter[str]:
    normalized = normalize_depth_value(value)
    counts: Counter[str] = Counter()

    def walk(item: Any, path: str, depth: int) -> None:
        kind = scalar_type_name(item)
        counts[f"{path}|{kind}"] += 1
        if depth >= max_depth:
            return
        if isinstance(item, Mapping):
            for key, child in item.items():
                walk(child, f"{path}.{key}", depth + 1)
        elif isinstance(item, list):
            for child in item[:10]:
                walk(child, f"{path}[]", depth + 1)

    walk(normalized, "$", 0)
    return counts


def bounded_preview(value: Any, *, depth: int = 0) -> Any:
    normalized = normalize_depth_value(value)
    if depth >= 5:
        return f"<{scalar_type_name(normalized)}>"
    if isinstance(normalized, Mapping):
        return {
            key: bounded_preview(child, depth=depth + 1)
            for key, child in list(normalized.items())[:12]
        }
    if isinstance(normalized, list):
        return [bounded_preview(child, depth=depth + 1) for child in normalized[:5]]
    if isinstance(normalized, float):
        if np.isnan(normalized) or np.isinf(normalized):
            return str(normalized)
    return normalized


def deterministic_sample_positions(length: int, *, limit: int = 256) -> list[int]:
    if length <= 0:
        return []
    count = min(int(limit), int(length))
    return sorted({int(position) for position in np.linspace(0, length - 1, count)})


def inspect_depth_series(series: pd.Series, *, sample_limit: int = 256) -> dict[str, Any]:
    non_null = series[series.notna()]
    positions = deterministic_sample_positions(len(non_null), limit=sample_limit)
    sampled_values = [non_null.iloc[position] for position in positions]

    root_types: Counter[str] = Counter()
    signatures: Counter[str] = Counter()
    path_types: Counter[str] = Counter()
    previews: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()

    for raw in sampled_values:
        normalized = normalize_depth_value(raw)
        root_types[scalar_type_name(normalized)] += 1
        signature = shape_signature(normalized)
        signatures[signature] += 1
        path_types.update(collect_path_types(normalized))
        if signature not in seen_signatures and len(previews) < 6:
            previews.append({"signature": signature, "value": bounded_preview(normalized)})
            seen_signatures.add(signature)

    dominant_signature = None
    if signatures:
        dominant_signature = sorted(signatures.items(), key=lambda item: (-item[1], item[0]))[0][0]

    key_tokens = sorted(
        {
            path.split("|")[0].split(".")[-1].replace("[]", "")
            for path in path_types
            if "." in path
        }
    )
    price_like_keys = sorted(
        key
        for key in key_tokens
        if any(token in key.lower() for token in ("price", "bidp", "askp", "ltp"))
    )
    size_like_keys = sorted(
        key
        for key in key_tokens
        if any(token in key.lower() for token in ("qty", "quantity", "size", "bidq", "askq"))
    )

    return {
        "row_count": int(len(series)),
        "non_null_count": int(len(non_null)),
        "sample_count": int(len(sampled_values)),
        "sample_positions": positions,
        "root_type_counts": dict(sorted(root_types.items())),
        "signature_counts": dict(sorted(signatures.items())),
        "dominant_signature": dominant_signature,
        "path_type_counts": dict(sorted(path_types.items())),
        "discovered_keys": key_tokens,
        "price_like_keys": price_like_keys,
        "size_like_keys": size_like_keys,
        "bounded_examples": previews,
    }
