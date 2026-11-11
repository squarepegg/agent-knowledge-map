---
title: New feature flags default to off in production and are removed within 30 days
repos: [shop-web]
tags: [flags, toggles, feature-toggle, cleanup, old-flags]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
source: 'example content (invented): replace with your own'
---
Create flags with `default: false`; turn on per environment from the flag console. After full rollout delete the flag and the dead branch within 30 days: stale flags are the main source of untested code paths.
The `flag-audit` job comments on PRs when a flag is older than 30 days at 100%.
