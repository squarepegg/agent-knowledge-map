---
name: brain
description: Use when starting or resuming a workstream, saving learnings, updating workstream STATE, compacting the brain inbox, checking stale facts (lint), maintaining scoped project vocabulary, recording decisions, creating topic skills, or promoting personal knowledge to a shared team brain.
---

# Brain

A git-versioned, plain-text knowledge base that persists across agent sessions and repos. Root = `$BRAIN_DIR` (default `~/.agents/brain`; call it `$B`). CLI: `python3 $B/scripts/brain.py` (works from any agent; no plugin required).

| Path | Role |
|---|---|
| `brain.config.yaml`, `style.md`, `glossary.yaml`, `capabilities.yaml` | Sources of truth. `build_primer.py` → `PRIMER.md`, the small router loaded every session |
| `facts/*.md` | Verified gotchas/commands. Frontmatter: title, repos, tags, anchors, verified_at, confidence, scope, source |
| `workstreams/<slug>/STATE.md` | Live state per piece of in-flight work (replaces HANDOFF files) |
| `decisions/YYYY-MM-DD-<slug>.md` | Append-only; supersede with a new file, never edit |
| `inbox/<date>-<session>.md` | Per-session append-only notes; processed → `inbox/processed/` |
| `skills/<topic>/SKILL.md` | Deep knowledge for one system, once a topic outgrows facts |
| `scripts/clash.py` | Opposite "use/never use `X`" directives across facts and skills (lint `CLASH`) |
| `scripts/guard_hook.py` | Opt-in PreToolUse policy; `replay` tests it on past sessions first |
| `scripts/lint_facts.py` | Flags facts whose anchors changed since `verified_at`, old/unverified facts, stale workstreams, secrets |

**Never write secrets, tokens, personal data or credentials into any brain file.** Prefer `anchors` (`repo@path-glob`) over copying code.

## 1. Session protocol
1. Read `PRIMER.md` (imported by your agent config) and the output of `scripts/session_start.py` (probes, matching workstreams, repo facts) when a hook provides it.
2. If a workstream matches the repo/branch/task, read its `STATE.md` fully before working. New work → `brain.py ws new <slug>`.
3. `brain.py search <keywords>` before rediscovering commands, endpoints, gotchas, terms.
4. At milestones and session end update `STATE.md`: `status`, `updated`, `next`, `## Progress`. No `HANDOFF-*.md` files.
5. `brain.py note <kind> "<title>" "<body>"` for each durable learning as it happens: one concise item with the fix/command.
6. Check a capability's `requires:` (vpn, auth, tool) before relying on it; say so if missing.

### STATE.md
Frontmatter: `slug, title, status: active|blocked|paused|done, repos, branches (globs), updated, next [..], links`.
Sections: Goal, Context, Progress, Verification evidence, Next steps, Open questions, References.
A Progress item is "done" only if a Verification-evidence row (`check | command | result | date`) backs it. Never reword unfinished items to hide them; move them to Next steps. Keep it current-state, not a log.

After running the check, complete with `brain.py ws complete <slug> --check <name> --command <command> --result <observed-result>`.
It records a dated completion attestation and clears `next`; it does not run the check or prove the result. New workstreams use `record_version: 1`; strict lint checks completion evidence after manual edits too. For legacy brains, enable `require_evidence: true` in `brain.config.yaml` after adding existing completion evidence.

Use `brain.py context "<task>" --budget 8000 --cwd <repo>` for a bounded context bundle. The budget is UTF-8 bytes (minimum 128), including all output; entries are whole and omissions counted. `[verified]` means explicit recorded verification within 90 days, `[stale]` means older, and other material is `[unverified]`. Anchor freshness is unchecked here: use lint. Read omitted STATE.md files directly when needed.

