---
title: Example - deploys go through the gitops repo, never kubectl apply
repos: [example-gitops]
tags: [deploy]
anchors: []
verified: true
verified_at: '2025-01-01'
confidence: medium
scope: team
source: example - delete this file
---
Prod changes are PRs to `example-gitops`; the ruleset requires the `lint` check. Direct `kubectl apply` is reverted by the sync controller.
