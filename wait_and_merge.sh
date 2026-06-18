while true; do
  gh pr checks > /dev/null 2>&1
  EXIT_CODE=$?
  if [ $EXIT_CODE -eq 0 ]; then
    echo "Checks passed!"
    gh pr merge -s -d
    break
  elif [ $EXIT_CODE -eq 1 ]; then
    echo "Checks failed!"
    exit 1
  elif [ $EXIT_CODE -eq 8 ]; then
    echo "Checks pending, waiting..."
    sleep 15
  else
    echo "Unknown exit code $EXIT_CODE"
    exit 1
  fi
done
