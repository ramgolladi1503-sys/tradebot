import json
import sqlite3
from pathlib import Path
from datetime import datetime
from config import config as cfg

def _read_trade_log():
    path = Path("data/trade_log.json")
    if not path.exists():
        return None
    rows = []
    with open(path, "r") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows

def _days_of_live_trading(rows):
    if not rows:
        return 0
    try:
        ts = [datetime.fromisoformat(r["timestamp"]) for r in rows if r.get("timestamp")]
    except Exception:
        return 0
    if not ts:
        return 0
    return (max(ts) - min(ts)).days

def _db_counts():
    db = Path(cfg.TRADE_DB_PATH)
    if not db.exists():
        return {"ticks": 0, "depth": 0}
    try:
        conn = sqlite3.connect(db)
        ticks = conn.execute("SELECT COUNT(*) FROM ticks").fetchone()[0]
        depth = conn.execute("SELECT COUNT(*) FROM depth_snapshots").fetchone()[0]
        conn.close()
        return {"ticks": ticks, "depth": depth}
    except Exception:
        return {"ticks": 0, "depth": 0}

def _model_registry_status():
    path = Path("logs/model_registry.json")
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
        return bool(data.get("active"))
    except Exception:
        return False

def _remaining_for(item, status):
    if status == "PASS":
        return []
    if item == "Live performance proof":
        return [
            "Accumulate 6-12 months of live logs",
            "Compute rolling PF/Sharpe/Drawdown",
            "Lock dataset timestamps (no edits)",
        ]
    if item == "Real execution router":
        return [
            "Enable live fills",
            "Log fill ratios + latency",
            "Enable queue-position model",
        ]
    if item == "Tick/depth research dataset":
        return [
            "Collect tick table at scale",
            "Collect depth snapshots at scale",
            "Run data audit and store results",
        ]
    if item == "Strict risk governance":
        return [
            "Enable auto-halt on drawdown",
            "Independent daily risk monitor",
            "Document risk limits",
        ]
    if item == "Model governance":
        return [
            "Register models with metrics",
            "Activate specific model versions",
            "Support rollback by registry",
        ]
    return []

def compute_scorecard():
    rows = _read_trade_log()
    live_days = _days_of_live_trading(rows)
    live_needed = getattr(cfg, "SCORECARD_LIVE_DAYS", 180)
    paper_needed = getattr(cfg, "SCORECARD_PAPER_DAYS", 30)
    live_ok = live_days >= live_needed
    paper_ok = live_days >= paper_needed

    counts = _db_counts()
    ticks_ok = counts["ticks"] >= getattr(cfg, "SCORECARD_TICK_MIN", 50000)
    depth_ok = counts["depth"] >= getattr(cfg, "SCORECARD_DEPTH_MIN", 5000)
    data_ok = ticks_ok and depth_ok and Path("logs/data_audit.json").exists()

    exec_live = bool(getattr(cfg, "EXECUTION_MODE_LIVE", False)) or getattr(cfg, "EXECUTION_MODE", "SIM") == "LIVE"
    exec_stats = Path("logs/execution_stats.csv").exists() or Path("data/trades.db").exists()
    exec_status = "NEEDS"
    if exec_stats:
        exec_status = "PARTIAL"
    if exec_live and exec_stats:
        exec_status = "PASS"
    # Promote based on execution analytics evidence
    try:
        ea_path = Path("logs/execution_analytics.json")
        if ea_path.exists():
            ea = json.loads(ea_path.read_text())
            fill_ratio = ea.get("fill_ratio")
            avg_latency = ea.get("avg_latency_ms")
            if fill_ratio is not None and fill_ratio >= 0.9 and avg_latency is not None:
                exec_status = "PASS"
            elif fill_ratio is not None:
                exec_status = "PARTIAL"
    except Exception:
        pass

    # Risk governance evidence: halt file + daily monitor output
    risk_governed = Path(cfg.RISK_HALT_FILE).exists() or Path("logs/risk_monitor.json").exists()
    model_governed = _model_registry_status()

    # Progress counters
    live_progress = f"{live_days}/{live_needed} days"
    ticks_needed = getattr(cfg, "SCORECARD_TICK_MIN", 50000)
    depth_needed = getattr(cfg, "SCORECARD_DEPTH_MIN", 5000)
    tick_progress = f"{counts['ticks']}/{ticks_needed}"
    depth_progress = f"{counts['depth']}/{depth_needed}"

    exec_progress = "No fills"
    try:
        ea_path = Path("logs/execution_analytics.json")
        if ea_path.exists():
            ea = json.loads(ea_path.read_text())
            fill_ratio = ea.get("fill_ratio")
            exec_progress = f"fill_ratio={fill_ratio}" if fill_ratio is not None else exec_progress
    except Exception:
        pass

    scorecard = [
        {
            "item": "Live performance proof",
            "status": "PASS" if live_ok else "NEEDS",
            "details": f"{live_days} days (target {live_needed})",
            "progress": live_progress,
            "remaining": _remaining_for("Live performance proof", "PASS" if live_ok else "NEEDS"),
        },
        {
            "item": "Paper performance proof",
            "status": "PASS" if paper_ok else "NEEDS",
            "details": f"{live_days} days (target {paper_needed})",
            "progress": f"{live_days}/{paper_needed} days",
            "remaining": [] if paper_ok else ["Accumulate paper logs"],
        },
        {
            "item": "Real execution router",
            "status": exec_status,
            "details": "Live fills + slicing + queue model" if exec_status == "PASS" else "Simulated or partial",
            "progress": exec_progress,
            "remaining": _remaining_for("Real execution router", exec_status),
        },
        {
            "item": "Tick/depth research dataset",
            "status": "PASS" if data_ok else "NEEDS",
            "details": f"ticks={counts['ticks']} depth={counts['depth']}",
            "progress": f"ticks {tick_progress}, depth {depth_progress}",
            "remaining": _remaining_for("Tick/depth research dataset", "PASS" if data_ok else "NEEDS"),
        },
        {
            "item": "Strict risk governance",
            "status": "PASS" if risk_governed else "NEEDS",
            "details": "Auto-halt + monitor" if risk_governed else "Missing halt file",
            "progress": "monitor_ok" if risk_governed else "no_monitor",
            "remaining": _remaining_for("Strict risk governance", "PASS" if risk_governed else "NEEDS"),
        },
        {
            "item": "Model governance",
            "status": "PASS" if model_governed else "NEEDS",
            "details": "Registry + activation/rollback" if model_governed else "No registry",
            "progress": "active" if model_governed else "inactive",
            "remaining": _remaining_for("Model governance", "PASS" if model_governed else "NEEDS"),
        },
    ]
    return scorecard

def write_scorecard(path="logs/scorecard.json"):
    sc = compute_scorecard()
    out = Path(path)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(sc, indent=2))
    return sc

def append_scorecard_history(path="logs/scorecard_history.json"):
    sc = compute_scorecard()
    out = Path(path)
    out.parent.mkdir(exist_ok=True)
    history = []
    if out.exists():
        try:
            history = json.loads(out.read_text())
        except Exception:
            history = []
    exec_metrics = {}
    try:
        ea_path = Path("logs/execution_analytics.json")
        if ea_path.exists():
            exec_metrics = json.loads(ea_path.read_text())
    except Exception:
        exec_metrics = {}
    history.append({
        "ts": datetime.now().isoformat(),
        "scorecard": sc,
        "execution": exec_metrics,
    })
    out.write_text(json.dumps(history[-1000:], indent=2))
    return history
