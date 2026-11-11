---
title: Terraform changes apply only through Atlantis PR comments
repos: [infra-live]
tags: [terraform, change]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
absolutes_ok: true
source: 'example content (invented): replace with your own'
---
Open a PR, wait for `atlantis plan`, review the plan, get approval, then comment `atlantis apply`. Never `terraform apply` locally against prod: state is locked by Atlantis and a local apply
creates drift the next plan will try to revert. If a lock is stuck use `atlantis unlock` on the PR, not DynamoDB edits.
