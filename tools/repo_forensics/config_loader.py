from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when repo-forensics config is missing or invalid."""


@dataclass(frozen=True)
class ForensicsConfig:
    path: Path
    data: dict[str, Any]

    @property
    def required_entrypoints(self) -> list[str]:
        return _as_str_list(self.data.get("entrypoints", {}).get("required", []))

    @property
    def optional_entrypoints(self) -> list[str]:
        return _as_str_list(self.data.get("entrypoints", {}).get("optional", []))

    @property
    def critical_modules(self) -> dict[str, list[str]]:
        raw = self.data.get("critical_modules", {})
        if not isinstance(raw, dict):
            raise ConfigError("critical_modules must be a mapping")
        return {str(group): _as_str_list(items) for group, items in raw.items()}

    @property
    def excluded_directories(self) -> set[str]:
        return set(_as_str_list(self.data.get("exclude", {}).get("directories", [])))

    @property
    def excluded_file_patterns(self) -> set[str]:
        return set(_as_str_list(self.data.get("exclude", {}).get("file_patterns", [])))

    @property
    def runtime_evidence_paths(self) -> list[str]:
        """Configured paths that may contain evidence/report artifacts.

        Repo-forensics code must not hardcode project runtime paths. The profile
        owns those paths so scanners stay generic and policy-driven.
        """

        configured = []
        agent_params = self.data.get("agent_parameters", {})
        if isinstance(agent_params, dict):
            evidence_auditor = agent_params.get("evidence_auditor", {})
            if isinstance(evidence_auditor, dict):
                configured.extend(_as_str_list(evidence_auditor.get("evidence_paths", [])))
        evidence = self.data.get("evidence", {})
        if isinstance(evidence, dict):
            for key in ("report_output_dir", "agent_review_dir"):
                value = evidence.get(key)
                if isinstance(value, str) and value.strip():
                    configured.append(value.strip())
        deduped: list[str] = []
        for path in configured:
            normalized = str(path).strip().lstrip("./")
            if normalized and normalized not in deduped:
                deduped.append(normalized)
        return deduped


def load_config(path: str | Path) -> ForensicsConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"config_not_found path={config_path}")
    data = parse_simple_yaml(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError("config_root_must_be_mapping")
    _validate_config(data)
    return ForensicsConfig(path=config_path, data=data)


def _validate_config(data: dict[str, Any]) -> None:
    required_top = ["project", "baseline_rules", "entrypoints", "critical_modules"]
    missing = [key for key in required_top if key not in data]
    if missing:
        raise ConfigError(f"missing_required_config_keys keys={','.join(missing)}")
    entrypoints = data.get("entrypoints")
    if not isinstance(entrypoints, dict):
        raise ConfigError("entrypoints_must_be_mapping")
    if not _as_str_list(entrypoints.get("required", [])):
        raise ConfigError("entrypoints.required_must_not_be_empty")
    critical = data.get("critical_modules")
    if not isinstance(critical, dict) or not critical:
        raise ConfigError("critical_modules_must_not_be_empty_mapping")


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    raise ConfigError(f"expected_list value_type={type(value).__name__}")


def parse_simple_yaml(text: str) -> Any:
    """Parse the strict YAML subset used by `.gsd-forensics.yaml`.

    This intentionally avoids a PyYAML dependency because the project does not
    currently require it. Supported subset:
    - indentation-based mappings
    - lists using `- item`
    - scalar strings, booleans, integers, floats, and null

    It is not intended to be a general YAML parser.
    """

    raw_lines = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        raw_lines.append(line)
    if not raw_lines:
        return {}
    parsed, index = _parse_block(raw_lines, 0, _indent_of(raw_lines[0]))
    if index != len(raw_lines):
        raise ConfigError(f"unparsed_config_lines start_index={index}")
    return parsed


def _parse_block(lines: list[str], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    current = lines[index]
    current_indent = _indent_of(current)
    if current_indent < indent:
        return {}, index
    if current.lstrip().startswith("- "):
        return _parse_list(lines, index, current_indent)
    return _parse_mapping(lines, index, current_indent)


def _parse_mapping(lines: list[str], index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        line = lines[index]
        line_indent = _indent_of(line)
        if line_indent < indent:
            break
        if line_indent > indent:
            raise ConfigError(f"unexpected_nested_mapping_line line={index + 1}")
        stripped = line.strip()
        if stripped.startswith("- "):
            break
        if ":" not in stripped:
            raise ConfigError(f"invalid_mapping_line line={index + 1}")
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if not key:
            raise ConfigError(f"empty_mapping_key line={index + 1}")
        if raw_value:
            result[key] = _parse_scalar(raw_value)
            index += 1
            continue
        index += 1
        if index >= len(lines) or _indent_of(lines[index]) <= line_indent:
            result[key] = {}
            continue
        value, index = _parse_block(lines, index, _indent_of(lines[index]))
        result[key] = value
    return result, index


def _parse_list(lines: list[str], index: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        line = lines[index]
        line_indent = _indent_of(line)
        if line_indent < indent:
            break
        if line_indent > indent:
            raise ConfigError(f"unexpected_nested_list_line line={index + 1}")
        stripped = line.strip()
        if not stripped.startswith("- "):
            break
        item = stripped[2:].strip()
        index += 1
        if item:
            result.append(_parse_scalar(item))
            continue
        if index >= len(lines) or _indent_of(lines[index]) <= line_indent:
            result.append(None)
            continue
        value, index = _parse_block(lines, index, _indent_of(lines[index]))
        result.append(value)
    return result, index


def _parse_scalar(value: str) -> Any:
    text = value.strip()
    if _is_quoted(text):
        return text[1:-1]
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none", "~"}:
        return None
    try:
        if "." not in text and "e" not in lowered:
            return int(text)
        return float(text)
    except ValueError:
        return text


def _is_quoted(text: str) -> bool:
    return len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))
