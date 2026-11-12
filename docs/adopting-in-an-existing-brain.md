# Adopting agent-knowledge-map in an existing brain

For teams that already run a home-grown brain (their own facts, scripts and extension) and want to share this core instead of maintaining copies.

## What to share and what to keep
| Share (identical everywhere) | Keep local (your content) |
|---|---|
| `scripts/` core: `brain.py`, `compact.py`, `build_primer.py`, `lint_facts.py`, `tour_lint.py`, `eval_run.py`, `mutation_check.py`, `auto_mutate.py`, `_guard.py`, `maintain.py`, `check_freshness.py`, `golden_skills.py`, `harness_check.py`, `session_start.py`, `capture_hook.py`, `digest_sessions.py` | `facts/`, `workstreams/`, `decisions/`, `glossary.yaml`, `capabilities.yaml`, `style.md`, `brain.config.yaml`, `probes.yaml`, `freshness.yaml`, `maintenance.yaml` |
| `skills/brain/`, `templates/`, `tests/` for the shared scripts | your topic skills, your catalogs and sync scripts (with their own tests and mutants) |

## Steps (do them in a branch; the brain keeps working at every step)
1. **Inventory.** Diff your scripts against `scripts/` here. Anything you changed locally that is generally useful goes upstream as a PR first; anything company-specific stays in your repo.
2. **Env names.** This repo reads `BRAIN_DIR` and `BRAIN_REPOS_ROOT`. If yours differ, export both in your shell profile; keep the old name working until every caller is migrated (`BRAIN_DIR="${OLD_BRAIN_DIR:-...}"`).
3. **Vendor the core.** `git subtree add --prefix=vendor/agent-knowledge-map <url> main --squash` (or a submodule), then replace your copies in `scripts/` with symlinks into `vendor/agent-knowledge-map/scripts/`. Pull updates with `git subtree pull`.
4. **Primer.** Move your hardcoded router rows into `brain.config.yaml` (`routes:`, `access:`). Run `brain.py primer` and diff the result against your old primer; the wording will differ but the same entries should be present.
5. **Lint.** Run `lint_facts.py`. Expect new soft findings (`SOURCE`, `ABSOLUTE`, `OLD`); they are real. Only `--strict` hard findings (`PARSE`, `SECRET`, `FIELD`, `REQ`) block.
6. **Probes.** Port your environment probes to `probes.yaml` (id, label, cmd, okWhen, fix). `capabilities.yaml` `requires:` may name any id declared there.
7. **Scheduling.** Replace the shell nightly with `maintain.py` + `maintenance.yaml`; keep your company syncs as extra steps (each behind `_guard.write_json_guarded`, each with a `freshness.yaml` entry).
8. **Gate.** Run `mutation_check.py` for every local script. Local scripts without mutants are debt: list them in `tests/mutants/GRANDFATHERED.txt` and let `auto_mutate.py --check` ratchet them.
9. **Cut over.** Only after the new primer, lint and evals match the old behaviour: switch the agent config to the new `PRIMER.md`, then delete the old copies.

## Evidence before you switch
- `eval_run.py` passes on your own `evals/questions.yaml` (port your old questions; `run: {search: ...}` or `run: {cmd: [...]}`).
- `lint_facts.py --strict` exits 0.
- Your agent still finds what it found before: run `agentic_eval.py` once against the old and once against the new brain (`AGENTIC_YAML` accepts the old question file) and compare scores.
