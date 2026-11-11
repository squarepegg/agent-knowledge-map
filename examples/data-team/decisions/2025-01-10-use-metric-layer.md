# Use a metric layer for business metrics
date: 2025-01-10
status: accepted
## Context
Three dashboards compute revenue differently; nobody can say which is right.
## Options considered
| option | evidence | falsifier | reversible? |
|---|---|---|---|
| keep per-dashboard SQL | works today | numbers keep diverging | yes |
| metric layer in dbt | reconciled Jan within 0.05% in a spike | cannot express refunds | yes (views) |
## Decision
Define metrics once in the metric layer; dashboards read only from it.
## Consequences
New metrics need a PR with tests; ad-hoc SQL stays possible on raw tables.
