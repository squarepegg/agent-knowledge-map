---
title: Airflow backfills must run with max_active_runs=1 or they exhaust warehouse slots
repos: [analytics-airflow]
tags: [airflow, pipelines]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
source: 'example content (invented): replace with your own'
---
`airflow dags backfill -s <start> -e <end> --reset-dagruns daily_core` with the default concurrency starts every day in parallel and queues interactive queries for an hour.
Run `airflow dags backfill ... --max-active-runs 1` (or set it on the DAG for the backfill window). Check slot usage in the warehouse console before starting.
