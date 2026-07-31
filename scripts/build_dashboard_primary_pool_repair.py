from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"dashboard_primary_pool_match_mismatch:{count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    path = ROOT / "dashboard/streamlit_app_runtime.py"
    replace_once(
        path,
        '''def _select_advisory_table_source(
''',
        '''def _show_executable_primary(show_advisory_candidates: bool) -> bool:
    """Keep executable opportunities primary unless the operator explicitly opens diagnostics."""
    return not bool(show_advisory_candidates)


def _select_advisory_table_source(
''',
    )
    replace_once(
        path,
        '''            show_exec_only = st.checkbox(
                "Executable only",
                value=False,
                key="suggested_trades_exec_only",
            )
''',
        '''            show_advisory_candidates = st.checkbox(
                "Show advisory/debug candidates",
                value=False,
                key="suggested_trades_show_advisory",
                help=(
                    "Executable opportunities remain the primary view. Advisory, recovered-fallback, "
                    "and near-executable rows never receive execution authority or capital."
                ),
            )
            show_exec_only = _show_executable_primary(show_advisory_candidates)
''',
    )
    print("dashboard_primary_pool_repair_built")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
