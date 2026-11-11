---
title: Argo CD sync waves order CRDs, operators and apps; do not set waves on apps
repos: [gitops]
tags: [argocd, gitops]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
source: 'example content (invented): replace with your own'
---
CRDs are wave -2, operators -1, namespaces and shared config 0, applications 1+. An app that needs a CRD must be in a later wave than the operator that ships it, otherwise the first sync fails with
`no matches for kind`. Re-syncing fixes the symptom; the permanent fix is the wave annotation. `Prune` is off for the platform project: delete removed resources by hand.
