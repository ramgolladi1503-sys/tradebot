import sqlite3
from pathlib import Path


def test_experiments_table_creation(tmp_path):
    db = tmp_path / "exp.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS experiments (experiment_id TEXT PRIMARY KEY, name TEXT, status TEXT, created_epoch REAL, started_epoch REAL, stopped_epoch REAL, metadata_json TEXT)"
        )
    assert db.exists()
