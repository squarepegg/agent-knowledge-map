# agent-knowledge-map

A map of everything your coding agents know, checked against the code and scored by evals, so answers stay structured and improve every week.

A git-versioned, plain-text **memory for coding agents**. It persists what an agent learns across sessions and repos: verified facts, in-flight work state, decisions, glossary, capabilities. A small generated *primer* routes every new session to it.

No framework, no daemon, no plugin: Markdown + YAML + a few hundred lines of Python (needs `pyyaml`). Works with any agent that reads an instructions file and can run a shell command (Claude Code, pi, Codex, Cursor, …).

## Why
- Agents re-discover the same gotchas every session. Notes fix that, but unchecked notes rot. This brain **lints for staleness**: facts carry `anchors` (`repo@path`); lint flags a fact when the anchored code changed after `verified_at`.
- The always-loaded context is a **router** (primer), not an encyclopedia; detail lives in facts and topic skills found by search.
- State lives in `workstreams/<slug>/STATE.md`, with evidence required before anything counts as "done".

## Quick start
```bash
git clone https://github.com/<you>/agent-knowledge-map ~/.agents/brain      # or anywhere; set BRAIN_DIR
pip install pyyaml
export BRAIN_DIR=~/.agents/brain
python3 $BRAIN_DIR/scripts/brain.py init --org "Acme Co" --no-examples --claude
```
`init` sets your org, drops the examples, builds `PRIMER.md` and (with `--claude`) wires Claude Code: imports the primer, links the skill and installs the SessionStart / Stop / UserPromptSubmit hooks. It is idempotent and prints every change. Then edit `brain.config.yaml` (routes, access notes) and `style.md`.

Start from an example instead of a blank template: `init --example data-team|web-app|platform-infra|solo-dev` (see [examples/README.md](examples/README.md)).

Other agents: import or symlink `PRIMER.md` as the global instructions file and link `skills/*` into the agent's skills directory (see [docs/integrations.md](docs/integrations.md)). As a Claude Code plugin (skill + hooks only; it needs a brain directory): `/plugin marketplace add <you>/agent-knowledge-map`.

Then tell the agent (in the primer's protocol) to: search before rediscovering, `note` learnings, update `STATE.md` at milestones. The `brain` skill holds the full protocol.

## CLI
```
brain.py search <keywords>          file-level ranked search across facts, workstreams, decisions, skills, docs, glossary, inbox
brain.py note <kind> <title> [body] append a learning to inbox/ (refuses secrets)
brain.py ws new|list                workstreams
brain.py decision <slug> [title]    append-only decision record
brain.py inbox                      what needs compaction
brain.py compact [--write|--archive] deterministic compaction plan; drafts unverified facts/decisions; flags duplicates
brain.py init [--org N] [--claude]  one-command, idempotent setup
brain.py primer                     regenerate PRIMER.md
brain.py lint [--strict]            staleness, missing fields, secrets, bad skills/tours
```
More (hooks, scheduling, readiness checks): [docs/integrations.md](docs/integrations.md); search quality is measured in [docs/benchmarks.md](docs/benchmarks.md).

## Layout
| Path | Role |
|---|---|
| `brain.config.yaml` | org name, repos root, primer routes, access notes |
| `style.md` | working-style rules injected into the primer |
| `glossary.yaml` / `capabilities.yaml` | one-line terms and "to do X use Y" entries (`core: true` → in primer) |
| `facts/` | verified gotchas with frontmatter (anchors, verified_at, confidence, scope) |
| `workstreams/<slug>/STATE.md` (+ optional `TOUR.md`) | in-flight work |
| `decisions/` | append-only log |
| `inbox/` | per-session raw notes (git-ignored), compacted into the above |
| `skills/brain/` | the protocol, as an agent skill |
| `templates/` | fact / STATE / decision skeletons |
| `evals/` | `questions.yaml` (deterministic), `agentic.yaml` (model-graded), `negative-results.md` |
| `tests/` + `tests/mutants/` | unit tests, hand-written mutants, grandfather list, legacy mutation scores |
| `probes.yaml`, `freshness.yaml`, `maintenance.yaml` | environment probes, catalog age budgets, scheduled upkeep steps |
| `scripts/` | core: `brain.py`, `init_brain.py`, `compact.py`, `build_primer.py`, `lint_facts.py`, `tour_lint.py`; session: `session_start.py`, `capture_hook.py`, `digest_sessions.py`, `mine_sessions.py`; upkeep: `maintain.py`, `check_freshness.py`, `_guard.py`; trust: `eval_run.py`, `recall_eval.py`, `agentic_eval.py`, `agentic_ab.py`, `mutation_check.py`, `auto_mutate.py`, `golden_skills.py`, `harness_check.py`; verification: `apply_verdicts.py`, `apply_skill_edits.py` |
| `examples/` | four invented, tested example brains (data team, web app, platform/infra, solo developer) |
| `docs/integrations.md` | hook, schedule and agent wiring; what is deliberately left out |

## Trust: evals and mutation testing
| Layer | Command | Runs |
|---|---|---|
| Unit tests | `python -m unittest discover -s tests` | CI every push |
| Deterministic evals (question → lookup → expected substrings) | `python scripts/eval_run.py` | CI every push |
| Retrieval recall (symptom query → the right file, recall@1/@5) | `python scripts/recall_eval.py` | CI every push |
| Hand-written mutation gate (every mutant must be killed) | `python scripts/mutation_check.py tests/mutants/<script>.yaml` | CI every push |
| Auto-mutation ratchet for scripts without hand-written mutants | `python scripts/auto_mutate.py --check` | weekly CI |
| Agentic eval (fresh agent answers real questions) | `AGENTIC_CMD='claude -p {prompt}' python scripts/agentic_eval.py` | manual/weekly; costs tokens |
| Does the brain help? Same questions with vs without an example brain | `python scripts/agentic_ab.py web-app` | on demand; costs tokens |
| Shrink guard for catalog writers | `scripts/_guard.py` | in your sync scripts |
| Skill goldens (frontmatter, pinned text, size) | `python scripts/golden_skills.py` | on demand / `--changed` in PRs |
| Everything scheduled | `python scripts/maintain.py` | daily (cron / CI) |

A new script ships only with tests, a mutants file (all killed) and an eval question; `tests/test_definition_of_done.py` enforces it.

## Extending
Add domain knowledge as `skills/<topic>/SKILL.md` and `facts/`; add your own catalogs/sync scripts under `scripts/` with tests; run `brain.py lint` in CI (see `.github/workflows/ci.yml`). Promote personal → team knowledge by rewriting generically (protocol §6 in the skill).

## Safety
Never store secrets or personal data. `note` and `lint` reject obvious secret patterns, but that is a backstop, not a guarantee. Keep a personal brain in a private repo.

## Tests
`python -m unittest discover -s tests`

See [CONTRIBUTING.md](CONTRIBUTING.md), [CHANGELOG.md](CHANGELOG.md) and [docs/adopting-in-an-existing-brain.md](docs/adopting-in-an-existing-brain.md).

License: MIT

## See also
Companion repo: [agent-toolkit](https://github.com/squarepegg/agent-toolkit): the agent skills (adversarial SDLC, deterministic simulation testing, evidence-gated decisions) I use alongside it.
