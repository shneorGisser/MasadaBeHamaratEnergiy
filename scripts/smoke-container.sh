#!/usr/bin/env bash
# Smoke test of a running deployment (container, Cloud Run): UI served, a project, a simulation,
# a lab dataset compared with it, a report and its PDF-independent Word export.
# Usage: scripts/smoke-container.sh http://127.0.0.1:8080
set -euo pipefail
B="${1:?base URL}"
j() { python3 -c "import json,sys; print(json.load(sys.stdin)$1)"; }

curl -fsS "$B/" | grep -q '<div id="root">' && echo "UI: served"
PID=$(curl -fsS -X POST "$B/api/projects" -H 'content-type: application/json' \
  -d '{"name":"smoke","experiment_id":"dc_motor"}' | j "['id']")
echo "project: $PID"
SID=$(curl -fsS -X POST "$B/api/projects/$PID/datasets/dc_motor_2025/import" \
  -H 'content-type: application/json' -d '{"study_kind":"load"}' | j "['sets'][0]['id']")
RUN=$(curl -fsS -X POST "$B/api/measurement-sets/$SID/simulate")
RID=$(echo "$RUN" | j "['id']")
STATUS=$(echo "$RUN" | j "['status']")
echo "run: $RID ($STATUS)"
[[ "$STATUS" == success* ]]
MED=$(curl -fsS "$B/api/comparison?run_id=$RID&set_id=$SID" | j "['summary']['median_abs_rel_error']")
echo "median |error| vs the 2025 table: $MED"
python3 -c "import sys; assert float(sys.argv[1]) < 0.05" "$MED"
REP=$(curl -fsS -X POST "$B/api/projects/$PID/reports" -H 'content-type: application/json' \
  -d "{\"title\":\"smoke\",\"sections\":[{\"study_kind\":\"load\",\"run_id\":\"$RID\",\"set_id\":\"$SID\"}]}" | j "['id']")
curl -fsS "$B/api/reports/$REP/docx" -o /tmp/smoke.docx
head -c 2 /tmp/smoke.docx | grep -q PK && echo "report: Word export OK"
curl -fsS "$B/api/projects/$PID/circuits/load/wiring" | j "['steps'][0]['colour_he']" >/dev/null && echo "wiring guide: OK"
echo "SMOKE PASSED"
