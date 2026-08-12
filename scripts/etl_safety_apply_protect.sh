#!/usr/bin/env bash
# Apply sql/36_crm_etl_protect.sql + seed 81 keys + smoke RAISE on prod.
# Usage: ./scripts/etl_safety_apply_protect.sh [HOST]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${1:-172.21.198.219}"
PROTECT_JSON="${PROTECT_JSON:-$ROOT/tmp/kosolapov_etl_safety_20260812/protect_81.json}"
SQL_MIG="$ROOT/sql/36_crm_etl_protect.sql"
NOTES="$ROOT/tmp/kosolapov_etl_safety_20260812/notes"
mkdir -p "$NOTES"

psql_prod() {
  ssh -o BatchMode=yes -o ConnectTimeout=30 "root@${HOST}" \
    "docker exec -i monitor-db psql -U monitor -d monitor -v ON_ERROR_STOP=1"
}

echo "=== Apply 36_crm_etl_protect.sql on ${HOST} ==="
psql_prod < "$SQL_MIG"

echo "=== Seed etl_protect from ${PROTECT_JSON} ==="
python3 - <<PY | psql_prod
import json
from pathlib import Path
data = json.loads(Path("$PROTECT_JSON").read_text())
keys = data["task_keys"]
reason = data.get("reason", "kosolapov_transfer_20260812")
print("BEGIN;")
print("DELETE FROM crm.etl_protect WHERE reason = %s;" % ("'" + reason.replace("'", "''") + "'"))
for k in keys:
    print(
        "INSERT INTO crm.etl_protect (object_key, object_kind, reason) "
        f"VALUES ('{k}'::uuid, 'task', '{reason}') "
        "ON CONFLICT (object_key) DO UPDATE SET reason = EXCLUDED.reason, object_kind = 'task';"
    )
print("SELECT COUNT(*) AS protect_count FROM crm.etl_protect WHERE reason = '%s';" % reason)
print("COMMIT;")
PY

echo "=== Record migration if webcrm.schema_migrations exists ==="
psql_prod <<'SQL'
INSERT INTO webcrm.schema_migrations (filename)
VALUES ('36_crm_etl_protect.sql')
ON CONFLICT DO NOTHING;
SQL

SMOKE_KEY="$(python3 -c "import json; print(json.load(open('$PROTECT_JSON'))['task_keys'][0])")"
echo "=== Smoke RAISE in transaction for key ${SMOKE_KEY} ==="
set +e
SMOKE_OUT=$(psql_prod <<SQL 2>&1
BEGIN;
DELETE FROM crm.tasks WHERE key = '${SMOKE_KEY}'::uuid;
ROLLBACK;
SQL
)
SMOKE_RC=$?
set -e
echo "$SMOKE_OUT" | tee "$NOTES/smoke_protect.txt"
if echo "$SMOKE_OUT" | grep -q "etl_protect: DELETE blocked"; then
  echo "SMOKE_OK: DELETE blocked as expected"
else
  echo "SMOKE_FAIL: expected etl_protect DELETE block" >&2
  exit 1
fi

echo "=== Non-protect sanity: count tasks ==="
psql_prod <<'SQL'
SELECT COUNT(*) AS tasks_total FROM crm.tasks;
SELECT COUNT(*) AS etl_protect_n FROM crm.etl_protect;
SQL

echo "APPLY_PROTECT_OK"
