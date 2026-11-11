---
slug: revenue-metric-v2
title: Move revenue to the metric layer
status: active
repos:
- analytics-dbt
branches:
- feat/revenue-metric-*
updated: '2025-01-15'
next:
- Backfill 2024 with max-active-runs 1
- Get finance sign-off on refund handling
links: []
---
## Goal
One governed revenue definition in the metric layer, replacing three divergent dashboard formulas.

## Context
Finance and growth quote revenue that differs by up to 2%: refunds, FX date and store-local dates are handled differently. The layer must use `created_at` (UTC) and net refunds.

## Progress
- Model `metric_revenue_v2` merged behind a flag
- Reconciled Jan 2025 within 0.05% of the ledger

## Verification evidence
| check | command | result | date |
|---|---|---|---|
| Jan 2025 revenue matches ledger | `dbt test --select metric_revenue_v2` | 12/12 pass | 2025-01-15 |

## Next steps
1. Backfill 2024 (see backfill concurrency fact)
2. Finance sign-off on refund handling
3. Switch dashboards, delete old formulas

## Open questions
- Does finance want FX at order date or settlement date?

## References
