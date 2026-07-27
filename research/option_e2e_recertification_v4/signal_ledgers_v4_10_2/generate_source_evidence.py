from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .source_search_manifest import (
    SOURCE_INCOMPLETE,
    build_git_search_manifest,
    compute_source_verdict,
    discover_root_inventory,
    file_sha256,
    inspect_candidate,
    iter_candidate_paths,
    semantic_hash,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _append_jsonl(handle, payload: dict[str, object]) -> None:
    handle.write(json.dumps(payload, sort_keys=True))
    handle.write("\n")
    handle.flush()


def _git_lead_resolved(git_searches: list[dict[str, object]]) -> bool:
    for search in git_searches:
        command = [str(item) for item in search.get("command", [])]
        if ("Aeron7" in command or "NIFTY_F1" in command) and search.get("stdout_lines"):
            return True
    return False


def generate(
    repo_root: Path,
    output_dir: Path,
    max_candidates_per_root: int,
    max_seconds_per_root: int,
    max_hash_bytes: int,
) -> dict[str, object]:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    checkpoints_dir = output_dir / "root_checkpoints"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)

    run_status_path = output_dir / "run_status.json"
    candidate_path = output_dir / "candidate_inventory.jsonl"
    candidate_path.touch()
    _write_json(
        run_status_path,
        {
            "status": "RUNNING",
            "repo_root": str(repo_root),
            "output_dir": str(output_dir),
        },
    )

    root_inventory: list[dict[str, object]] = []
    diagnostics: dict[str, object] = {}
    git_searches: list[dict[str, object]] = []
    root_summaries: list[dict[str, object]] = []
    accepted_candidates: list[dict[str, object]] = []
    unresolved_candidates: list[dict[str, object]] = []
    seen_physical_paths: set[Path] = set()
    candidate_count = 0
    accepted_count = 0
    unresolved_count = 0
    timed_out_root_count = 0
    truncated = False
    lead_seen = False

    try:
        root_inventory, diagnostics = discover_root_inventory(repo_root)
        _write_json(output_dir / "root_inventory.json", root_inventory)
        _write_json(output_dir / "local_diagnostics.json", diagnostics)

        git_searches = build_git_search_manifest(repo_root)
        _write_json(output_dir / "git_search_manifest.json", git_searches)

        root_paths = dict(diagnostics.get("root_paths", {}))
        with candidate_path.open("w", encoding="utf-8") as candidate_handle:
            for root_record in root_inventory:
                root_id = str(root_record["root_id"])
                root_class = str(root_record["root_class"])
                root_path = Path(str(root_paths.get(root_id, "")))
                root_started = time.monotonic()
                yielded_path_count = 0
                root_candidate_count = 0
                root_accepted_count = 0
                root_unresolved_count = 0
                root_errors: list[str] = []

                if not root_record.get("available") or not root_record.get("is_directory"):
                    summary = {
                        "root_id": root_id,
                        "status": "UNAVAILABLE",
                        "candidate_count": 0,
                        "accepted_candidate_count": 0,
                        "unresolved_candidate_count": 0,
                        "timed_out": False,
                        "truncated": False,
                        "errors": ["ROOT_UNAVAILABLE"],
                    }
                    root_summaries.append(summary)
                    _write_json(checkpoints_dir / f"{root_id}.json", summary)
                    continue

                try:
                    for path in iter_candidate_paths(
                        root_path,
                        root_class,
                        max_candidates=max_candidates_per_root,
                        max_seconds=max_seconds_per_root,
                        excluded_paths=(output_dir.parent,),
                    ):
                        yielded_path_count += 1
                        relative_lower = path.relative_to(root_path).as_posix().lower()
                        if "aeron7" in relative_lower or "nifty_f1" in relative_lower:
                            lead_seen = True
                        resolved_path = path.resolve()
                        if resolved_path in seen_physical_paths:
                            continue
                        seen_physical_paths.add(resolved_path)
                        try:
                            candidate = inspect_candidate(
                                root_id,
                                root_path,
                                path,
                                max_hash_bytes=max_hash_bytes,
                            )
                        except Exception as exc:
                            candidate = {
                                "root_id": root_id,
                                "relative_path": path.relative_to(root_path).as_posix(),
                                "classification": "CANDIDATE_INSPECTION_FAILED",
                                "accepted": False,
                                "unresolved": True,
                                "rejection_code": f"INSPECTION_FAILED:{type(exc).__name__}",
                            }
                        _append_jsonl(candidate_handle, candidate)
                        candidate_count += 1
                        root_candidate_count += 1
                        if candidate.get("accepted"):
                            accepted_count += 1
                            root_accepted_count += 1
                            accepted_candidates.append(candidate)
                        if candidate.get("unresolved"):
                            unresolved_count += 1
                            root_unresolved_count += 1
                            unresolved_candidates.append(candidate)
                except Exception as exc:
                    root_errors.append(f"ROOT_SCAN_FAILED:{type(exc).__name__}:{exc}")

                elapsed = time.monotonic() - root_started
                root_timed_out = elapsed >= max_seconds_per_root
                root_truncated = yielded_path_count >= max_candidates_per_root
                if root_timed_out:
                    timed_out_root_count += 1
                truncated = truncated or root_truncated
                summary = {
                    "root_id": root_id,
                    "status": "COMPLETE" if not root_errors and not root_timed_out and not root_truncated else "INCOMPLETE",
                    "yielded_path_count": yielded_path_count,
                    "candidate_count": root_candidate_count,
                    "accepted_candidate_count": root_accepted_count,
                    "unresolved_candidate_count": root_unresolved_count,
                    "elapsed_seconds": round(elapsed, 3),
                    "timed_out": root_timed_out,
                    "truncated": root_truncated,
                    "errors": root_errors,
                }
                root_summaries.append(summary)
                _write_json(checkpoints_dir / f"{root_id}.json", summary)
                _write_json(
                    run_status_path,
                    {
                        "status": "RUNNING",
                        "last_completed_root": root_id,
                        "candidate_count": candidate_count,
                        "accepted_candidate_count": accepted_count,
                        "unresolved_candidate_count": unresolved_count,
                    },
                )

        lead_resolved = lead_seen or _git_lead_resolved(git_searches)
        conclusion, reason_codes = compute_source_verdict(
            root_inventory=root_inventory,
            git_searches=git_searches,
            accepted_candidate_count=accepted_count,
            unresolved_candidate_count=unresolved_count,
            truncated=truncated,
            timed_out_root_count=timed_out_root_count,
            aeron7_nifty_f1_resolved=lead_resolved,
        )
        candidate_inventory_sha256 = file_sha256(candidate_path)
        semantic_payload = {
            "schema_version": "v4_10_2_streaming_source_search_v1",
            "root_inventory": root_inventory,
            "git_searches": git_searches,
            "root_summaries": root_summaries,
            "candidate_inventory_file": "candidate_inventory.jsonl",
            "candidate_inventory_sha256": candidate_inventory_sha256,
            "candidate_count": candidate_count,
            "accepted_candidate_count": accepted_count,
            "unresolved_candidate_count": unresolved_count,
            "accepted_candidates": accepted_candidates,
            "unresolved_candidates": unresolved_candidates,
            "aeron7_nifty_f1_lead_resolved": lead_resolved,
            "timed_out_root_count": timed_out_root_count,
            "truncated": truncated,
            "conclusion": conclusion,
            "reason_codes": reason_codes,
        }
        manifest_hash = semantic_hash(semantic_payload)
        manifest = {**semantic_payload, "semantic_sha256": manifest_hash}
        _write_json(output_dir / "source_search_manifest.json", manifest)
        (output_dir / "source_search_manifest.json.sha256").write_text(
            f"{manifest_hash}  source_search_manifest.json\n",
            encoding="utf-8",
        )

        summary = {
            "conclusion": conclusion,
            "reason_codes": reason_codes,
            "candidate_count": candidate_count,
            "accepted_candidate_count": accepted_count,
            "unresolved_candidate_count": unresolved_count,
            "timed_out_root_count": timed_out_root_count,
            "truncated": truncated,
            "aeron7_nifty_f1_lead_resolved": lead_resolved,
            "semantic_sha256": manifest_hash,
            "output_dir": str(output_dir),
        }
        _write_json(output_dir / "source_search_summary.json", summary)
        _write_json(run_status_path, {"status": "COMPLETE", **summary})
        return summary
    except Exception as exc:
        failure_summary = {
            "conclusion": SOURCE_INCOMPLETE,
            "reason_codes": [f"GENERATOR_FAILED:{type(exc).__name__}"],
            "candidate_count": candidate_count,
            "accepted_candidate_count": accepted_count,
            "unresolved_candidate_count": unresolved_count,
            "timed_out_root_count": timed_out_root_count,
            "truncated": truncated,
            "output_dir": str(output_dir),
            "error": str(exc),
        }
        _write_json(output_dir / "source_search_summary.json", failure_summary)
        _write_json(run_status_path, {"status": "FAILED", **failure_summary})
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate offline VWAP source-search evidence.")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-candidates-per-root", type=int, default=2500)
    parser.add_argument("--max-seconds-per-root", type=int, default=90)
    parser.add_argument("--max-hash-size-mb", type=int, default=2048)
    args = parser.parse_args()

    summary = generate(
        args.repo.resolve(),
        args.output.resolve(),
        args.max_candidates_per_root,
        args.max_seconds_per_root,
        args.max_hash_size_mb * 1024**2,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
