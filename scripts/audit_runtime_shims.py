from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePatch:
    path: str
    line: int
    owner: str
    mechanism: str
    description: str


def _qualified_name(node: ast.AST) -> str:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def audit_sitecustomize(path: Path) -> list[RuntimePatch]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    aliases: dict[str, str] = {}
    patches: list[RuntimePatch] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = str(node.module or "")
            for alias in node.names:
                local = alias.asname or alias.name
                owner = f"{module}.{alias.name}" if module else alias.name
                aliases[local] = owner
        elif isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "install" and isinstance(node.func.value, ast.Name):
                local = node.func.value.id
                owner = aliases.get(local, local)
                patches.append(
                    RuntimePatch(
                        path=str(path),
                        line=node.lineno,
                        owner=owner,
                        mechanism="install_hook",
                        description=f"Automatic `{owner}.install()` call from sitecustomize.",
                    )
                )
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                name = _qualified_name(target)
                if name:
                    root = name.split(".", 1)[0]
                    owner = aliases.get(root, root)
                    if "." in name and (
                        owner.startswith("pandas")
                        or owner.startswith("core.")
                    ):
                        patches.append(
                            RuntimePatch(
                                path=str(path),
                                line=node.lineno,
                                owner=owner,
                                mechanism="attribute_replacement",
                                description=f"Automatic attribute replacement: `{name}`.",
                            )
                        )

    unique: dict[tuple[str, int, str, str], RuntimePatch] = {}
    for patch in patches:
        key = (patch.path, patch.line, patch.owner, patch.mechanism)
        unique[key] = patch
    return sorted(unique.values(), key=lambda item: (item.path, item.line, item.owner))


def build_report(path: Path) -> dict[str, object]:
    patches = audit_sitecustomize(path)
    owners = sorted({patch.owner for patch in patches})
    return {
        "schema_version": 1,
        "sitecustomize_path": str(path),
        "active_patch_count": len(patches),
        "active_patch_owners": owners,
        "certification_ready": len(patches) == 0,
        "patches": [asdict(patch) for patch in patches],
    }


def write_markdown(report: dict[str, object], path: Path) -> None:
    lines = [
        "# Runtime Shim Audit",
        "",
        f"- Sitecustomize: `{report['sitecustomize_path']}`",
        f"- Active automatic patches: `{report['active_patch_count']}`",
        f"- Certification ready: `{report['certification_ready']}`",
        "",
        "## Active patches",
        "",
    ]
    patches = report["patches"]
    if patches:
        for patch in patches:
            lines.append(
                f"- `{patch['path']}:{patch['line']}` — `{patch['owner']}` "
                f"({patch['mechanism']}): {patch['description']}"
            )
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Certification rule",
            "",
            "A production-parity QA certification requires zero automatic behavior patches from `sitecustomize.py`.",
            "Compatibility helpers may remain only when they do not replace TradeBot-owned behavior and are independently justified.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inventory automatic runtime/test shims installed by sitecustomize.py."
    )
    parser.add_argument("--sitecustomize", default="sitecustomize.py")
    parser.add_argument("--report-dir", default=".runtime/qa")
    parser.add_argument("--fail-on-active", action="store_true")
    args = parser.parse_args()

    source_path = Path(args.sitecustomize)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "runtime_shim_report.json"
    md_path = report_dir / "runtime_shim_report.md"

    try:
        report = build_report(source_path)
    except (OSError, SyntaxError) as exc:
        print(f"RUNTIME SHIM AUDIT: ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    write_markdown(report, md_path)
    print(
        "RUNTIME SHIM AUDIT: "
        f"active={report['active_patch_count']} "
        f"certification_ready={report['certification_ready']}"
    )
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    if args.fail_on_active and report["active_patch_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
