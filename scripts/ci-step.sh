#!/usr/bin/env bash
# Run one CI stage; on failure publish the tail of its output as a GitHub error annotation,
# so the reason is readable from the checks API even where raw logs are not accessible.
set -uo pipefail
name="$1"
cmd="$2"
log="$(mktemp)"
bash -c "$cmd" 2>&1 | tee "$log"
status=${PIPESTATUS[0]}
if [ "$status" -ne 0 ]; then
  tail -n 60 "$log" | sed -e 's/%/%25/g' | awk 'BEGIN{ORS="%0A"} {print}' > "$log.tail"
  echo "::error title=${name} failed (exit ${status})::$(cat "$log.tail")"
fi
exit "$status"
