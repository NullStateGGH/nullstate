#!/bin/bash
cd /home/Nullstate-linux-vm/

tail -F /home/Nullstate-linux-vm/.local/share/opencode/log/*.log | while read -r LOG_LINE; do
  TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  SERVICE=$(echo "$LOG_LINE" | grep -oP 'service=\K[^ ]+')
  METRIC=$(echo "$LOG_LINE" | grep -oP '(duration|context_tokens|error|commit_hash)=\K[^ ]+')
  
  if [ ! -z "$SERVICE" ]; then
    # FIXED: Pipe data directly into bq via standard input
    echo "{\"timestamp\": \"$TIMESTAMP\", \"service\": \"$SERVICE\", \"metric_payload\": \"$METRIC\"}" | \
    bq insert personal-workspace-480613:nullstate_telemetry.realtime_logs
  fi

  if [[ $(git status --porcelain) ]]; then
    git add .
    git commit -m "🤖 Auto-Evolutionary Checkpoint: $(date +'%Y-%m-%d %H:%M:%S')"
    COMMIT_HASH=$(git rev-parse HEAD | cut -c1-7)
    
    echo "{\"timestamp\": \"$TIMESTAMP\", \"service\": \"version_control\", \"metric_payload\": \"commit_hash=$COMMIT_HASH\"}" | \
    bq insert personal-workspace-480613:nullstate_telemetry.realtime_logs
  fi
done
