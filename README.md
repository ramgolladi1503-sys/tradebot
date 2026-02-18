## Setup

Install dependencies:
```bash
pip install -r requirements.txt
```
After pulling changes, run the same command again to sync new dependencies.

Create a `.env` file using the provided template:
```bash
cp .env.example .env
```

Example `.env` values:
```env
KITE_API_KEY=your_kite_api_key
KITE_API_SECRET=your_kite_api_secret
KITE_ACCESS_TOKEN=your_kite_access_token
KITE_USE_API=true
KITE_TRADES_SYNC=true
KITE_INSTRUMENTS_TTL=3600
TERM_STRUCTURE_EXPIRY=WEEKLY

ENABLE_TELEGRAM=true
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

EMAIL_REPORTS=false
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_TO=
```

## Run

Start the live bot:
```bash
python main.py
```

## Decision Logging

Decision logging can be enabled to persist Decision objects into a SQLite table.

- Enable with: `DECISION_LOG_ENABLED=true`
- Database path: `DECISION_DB_PATH` (defaults to `TRADE_DB_PATH`)
- Table: `decision_log` with columns `decision_id, ts_epoch, run_id, symbol, status, decision_json`

Depth websocket (optional):
```bash
python scripts/start_depth_ws.py
```
Depth snapshots are stored in SQLite `depth_snapshots`.
Tick data is stored in SQLite `ticks`.

Check Kite auth:
```bash
python scripts/check_kite_auth.py
```

Validate Kite session from .env (safe):
```bash
python scripts/validate_kite_session.py
```

Generate a fresh access token from request token:
```bash
python scripts/generate_kite_access_token.py
python scripts/generate_kite_access_token.py --update-env
```

Download instruments (fallback CSV):
```bash
python scripts/download_instruments.py
```

Manual approval (when enabled):
```bash
python scripts/approve_trade.py <trade_id>
```

Long-horizon labeling storage is persisted in SQLite:
```
data/trades.db
```

## RL Scaffold

Run RL environment stub:
```bash
python rl/train_stub.py
```

Train PPO or DDPG:
```bash
python rl/train_ppo.py
python rl/train_ddpg.py
```

Train/validate RL with split:
```bash
python rl/train_validate_rl.py
```

RL metrics are logged to `logs/rl_metrics.csv`.
RL metrics are also logged to `logs/rl_metrics.json` and sent to Telegram if enabled.
Micro rolling window and alert threshold can be set in `config/config.py`.

## ML Training & Evaluation

Build dataset, train model, and evaluate walk-forward:
```bash
python models/build_ml_dataset.py
python models/train_live_model.py
python models/train_deep_model.py
python models/train_micro_model.py
python models/walk_forward_train.py
```
Register and activate model after training:
```bash
python models/train_live_model.py --register
python scripts/activate_model.py --type xgb --path models/xgb_live_model.pkl
```

## Tick Training

Build a tick-based dataset from SQLite and optionally join nearest depth snapshots:
```bash
python models/train_from_ticks.py --out data/tick_features.csv
python models/train_from_ticks.py --from-depth --depth-tolerance-sec 2 --train-micro
```
Audit tick/depth dataset:
```bash
python scripts/audit_market_data.py
```

## TradingView Alerts

Start webhook server:
```bash
python scripts/tradingview_webhook.py
```

Alerts are queued in `logs/tv_queue.json`.
Alerts with trade fields are also added to `logs/review_queue.json`.
Signature verification uses `X-Signature` header with HMAC-SHA256 and `TV_SHARED_SECRET`.
Signature example (GET):
```
http://localhost:8000/signature_example
```

Test TradingView client:
```bash
python scripts/tv_test_client.py
```

## Excel Integration

Export trades to Excel:
```bash
python scripts/export_trades_excel.py
```

Import signals from Excel:
```bash
python scripts/import_signals_excel.py
```

Microstructure model live accuracy:
```bash
python scripts/micro_accuracy.py
```

Auto-run with best params from grid search:
```bash
python models/optimize_ml_params.py
python models/best_params_train.py
```

## Backtest

Run a backtest on sample data:
```bash
python core/run_backtest.py
```

## Testing

Run unit tests:
```bash
pytest -q
```

Automation script (logs to `logs/test_runs.log`):
```bash
./scripts/run_tests.sh
```

## Trade Outcome Labeling (for ML retraining)

Update a trade outcome (after exit):
```bash
python scripts/update_trade_outcome.py <trade_id> <exit_price> [actual(1/0)]
```

Export JSON log to CSV for retraining:
```bash
python scripts/export_trade_log_csv.py
```

Strategy performance tracking (auto-disables underperformers):
- Outcomes are recorded when you run `scripts/update_trade_outcome.py`
- Strategy scores persist in `logs/strategy_perf.json`

## Reports & Dashboard

Daily report (JSON + CSV):
```bash
python scripts/daily_report.py
```

Risk monitor (independent check):
```bash
python scripts/risk_monitor.py
python scripts/reset_risk_halt.py
./scripts/kill_switch.sh
```

Scorecard (top-1% readiness):
```bash
python scripts/update_scorecard.py
```

Daily scorecard + Telegram summary:
```bash
python scripts/daily_scorecard.py
```

Streamlit dashboard:
```bash
streamlit run dashboard/streamlit_app.py
```

Execution analytics:
```bash
python scripts/run_execution_analytics.py
```

Data governance helpers:
```bash
python scripts/hash_trade_log.py
python scripts/data_manifest.py
python scripts/freeze_dataset.py
```

Daily ops bundle:
```bash
python scripts/daily_ops.py
```

Live fills sync (run every 5 minutes):
```bash
python scripts/live_fills_sync.py
```

Data QC / SLA checks:
```bash
python scripts/data_qc.py
python scripts/sla_check.py
python scripts/daily_rollup.py
```

Reconcile fills vs trade log:
```bash
python scripts/reconcile_fills.py
```

Execution router live intent log:
```bash
cat logs/execution_intents.jsonl
```

Soft-kill thresholds (config):
- `MIN_DAILY_PF`
- `MIN_DAILY_SHARPE`
- `PERF_ALERT_DAYS`

Generate sample trades (for testing dashboard):
```bash
python scripts/generate_sample_trades.py
```

Email/Telegram delivery:
- Telegram uses `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
- Email uses SMTP env vars (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TO`)

## Troubleshooting

- Missing env vars warning: ensure your `.env` file is present and filled, or export the variables in your shell.
- `ModuleNotFoundError`: run `pip install -r requirements.txt`.
- If no trades are generated, check that market data is available and your ML model has been trained.
