#!/bin/bash
while true; do
  checks=$(gh pr checks 716 2>&1)
  if echo "$checks" | grep -q "pending" || echo "$checks" | grep -q "in_progress"; then
    echo "Checks are still pending..."
    sleep 15
  elif echo "$checks" | grep -q "fail"; then
    echo "Checks failed!"
    exit 1
  else
    echo "Checks passed, merging..."
    gh pr merge 716 --squash --delete-branch
    if [ $? -eq 0 ]; then
      echo "Merged successfully!"
      cd /Users/madhuram
      git -C /Users/madhuram/tradebot worktree remove /Users/madhuram/tradebot-feature-production-option-analytics-v1 --force
      exit 0
    else
      echo "Failed to merge, retrying..."
      sleep 15
    fi
  fi
done
