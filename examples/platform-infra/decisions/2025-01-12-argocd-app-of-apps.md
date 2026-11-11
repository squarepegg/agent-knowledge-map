# Use app-of-apps for platform and workloads in Argo CD
date: 2025-01-12
status: accepted
## Context
Applications were registered by hand, so a rebuilt cluster came back empty.
## Options considered
| option | evidence | falsifier | reversible? |
|---|---|---|---|
| hand-registered apps | works until a rebuild | cluster rebuild test | yes |
| app-of-apps root per cluster | staging rebuilt from git in 25 minutes | sync-wave ordering fails | yes |
## Decision
One root Application per cluster generates the rest; sync waves order CRDs and operators.
## Consequences
New apps are PRs to the gitops repo; no manual Argo registration.
