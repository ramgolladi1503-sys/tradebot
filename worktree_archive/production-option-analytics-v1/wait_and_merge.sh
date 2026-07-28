#!/bin/bash
while true; do
  checks=$(gh pr checks 716 2>&1)
  if echo "$checks" | grep -q "pending"; then
    echo "Checks are still pending..."
    sleep 10
  elif echo "$checks" | grep -q "fail"; then
    echo "Checks failed!"
    exit 1
  else
    echo "Checks passed, merging..."
    gh pr merge 716 --squash --delete-branch
    if [ $? -eq 0 ]; then
      echo "Merged successfully!"
      exit 0
    else
      echo "Failed to merge, retrying..."
      sleep 10
    fi
  fi
done
