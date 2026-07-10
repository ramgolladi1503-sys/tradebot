from datetime import datetime
import threading

from core import orchestrator_reports as _orchestrator_reports
from core.orchestrator_reports import load_truth_dataset_for_reports


def update_risk_pct_fields(orch):
    try:
        equity_high = orch.portfolio.get("equity_high", orch.portfolio.get("capital", 0.0))
        daily_pnl = orch.portfolio.get("daily_profit", 0.0) + orch.portfolio.get("daily_loss", 0.0)
        orch.portfolio["daily_pnl"] = daily_pnl
        orch.portfolio["daily_pnl_pct"] = 0.0 if equity_high in (None, 0) else daily_pnl / float(equity_high)
        open_risk = orch._open_risk()
        orch.portfolio["open_risk"] = open_risk
        orch.portfolio["open_risk_pct"] = 0.0 if equity_high in (None, 0) else open_risk / float(equity_high)
    except Exception:
        pass


def quote_age_sec(quote_ts):
    from core.orchestrator_truth import safe_float
    from core.time_utils import now_utc_epoch
    if not quote_ts:
        return None
    try:
        if isinstance(quote_ts, (int, float)):
            ts = float(quote_ts)
        else:
            text = str(quote_ts)
            try:
                ts = float(text)
            except Exception:
                ts = datetime.fromisoformat(text).timestamp()
        return max(0.0, now_utc_epoch() - ts)
    except Exception:
        return None


def quote_ts_epoch(quote_ts):
    if not quote_ts:
        return None
    if isinstance(quote_ts, (int, float)):
        return float(quote_ts)
    try:
        return float(quote_ts)
    except Exception:
        pass
    try:
        text = str(quote_ts)
        if text.endswith("Z"):
            text = text.replace("Z", "+00:00")
        return datetime.fromisoformat(text).timestamp()
    except Exception:
        return None


def _do_write_cycle_reports(*args, **kwargs):
    return _orchestrator_reports.write_cycle_reports(*args, **kwargs)


def write_cycle_reports(*args, **kwargs):
    thread = threading.Thread(target=_do_write_cycle_reports, args=args, kwargs=kwargs, daemon=True)
    thread.start()
    return thread
