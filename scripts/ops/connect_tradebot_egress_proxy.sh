#!/usr/bin/env bash
# ==============================================================================
# TradeBot AWS Fixed Egress SOCKS5 Proxy Connector
# Static IP: 52.65.141.23 (AWS ap-southeast-2)
# ==============================================================================
set -euo pipefail

PROXY_IP="52.65.141.23"
KEY_PATH="${1:-$HOME/Downloads/tradebot-proxy.pem}"
LOCAL_PORT="1080"

if [ ! -f "$KEY_PATH" ]; then
    echo "[!] Error: SSH Private Key not found at $KEY_PATH"
    echo "Usage: ./connect_tradebot_egress_proxy.sh [path_to_pem_file]"
    exit 1
fi

chmod 400 "$KEY_PATH"

echo "[*] Initializing SOCKS5 tunnel to AWS Static IP ($PROXY_IP)..."
if pgrep -f "ssh.*-D $LOCAL_PORT.*$PROXY_IP" > /dev/null; then
    echo "[✓] Proxy tunnel is already running on port $LOCAL_PORT."
else
    ssh -i "$KEY_PATH" -D "$LOCAL_PORT" -f -N -C -q -o "StrictHostKeyChecking=no" -o "UserKnownHostsFile=/dev/null" ec2-user@"$PROXY_IP"
    echo "[✓] Encrypted SOCKS5 proxy active on 127.0.0.1:$LOCAL_PORT"
fi

# Verify egress public IP matches whitelisted Upstox IP
OUTGOING_IP=$(curl --socks5-hostname "127.0.0.1:$LOCAL_PORT" -s https://api.ipify.org || echo "FAILED")
echo "[*] Verified Outgoing Egress IP: $OUTGOING_IP"

if [ "$OUTGOING_IP" = "$PROXY_IP" ]; then
    echo "[✓] SUCCESS: Outgoing traffic verified as $PROXY_IP (Whitelisted Upstox IP)"
else
    echo "[!] Warning: Egress IP ($OUTGOING_IP) does not match expected ($PROXY_IP)"
fi
