#!/usr/bin/env bash
# Server-local post-ETL job (runs ON .219). Applies pin if assert+compare green.
set -euo pipefail

ROOT="${ROOT:-/opt/monitor/etl_safety}"
NOTES="$ROOT/notes"
PROTECT="$ROOT/protect_81.json"
MIG="$ROOT/36_crm_etl_protect.sql"
export PATH="/usr/bin:/bin:/usr/local/bin:$PATH"

mkdir -p "$NOTES"
cd "$ROOT"

echo "=== $(date -Is) post-ETL safety ===" | tee -a "$NOTES/post_etl_run.log"

echo "=== Collector log scan ===" | tee -a "$NOTES/post_etl_run.log"
docker logs monitor-collector --since 18h 2>&1 \
  | grep -Ei 'data_mos|task_key preservation|CRM task sync|crm_task_sync|ERROR|RuntimeError' \
  | tee "$NOTES/collector_post_etl.log" \
  | tail -80 | tee -a "$NOTES/post_etl_run.log" || true

if grep -Ei 'task_key preservation failed|CRM task sync gap' "$NOTES/collector_post_etl.log" >/dev/null 2>&1; then
  echo "FAIL: collector task_key/CRM sync problems" | tee -a "$NOTES/post_etl_run.log"
  exit 1
fi

python3 "$ROOT/etl_safety_assert.py" --local --mode post \
  --protect "$PROTECT" \
  --baseline "$NOTES/baseline_pre_etl.json" \
  --out-dir "$NOTES" | tee -a "$NOTES/post_etl_run.log"

# Seed + migration only if compare ok
python3 - <<'PY' | tee -a "$NOTES/post_etl_run.log"
import json, sys
from pathlib import Path
notes = Path("/opt/monitor/etl_safety/notes")
post = json.loads((notes/"baseline_post_etl.json").read_text())
cmp = json.loads((notes/"compare_pre_post.json").read_text())
if not post.get("ok") or not cmp.get("ok"):
    print("SKIP_PIN: assert/compare not green", post.get("failed"), cmp.get("issues"))
    sys.exit(2)
print("COMPARE_GREEN")
PY

echo "=== Apply protect migration + seed ===" | tee -a "$NOTES/post_etl_run.log"
docker exec -i monitor-db psql -U monitor -d monitor -v ON_ERROR_STOP=1 < "$MIG"

python3 - <<'PY' | docker exec -i monitor-db psql -U monitor -d monitor -v ON_ERROR_STOP=1
import json
from pathlib import Path
data = json.loads(Path("/opt/monitor/etl_safety/protect_81.json").read_text())
reason = data.get("reason", "kosolapov_transfer_20260812")
print("BEGIN;")
print(f"DELETE FROM crm.etl_protect WHERE reason = '{reason}';")
for k in data["task_keys"]:
    print(
        "INSERT INTO crm.etl_protect (object_key, object_kind, reason) "
        f"VALUES ('{k}'::uuid, 'task', '{reason}') "
        "ON CONFLICT (object_key) DO UPDATE SET reason = EXCLUDED.reason;"
    )
print(f"SELECT COUNT(*) AS protect_count FROM crm.etl_protect WHERE reason = '{reason}';")
print("INSERT INTO webcrm.schema_migrations (filename) VALUES ('36_crm_etl_protect.sql') ON CONFLICT DO NOTHING;")
print("COMMIT;")
PY

SMOKE_KEY=$(python3 -c "import json; print(json.load(open('/opt/monitor/etl_safety/protect_81.json'))['task_keys'][0])")
set +e
SMOKE_OUT=$(docker exec -i monitor-db psql -U monitor -d monitor -v ON_ERROR_STOP=1 <<SQL 2>&1
BEGIN;
DELETE FROM crm.tasks WHERE key = '${SMOKE_KEY}'::uuid;
ROLLBACK;
SQL
)
set -e
echo "$SMOKE_OUT" | tee "$NOTES/smoke_protect.txt" | tee -a "$NOTES/post_etl_run.log"
echo "$SMOKE_OUT" | grep -q "etl_protect: DELETE blocked"
echo "APPLY_PROTECT_OK" | tee -a "$NOTES/post_etl_run.log" | tee "$NOTES/APPLY_PROTECT_OK"
