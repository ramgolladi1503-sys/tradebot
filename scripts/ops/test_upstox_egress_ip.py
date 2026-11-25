#!/usr/bin/env python3
"""Checks whether outgoing traffic to Upstox passes through the whitelisted static IP."""
import sys
import requests

EXPECTED_IP = "52.65.141.23"
PROXIES = {
    "http": "socks5h://127.0.0.1:1080",
    "https": "socks5h://127.0.0.1:1080",
}

print(f"[*] Testing outgoing IP via local proxy 127.0.0.1:1080...")
try:
    r = requests.get("https://api.ipify.org?format=json", proxies=PROXIES, timeout=5)
    ip = r.json().get("ip")
    print(f"[✓] Outgoing IP via proxy: {ip}")
    if ip == EXPECTED_IP:
        print(f"[✓] CONFIRMED: Outgoing IP matches whitelisted Upstox IP ({EXPECTED_IP})!")
    else:
        print(f"[!] MISMATCH: Outgoing IP is {ip}, expected {EXPECTED_IP}")
except Exception as e:
    print(f"[*] Proxy not active or reachable: {e}")
