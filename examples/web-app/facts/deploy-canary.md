---
title: Every deploy canaries at 10% for 15 minutes before full rollout
repos: [shop-web, shop-api]
tags: [deploy, release, rollout, rollback, production, outage]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
source: 'example content (invented): replace with your own'
---
Merging to main starts the `deploy` workflow: build, run migrations, release to 10% of traffic, hold 15 minutes watching error rate and p95 latency, then roll to 100%.
Auto-rollback triggers when the 5xx rate is more than 2x baseline. To abort manually: `gh workflow run rollback.yml -f version=<previous>`. Do not deploy during the Friday freeze window (after 14:00).
