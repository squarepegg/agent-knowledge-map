---
title: Database migrations must be backward compatible (expand, then contract)
repos: [shop-api]
tags: [database, deploy]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
source: 'example content (invented): replace with your own'
---
During a canary the old and new code run against the same database, so a migration that renames or drops a column breaks the old code. Ship in three deploys: add the new column (expand),
dual-write and backfill, then remove the old column in a later release (contract). CI rejects migrations containing `DROP COLUMN` or `RENAME` unless the PR has the `contract` label.
