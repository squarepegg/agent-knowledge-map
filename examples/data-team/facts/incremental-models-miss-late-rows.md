---
title: Incremental dbt models do not pick up rows that arrive late
repos: [analytics-dbt]
tags: [dbt, warehouse]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
absolutes_ok: true
source: 'example content (invented): replace with your own'
---
Incremental models filter on `loaded_at > max(loaded_at)`, so rows backfilled with an old `loaded_at` are skipped. Fix for one model: `dbt run --select <model> --full-refresh`.
Fix in code: set the `lookback_days` var (default 3) so each run re-reads the last N days. Never full-refresh `fct_events` during business hours: it takes ~40 minutes and locks dashboards.
