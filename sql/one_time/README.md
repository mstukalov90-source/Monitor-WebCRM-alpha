# One-time SQL migrations

These scripts are **not** run automatically by `deploy/deploy.sh`.
They contain destructive `DELETE FROM crm.tasks` operations and must be
executed manually after review.

See [docs/webcrm_tasks_deletion_investigation.md](../docs/webcrm_tasks_deletion_investigation.md)
for incident context and acceptance criteria.

## Files

| File | Purpose |
|------|---------|
| `17_tasks_business_id_unique.sql` | Deduplicate crm.tasks by business-id columns |
| `18_earthwork_restore_point_tasks.sql` | Remove legacy earthwork order tasks |
| `20_oati_scoped_geometry_tasks.sql` | Remove legacy OATI order tasks |
| `21_localwork_avr_scoped_geometry_tasks.sql` | Remove legacy localwork/AVR order tasks |
| `28_cleanup_link_orphan_tasks.sql` | Remove link-orphan tasks (excludes MONITOR ETL) |

## How to run

```bash
# From /opt/monitor/webcrm on the server (or with DB env from backend/.env):

# Non-destructive preview for 28 (orphan count printed, abort if >100):
./scripts/run_one_time_migration.sh sql/one_time/28_cleanup_link_orphan_tasks.sql

# Destructive run (requires explicit flag):
ALLOW_DESTRUCTIVE_MIGRATION=1 ./scripts/run_one_time_migration.sh sql/one_time/28_cleanup_link_orphan_tasks.sql
```

Before running `28_cleanup` on production:

1. Run MONITOR backfill: `backfill_data_mos_crm_tasks`
2. Verify gap = 0: `scripts/crm_task_sync_audit.py` (on MONITOR)
3. Review dry-run metrics printed by the script
4. Set `ALLOW_DESTRUCTIVE_MIGRATION=1` only if count is acceptable

Applied migrations are recorded in `webcrm.schema_migrations` and will not
run again.
