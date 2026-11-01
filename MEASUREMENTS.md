# Measurements

All numbers: local Docker (postgres:16), warm cache, synthetic data. Median of 5 runs, `EXPLAIN ANALYZE` Execution Time. Measured 2026-11-01.

## Index `ix_ping_results_endpoint_checked (endpoint_id, checked_at)`

Data: 1,000,000 rows in `ping_results`, 10 endpoints, 100,000 rows each, 133 MB.

| Query | Without index | With index |
|---|---|---|
| Uptime, last 24 h (about 3,450 rows) | 15.8 ms (Parallel Seq Scan) | 0.86 ms (Bitmap Index Scan) |
| Latest 50 pings | 16.6 ms (Parallel Seq Scan) | 0.076 ms (Index Scan Backward) |
| Uptime, last 30 days (100,000 rows, whole endpoint) | 19.7 ms | 17.3 ms |

Reading: the index wins when a query touches a small slice of the table. When the window covers the endpoint's whole history, a scan is just as good.

## How to repeat

1. Create a scratch DB, run `alembic upgrade head` on it.
2. Seed 1 user, 10 endpoints, 100,000 pings each with `generate_series`.
3. Run `EXPLAIN ANALYZE` five times per query. For the "without" case, drop the index inside a transaction and `ROLLBACK`.
