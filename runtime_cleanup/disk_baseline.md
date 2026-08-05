# Disk Baseline

```json
{
  "generated_at": "2026-08-05T06:31:58.553799+00:00",
  "repo": "/Users/madhuram/tradebot",
  "shared_root": "/Users/madhuram/tradebot-shared-data",
  "date": {
    "args": [
      "date"
    ],
    "returncode": 0,
    "stdout": "Wed Aug  5 12:01:58 IST 2026",
    "stderr": ""
  },
  "df_h": {
    "args": [
      "df",
      "-h",
      "/"
    ],
    "returncode": 0,
    "stdout": "Filesystem        Size    Used   Avail Capacity iused ifree %iused  Mounted on\n/dev/disk3s1s1   228Gi    11Gi   2.4Gi    83%    453k   25M    2%   /",
    "stderr": ""
  },
  "df_k": {
    "args": [
      "df",
      "-k",
      "/"
    ],
    "returncode": 0,
    "stdout": "Filesystem     1024-blocks      Used Available Capacity iused    ifree %iused  Mounted on\n/dev/disk3s1s1   239362496  12007860   2464940    83%  453127 24649400    2%   /",
    "stderr": ""
  },
  "active_processes": {
    "args": [
      "bash",
      "-lc",
      "ps aux | grep -E 'tradebot|kite|upstox|market_event|persistence|parquet' | grep -v grep || true"
    ],
    "returncode": 0,
    "stdout": "madhuram         20027  88.2  1.7 412139152 140912   ??  R    12:01PM   0:02.98 /opt/anaconda3/bin/python /Users/madhuram/tradebot/scripts/scheduler.py\nmadhuram         13889   5.6  0.7 413652448  61984   ??  S    10:42AM   7:55.13 python -u scripts/upstox_capture/run_upstox_replay_capture_v1.py --session-date 20260805 --campaign-id meg-dual-provider-20260805-04 --output-root .runtime/market_data/upstox_multi_asset/20260805\nmadhuram          7012   0.0  0.0 435331584   1216   ??  S     9:09AM   0:00.28 /Users/madhuram/tradebot/.venv/bin/python -c from multiprocessing.resource_tracker import main;main(7)\nmadhuram          6997   0.0  0.1 435837952   7232   ??  S     9:09AM   0:20.20 .venv/bin/python scripts/upstox_full_tick_collector.py\nmadhuram         41504   0.0  0.1 412478096   6848   ??  S    Tue09AM   1:05.05 python3 scripts/upstox_full_tick_collector.py\nmadhuram         35006   0.0  0.4 436836192  36624   ??  S    Tue12AM   0:30.23 /Applications/Antigravity.app/Contents/Resources/bin/language_server multicall schedule 0 9 * * 1-5 agentapi new-conversation Run the upstox tick data collector script (upstox_full_tick_collector.py) in the background.\nmadhuram         65016   0.0  0.0 435327600   1056   ??  S    Mon09AM   0:00.06 /Users/madhuram/tradebot/.venv/bin/python -c from multiprocessing.resource_tracker import main;main(7)\nmadhuram         64993   0.0  0.2 435844144  13792   ??  S    Mon09AM   2:10.47 .venv/bin/python scripts/upstox_full_tick_collector.py\nmadhuram          2287   0.0  0.0 411575856      0   ??  S    25Jul26   0:00.52 /opt/anaconda3/bin/python -m streamlit run /Users/madhuram/tradebot/dashboard/streamlit_app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true\nmadhuram          2272   0.0  0.0 435299280     16   ??  S    25Jul26   0:00.02 /bin/bash /Users/madhuram/tradebot/scripts/run_all.sh",
    "stderr": ""
  },
  "active_repair_runtime_lsof": {
    "args": [
      "bash",
      "-lc",
      "lsof +D /Users/madhuram/tradebot-kite-depth-persistence-saturation-v1/runtime 2>/dev/null || true"
    ],
    "returncode": 0,
    "stdout": "",
    "stderr": ""
  }
}
```
