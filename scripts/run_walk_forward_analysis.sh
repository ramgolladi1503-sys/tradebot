#!/usr/bin/env bash

set -e

# Walk-Forward Backtesting & Strategy Optimization Script
# This script is strictly offline and adheres to Tradebot rules.

# Ensure we are in the repo root
cd "$(dirname "$0")/.."

# Execute the python pipeline
export PYTHONPATH="."
python -m core.analytics.walk_forward_pipeline
