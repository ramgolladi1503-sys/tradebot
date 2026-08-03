#!/usr/bin/env python3
"""Build, query, evaluate, and inspect the local TradeBot RAG index."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.tradebot_rag import (
    DEFAULT_INCLUDE_PATHS,
    ask_index,
    build_index,
    default_index_path,
    index_status,
    search_index,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _build(args: argparse.Namespace) -> int:
    root = Path(args.repo_root).expanduser().resolve()
    index_path = Path(args.index).expanduser() if args.index else default_index_path(root)
    report = build_index(
        root,
        index_path,
        include_paths=tuple(args.include),
        max_file_bytes=args.max_file_bytes,
        max_chunk_chars=args.chunk_chars,
        overlap_lines=args.overlap_lines,
    )
    _print_json(report.__dict__)
    return 0


def _query(args: argparse.Namespace) -> int:
    root = Path(args.repo_root).expanduser().resolve()
    index_path = Path(args.index).expanduser() if args.index else default_index_path(root)
    answer = ask_index(
        index_path,
        args.question,
        top_k=args.top_k,
        path_prefix=args.path_prefix,
        min_score=args.min_score,
    )
    if args.json:
        _print_json(answer.to_dict())
    else:
        print(answer.answer)
        print(f"\nConfidence: {answer.confidence}")
    return 2 if answer.refusal_reason else 0


def _status(args: argparse.Namespace) -> int:
    root = Path(args.repo_root).expanduser().resolve()
    index_path = Path(args.index).expanduser() if args.index else default_index_path(root)
    payload = index_status(index_path)
    _print_json(payload)
    return 0 if payload["exists"] else 2


def _evaluate(args: argparse.Namespace) -> int:
    root = Path(args.repo_root).expanduser().resolve()
    index_path = Path(args.index).expanduser() if args.index else default_index_path(root)
    cases_path = Path(args.cases).expanduser()
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("evaluation_cases_must_be_nonempty_list")

    results = []
    reciprocal_ranks = []
    hit_count = 0
    for case in cases:
        query = str(case["query"])
        expected_paths = tuple(str(item) for item in case.get("expected_paths", []))
        expected_terms = tuple(str(item).lower() for item in case.get("expected_terms", []))
        hits = search_index(index_path, query, top_k=args.top_k)
        rank = None
        for index, hit in enumerate(hits, start=1):
            path_ok = not expected_paths or any(expected in hit.path for expected in expected_paths)
            term_ok = not expected_terms or all(term in hit.text.lower() for term in expected_terms)
            if path_ok and term_ok:
                rank = index
                break
        passed = rank is not None
        hit_count += int(passed)
        reciprocal_ranks.append(0.0 if rank is None else 1.0 / rank)
        results.append(
            {
                "query": query,
                "passed": passed,
                "rank": rank,
                "top_paths": [hit.path for hit in hits],
            }
        )

    total = len(cases)
    summary = {
        "case_count": total,
        "hit_at_k": hit_count / total,
        "mrr": sum(reciprocal_ranks) / total,
        "top_k": args.top_k,
        "minimum_hit_at_k": args.min_hit_at_k,
        "passed": (hit_count / total) >= args.min_hit_at_k,
        "results": results,
    }
    _print_json(summary)
    return 0 if summary["passed"] else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(_repo_root()))
    parser.add_argument("--index", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Incrementally build the evidence index")
    build.add_argument("--include", nargs="+", default=list(DEFAULT_INCLUDE_PATHS))
    build.add_argument("--max-file-bytes", type=int, default=2_000_000)
    build.add_argument("--chunk-chars", type=int, default=1_800)
    build.add_argument("--overlap-lines", type=int, default=3)
    build.set_defaults(handler=_build)

    query = subparsers.add_parser("query", help="Ask a grounded question")
    query.add_argument("question")
    query.add_argument("--top-k", type=int, default=8)
    query.add_argument("--path-prefix", default=None)
    query.add_argument("--min-score", type=float, default=0.28)
    query.add_argument("--json", action="store_true")
    query.set_defaults(handler=_query)

    status = subparsers.add_parser("status", help="Inspect index metadata")
    status.set_defaults(handler=_status)

    evaluate = subparsers.add_parser("evaluate", help="Run deterministic retrieval evaluation")
    evaluate.add_argument("--cases", default=str(_repo_root() / "rag" / "eval_cases.json"))
    evaluate.add_argument("--top-k", type=int, default=5)
    evaluate.add_argument("--min-hit-at-k", type=float, default=0.8)
    evaluate.set_defaults(handler=_evaluate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
