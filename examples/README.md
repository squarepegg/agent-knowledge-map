# Example brains

Four small, invented brains showing what good content looks like for different teams. None of it is real: replace it with your own.

| Example | For | Shows |
|---|---|---|
| `data-team` | analytics engineering | warehouse/dbt/Airflow gotchas, data freshness SLAs, PII handling, a metric-layer workstream |
| `web-app` | product engineering | canary deploys, expand/contract migrations, flags, flaky tests, error budgets, a checkout workstream |
| `platform-infra` | platform / SRE | Terraform via Atlantis, SSO cluster access, Argo CD sync waves, node drains, IRSA, severities, an EKS upgrade workstream |
| `solo-dev` | one person | dotfiles bootstrap, secrets via a CLI, git identities, per-project Python, backups, a site rebuild |

Use one: `python3 scripts/brain.py init --example web-app` (add `--force` to overwrite files you changed; add `--org "My Co"` to rename). It replaces the placeholder content, copies the example's facts, workstream, decision, glossary, capabilities and probes, and appends its eval questions so `scripts/eval_run.py` checks them. Dates in the copied facts and workstream are stamped with today, so a fresh example lints clean; replace the content with yours before relying on it. Every example is tested: complete, lint-clean, passes its own evals, and its evals fail without it.
