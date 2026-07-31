from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    path = ROOT / "dashboard/streamlit_app_runtime.py"
    text = path.read_text(encoding="utf-8")
    old = '''    if str(snapshot.get("state") or "") != "ok":
        import streamlit as st
        st.error("canonical ranked pipeline missing")
        return {"top_executable": pd.DataFrame(), "top_advisory": pd.DataFrame()}
    if str(snapshot.get("state") or "") != "ok":
        return {"top_executable": pd.DataFrame(), "top_advisory": pd.DataFrame()}
'''
    new = '''    if not isinstance(snapshot, dict) or str(snapshot.get("state") or "") != "ok":
        try:
            import streamlit as st

            st.error("canonical ranked pipeline missing")
        except Exception:
            logger.warning("dashboard_canonical_ranked_pipeline_missing")
        return {"top_executable": pd.DataFrame(), "top_advisory": pd.DataFrame()}
'''
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"dashboard_runtime_guard_match_mismatch:{count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("dashboard_runtime_guard_repair_built")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
