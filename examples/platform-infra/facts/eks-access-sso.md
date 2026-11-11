---
title: Cluster access uses SSO profiles; expired tokens look like connection errors
repos: [infra-live]
tags: [eks, access]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
source: 'example content (invented): replace with your own'
---
`aws sso login --profile prod` then `kubectl --context prod-eks ...`. When the SSO token expires `kubectl` reports `Unable to connect to the server` or `You must be logged in`; it is not a cluster outage.
Retry once after logging in, then escalate. The cluster API is only reachable on the VPN.
