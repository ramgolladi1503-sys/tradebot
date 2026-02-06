from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import json
import hmac
import hashlib
import requests
import pandas as pd

URL = "http://localhost:8000/webhook"
SECRET = "YOUR_TV_SHARED_SECRET"
EXCEL_PATH = "logs/signals.xlsx"

df = pd.read_excel(EXCEL_PATH)
for _, row in df.iterrows():
    payload = row.to_dict()
    raw = json.dumps(payload).encode()
    signature = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    resp = requests.post(URL, json=payload, headers={"X-Signature": signature})
    print(resp.status_code, resp.text)
