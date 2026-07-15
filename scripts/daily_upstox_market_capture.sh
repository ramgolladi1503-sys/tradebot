#!/bin/bash
# scripts/daily_upstox_market_capture.sh
# Automates the daily market data capture, file combining, and GitHub push.
# Expected to be launched via cron around 09:14 AM IST (market opens at 09:15).

set -e

# 1. Setup workspace
cd /Users/madhuram/tradebot

# 2. Source environment variables to get UPSTOX_ACCESS_TOKEN
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
else
    echo "[!] .env file not found. UPSTOX_ACCESS_TOKEN may be missing."
fi

if [ -z "$UPSTOX_ACCESS_TOKEN" ]; then
    echo "[!] UPSTOX_ACCESS_TOKEN is not set in environment or .env file. Aborting."
    exit 1
fi

echo "[*] Starting daily market data capture pipeline..."

source .venv/bin/activate

# 3. Start the capture script
# The python script is designed to run until 15:35 IST and then terminate automatically.
python scripts/capture_upstox_market_daily.py

echo "[*] Capture script finished. Proceeding with file concatenation."

# 4. Run the combination script
python scripts/combine_parquet.py

echo "[*] Concatenation finished. Proceeding to push to GitHub via LFS."

# 5. Git commit and push logic
TODAY=$(date +"%Y%m%d")
BRANCH_NAME="data/combined-upstox-$TODAY"
FILE_PATH="runtime/market_data/upstox/$TODAY/combined.parquet"

if [ -f "$FILE_PATH" ]; then
    # Create or switch to the daily backup branch (detached from current HEAD to avoid main issues)
    # We will branch off origin/main to ensure a clean commit history.
    git fetch origin main
    git checkout -B $BRANCH_NAME origin/main
    
    # Ensure LFS is tracking parquets
    git lfs install
    git lfs track "*.parquet"
    
    # Force add the file in case it is ignored in .gitignore
    git add -f "$FILE_PATH" .gitattributes
    
    git commit -m "data: push final combined upstox parquet for $TODAY"
    
    echo "[*] Pushing branch $BRANCH_NAME to origin..."
    git push -u origin $BRANCH_NAME
    
    echo "[*] Pipeline completed successfully!"
else
    echo "[!] Combined file $FILE_PATH was not generated! Something went wrong."
    exit 1
fi
