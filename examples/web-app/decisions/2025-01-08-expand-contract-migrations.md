# Enforce expand/contract migrations in CI
date: 2025-01-08
status: accepted
## Context
A rename migration broke the old pods during a canary and caused a 6-minute incident.
## Options considered
| option | evidence | falsifier | reversible? |
|---|---|---|---|
| convention only | incident happened anyway | none needed | yes |
| CI rule on DROP/RENAME | would have blocked the incident PR | blocks legitimate contract PRs without the label | yes |
## Decision
CI blocks DROP COLUMN and RENAME unless the PR has the `contract` label.
## Consequences
Contract changes need a second deploy; reviewers check the label.
