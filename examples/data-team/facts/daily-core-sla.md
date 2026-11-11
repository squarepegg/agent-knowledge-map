---
title: daily_core must finish by 07:00 UTC; the exec dashboard refreshes at 07:30
repos: [analytics-airflow]
tags: [sla, pipelines, dashboard, stale, morning, freshness]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
source: 'example content (invented): replace with your own'
---
The executive dashboard extract starts at 07:30 UTC and reads whatever `daily_core` has produced. If the DAG is not green at 07:00 the on-call analytics engineer is paged and posts
in the data-status channel. Common causes: late upstream export (check the `source_freshness` task), warehouse queue (see backfill concurrency), a failed incremental model.
