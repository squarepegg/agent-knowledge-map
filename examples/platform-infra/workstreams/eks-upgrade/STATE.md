---
slug: eks-upgrade
title: Upgrade EKS 1.30 to 1.31
status: active
repos:
- infra-live
- gitops
branches:
- feat/eks-1-31*
updated: '2025-01-15'
next:
- Roll staging node groups
- Check deprecated APIs in the gitops repo
links: []
---
## Goal
Upgrade production to Kubernetes 1.31 with no customer impact and no unplanned downtime.

## Context
Staging control plane is on 1.31; node groups still on 1.30 AMIs. Add-ons (CoreDNS, kube-proxy, VPC CNI) have compatible versions listed in the upgrade checklist.

## Progress
- Staging control plane upgraded
- Deprecated API scan: 2 findings fixed

## Verification evidence
| check | command | result | date |
|---|---|---|---|
| no deprecated APIs remain | `pluto detect-files -d gitops/` | 0 findings | 2025-01-15 |

## Next steps
1. Roll staging nodes (drain first)
2. Soak a week
3. Prod control plane then nodes in off-peak window

## Open questions
- Do we freeze deploys for the node roll window?

## References
