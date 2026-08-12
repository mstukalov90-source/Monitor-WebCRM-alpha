#!/usr/bin/env bash
# Post-nightly ETL compare + optional protect apply.
# Usage:
#   ./scripts/etl_safety_post_etl.sh              # compare only
#   ./scripts/etl_safety_post_etl.sh --apply-pin  # compare then apply pin if green
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${HOST:-172.21.198.219}"
NOTES="$ROOT/tmp/kosolapov_etl_safety_20260812/notes"
APPLY_PIN=0
for arg in "$@"; do
  case "$arg" in
    --apply-pin) APPLY_PIN=1 ;;
  esac
done

mkdir -p "$NOTES"
cd "$ROOT"

echo "=== Collector log scan (task_key / CRM sync) ==="
ssh -o BatchMode=yes -o ConnectTimeout=30 "root@${HOST}" \
  'docker logs monitor-collector --since 18h 2>&1' \
  | grep -Ei 'data_mos|task_key preservation|CRM task sync|crm_task_sync|ERROR|RuntimeError' \
  | tee "$NOTES/collector_post_etl.log" \
  | tail -80 || true

if grep -Ei 'task_key preservation failed|CRM task sync gap' "$NOTES/collector_post_etl.log" >/dev/null 2>&1; then
  echo "FAIL: collector reported task_key / CRM sync problems" >&2
  exit 1
fi

echo "=== Assert post vs pre ==="
python3 "$ROOT/scripts/etl_safety_assert.py" --host "$HOST" --mode post \
  --baseline "$NOTES/baseline_pre_etl.json" \
  --out-dir "$NOTES"

if [[ "$APPLY_PIN" -eq 1 ]]; then
  echo "=== Apply etl_protect pin ==="
  bash "$ROOT/scripts/etl_safety_apply_protect.sh" "$HOST"
fi

echo "POST_ETL_OK"
