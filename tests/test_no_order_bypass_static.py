from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _line_hits(path: Path, needle: str) -> list[int]:
    hits = []
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if needle in line and not line.strip().startswith("#"):
            hits.append(idx)
    return hits


def test_no_direct_broker_place_order_bypass() -> None:
    allowlist = {
        "tools/legacy/flatten_positions.py",
    }
    offenders: list[str] = []
    for path in REPO_ROOT.rglob("*.py"):
        rel = str(path.relative_to(REPO_ROOT))
        if rel.startswith("tests/"):
            continue
        hit_lines = _line_hits(path, ".place_order(")
        if not hit_lines:
            continue
        if rel not in allowlist:
            offenders.append(f"{rel}:{','.join(str(x) for x in hit_lines)}")
            continue
        body = path.read_text(encoding="utf-8")
        if "require_approval_or_abort(" not in body:
            offenders.append(f"{rel}:missing_chokepoint")
        if "--i-know-what-im-doing" not in body:
            offenders.append(f"{rel}:missing_i_know_flag")
    assert not offenders, "Direct broker place_order bypass detected:\n" + "\n".join(offenders)


def test_no_direct_paper_fill_simulator_bypass() -> None:
    allowlist = {
        "core/execution_router.py",
        "core/paper_fill_simulator.py",
    }
    offenders: list[str] = []
    for path in REPO_ROOT.rglob("*.py"):
        rel = str(path.relative_to(REPO_ROOT))
        if rel.startswith("tests/"):
            continue
        hit_lines = _line_hits(path, "paper_sim.simulate(")
        if hit_lines and rel not in allowlist:
            offenders.append(f"{rel}:{','.join(str(x) for x in hit_lines)}")
    assert not offenders, "Direct paper fill simulator bypass detected:\n" + "\n".join(offenders)

