---
title: IRSA roles fail with AccessDenied when the trust policy subject does not match the ServiceAccount
repos: [infra-live]
tags: [iam, eks]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
source: 'example content (invented): replace with your own'
---
The role's trust policy must have `system:serviceaccount:<namespace>:<name>` exactly as the pod's ServiceAccount, and the SA needs the `eks.amazonaws.com/role-arn` annotation. A renamed namespace
silently breaks it: pods start but every AWS call returns `AccessDenied` / `WebIdentityErr`. Check with `aws sts get-caller-identity` inside the pod.
