import argparse
from core.db_guard import ensure_db_ready


def main():
    parser = argparse.ArgumentParser(description="Recover DB path and clear db_write_fail halt if applicable.")
    parser.add_argument("--db-path", default=None, help="Override DB path for probe.")
    args = parser.parse_args()

    try:
        result = ensure_db_ready(db_path=args.db_path)
    except RuntimeError as exc:
        print(f"[DB_RECOVERY_FAIL] {exc}")
        raise SystemExit(2)

    print(f"[DB_RECOVERY_OK] db_path={result.get('db_path')} ok={result.get('ok')}")


if __name__ == "__main__":
    main()