## 2. Inbox compaction
Starting from an example (`init --example web-app`, see `examples/README.md`) gives realistic facts, a workstream and tested eval questions to replace with your own. Setup in one command: `brain.py init --org "Acme" --claude` (config, primer, Claude Code import/skills/hooks; idempotent). Capture is automatic with the hooks it installs: `capture_hook.py stop` asks once, after real work, for learnings to be recorded; `capture_hook.py prompt` stores user corrections in the inbox.
`mine_sessions.py` (after `digest_sessions.py`) proposes inbox entries from recurring errors and user corrections across past sessions. `brain.py compact` prints a deterministic plan (where each item goes, probable duplicates); `--write` drafts unverified facts/decisions, `--archive` moves handled files to `inbox/processed/`. Drafts still need the verification below. `--group` annotates same-problem items (off: it lowered a model's grouping F1 in an A/B).
1. `brain.py inbox` lists unprocessed files. Read each.
2. Classify every item:
   - gotcha/learning → `facts/<slug>.md` (template: `templates/fact.md`)
   - capability (new tool/endpoint/access path) → `capabilities.yaml`
   - term/system/env name → `glossary.yaml`
   - workstream progress → that `STATE.md`
   - decision → `brain.py decision <slug>`. Fill `Predicted outcome` first; append `Observed` lines later.
   - `correction` (the user pushed back) → the user is the authority. Search for the rejected claim; if a fact/skill states it, FIX that file (`verify_by: user-confirmed <date>`). Never re-verify a correction against older data and override it. Durable ones also become a "When trigger → do action" row in a `facts/user-instincts.md` (tag `instincts`); drop one-offs.
3. Dedupe with `brain.py search`; merge into the existing entry and bump `verified_at` rather than appending duplicates.
4. Verify cheaply before saving (run the command, grep the anchor). Model-dependent: `evaluated_on:`. Unverified → `verified: false`, `recorded_at`, `confidence: low`.
   After observing the evidence, `brain.py fact verify <slug> --source "<provenance>"` records verification date and provenance together, preserving the claim. It attests your observation; it does not establish truth.
5. Formats: capability `id, enables, requires, how, skill?, examples, gotchas?`; glossary `term, kind, one_liner (<=140 chars), repos, skill?, core?`; fact body 2-10 lines incl. fix/command.
6. `mv` handled files to `inbox/processed/`. Run `brain.py primer` and `brain.py lint`; fix errors.
7. Keep the PRIMER small: one-line glossary/capability entries only; detail goes in facts or a topic skill.
8. Tell the user: counts added/merged/discarded, files touched, lint result.

## 3. Staleness
Run `brain.py lint`. For each flagged fact re-verify against the anchored code (`git log` on the anchor) or the live system. Still true → set `verified_at` to today. Changed → rewrite and bump. Wrong → delete the file and its references. Facts with `verified: false` are leads, not truth. Re-run until clean.

## 4. Tours (optional, for long high-stakes workstreams)
`workstreams/<slug>/TOUR.md` is a curated path Need → Decision → Design → Code → Test → Risk → Question; each waypoint has a one-line *why* and a content-hashed anchor. `STATE.md` = status, `TOUR.md` = why. The human authors, the agent audits: `scripts/tour_lint.py <TOUR.md>` (check), `--pin` (owner, after re-reading), `--review` (prints diffs for stale waypoints; edits nothing), `--backtest`. Prefer `#h:<heading>` anchors. Never silently fix a stale waypoint.

## 5. Topic skills
When a topic accumulates >~8 facts or is needed repeatedly, create `skills/<topic>/SKILL.md` (frontmatter `name` = dir, trigger-rich `description` ≤1024 chars; terse imperative body). Move detail out of facts, set `skill:` on related glossary/capability entries, rebuild the primer. Symlink `skills/*` into your agent's skills dir.

### Project extension contracts
When a recurring task requires rediscovering design choices, capture its supported extension point as a fact using `templates/extension-contract.md` (`kind: extension-contract`). Record **need, use, guarantees, boundary, enforcement, example, choices_removed, change_when**. Reference one canonical implementation and an executable project check; validate the actual boundary before marking the fact verified. Keep details out of the primer.

Use and preserve the supported abstraction while its guarantees fit the task. When requirements differ, inspect the implementation, extend or replace the abstraction and its checks, then update the contract. When proposing an abstraction, identify the choices it removes and how violations will be detected. Brain lint checks contract structure; project lint/tests enforce code boundaries. See `docs/brain-abstractions.md` for schemas, migration, evidence limits and the concrete record-writer contract. Writers share `_records.py`; bounded retrieval in `_context.py` reuses existing ranking and workstream selection.

### Shared domain language
Before extending a project, search its glossary and use its canonical terms in the relevant bounded context. A shared name conveys a model; inspect code/tests when claiming the implementation follows it. Here domain-driven design is distinct from the doubt-driven-development review workflow.

For a recurring ambiguity, add an opt-in `record_version: 1` glossary entry with `term`, `context`, `kind`, `one_liner`, optional `aliases`, and `definition: facts/<topic>.md`. Use `templates/domain-language.md` for the linked versioned fact: precise meaning, relationships/invariants, canonical symbols, anchored executable checks, counterexamples, and when to revise the model. Keep details out of the primer. Strict lint checks same-context term/alias ambiguity and scoped definition links; it does not scan arbitrary source identifiers or prove meaning. Aliases are searchable text, not automatic query expansion. Qualify the context when meanings differ; do not impose one vocabulary across unrelated domains. See `docs/domain-language.md` and the two `Verified` examples in glossary.yaml.

## 6. Promoting to a shared team brain
Personal brain → team brain is a rewrite, not a copy.
1. Candidates: `scope: team`, `confidence: high`, verified in the last 30 days, no `promoted:` yet, and **no personal details** (home paths, personal profiles, names, emails). Rewrite generically.
2. Dedupe against the team repo; edit in place instead of adding parallel docs.
3. Work in a branch/worktree of the team repo; show the diff to the user. **Never push or open a PR without explicit confirmation.**
4. Afterwards add `promoted: <date>` to each source item and note the PR in the STATE.md.

## 7. Upkeep and trust
`scripts/maintain.py` (scheduled) runs primer, lint, evals, freshness and the weekly mutation ratchet from `maintenance.yaml` and records `status/maintenance.json`; check it when something seems stale. `golden_skills.py` pins what skills must keep; `harness_check.py` scores repos for agent-readiness; `apply_verdicts.py` / `apply_skill_edits.py` apply a verification pass mechanically. Details: `docs/integrations.md`.

### Keeping the brain trustworthy (evals + mutation testing)
**Evals** answer "did this edit make the brain better?"
- `scripts/eval_run.py` (free, CI): `evals/questions.yaml` maps a question to a local lookup and the substrings the answer must contain. `tier: must` fails CI; `tier: coverage` is a known gap, reported only. Add a question whenever a session had to re-learn something; promote coverage → must once answered.
- `scripts/agentic_eval.py` (costs tokens, weekly/manual): a fresh agent (`AGENTIC_CMD`, e.g. `claude -p {prompt}`) answers `evals/agentic.yaml`; graded for correctness and concision; history in `metrics/agentic.json`.
- `scripts/agentic_ab.py EXAMPLE` asks an example's `evals/agentic.yaml` questions twice, with the brain (primer, tools, brain directory) and without (no primer, no tools, empty directory), and prints both scores. The example facts are invented, so the gap is the brain's contribution.
- **Eval delta rule:** a behaviour-changing edit to the primer, skills, facts or glossary must name the question it moves and show before/after. If nothing moves, log it in `evals/negative-results.md` and drop the change.

- `scripts/recall_eval.py` measures the search itself: `evals/recall.yaml` lists symptom-style queries (what someone types when stuck, not the fact's title) with the file that should come back; it reports recall@1 and recall@5 and fails below a floor (default 0.9). A miss usually means the fact lacks the words people use: add them as alias `tags:`. Queries written by someone who just read the titles are optimistic; add queries from real sessions over time.
- Instinct rows (`facts/user-instincts.md`, `tags: [instincts]`) have the shape `- **When** trigger -> **do** action. _Evidence:_ date, what was said. high|medium|low.` and are linted.

**Mutation testing** answers "would the tests notice if this script broke?"
- Hand-written mutants: `tests/mutants/<script>.yaml` lists exact `old → new` swaps (dropped guard, flipped threshold, off-by-one). `python3 scripts/mutation_check.py tests/mutants/<script>.yaml` must report all killed, no survivors, no stale. Fix survivors by adding tests, never by deleting mutants.
- Legacy scripts: `scripts/auto_mutate.py <script>` auto-mutates and lists surviving lines; `--update` records scores in `tests/mutants/legacy_scores.json`; `--check` (weekly CI) fails on any drop. Scripts without hand-written mutants live in `tests/mutants/GRANDFATHERED.txt`, which may only shrink.

**Definition of done for a new script/generator/checker** (enforced by `tests/test_definition_of_done.py`): tests written from the spec and known gotchas first; a `tests/mutants/<script>.yaml` with all mutants killed; read-only/offline unless its job is otherwise; no secrets in output; `_guard.write_json_guarded` on catalog writes (refuses >30% shrink); an eval question proving the answer is findable; and automatic upkeep (CI or scheduled job) so no manual step keeps it current.
