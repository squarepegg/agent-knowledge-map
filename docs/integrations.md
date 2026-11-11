# Integrations

The brain is plain files plus a CLI, so wiring is a few lines per agent.

## Always-loaded context (primer)
`python3 scripts/brain.py primer` writes `PRIMER.md`. Import it from the agent's global instructions:
- Claude Code: `@~/.agents/brain/PRIMER.md` in `~/.claude/CLAUDE.md`
- Codex / pi / others: symlink `PRIMER.md` to the global instructions file (`AGENTS.md`)

## Skills
Symlink `skills/*` into the agent's skills directory (`~/.claude/skills/`, `~/.agents/skills/`, ...).

## Session-start context (workstream + probes + repo facts)
`python3 scripts/session_start.py` prints environment probes (from `probes.yaml`), the active workstreams that match the current repo/branch (marking a LIKELY one only when exactly one has branch evidence) and the fact titles for the repo.

Claude Code `~/.claude/settings.json`:
```json
{ "hooks": { "SessionStart": [ { "hooks": [ { "type": "command", "command": "python3 ~/.agents/brain/scripts/session_start.py" } ] } ] } }
```
Other agents: run it from the startup script and prepend the output to the first prompt.

## Capturing learnings
`brain.py init --claude` installs three hooks (also shipped as a plugin in `hooks/hooks.json`): `session_start.py` (context), `capture_hook.py stop` (once per session, after >= 8 tool calls and no `brain.py note`, asks the agent to record learnings or say there is nothing; never loops) and `capture_hook.py prompt` (stores user corrections such as "that's wrong" in the inbox as `correction`, skipping anything that looks like a secret). Verified end to end in Claude Code: see [trial-claude-code.md](trial-claude-code.md). Run `brain.py compact` to turn the inbox into a plan, `--write` to draft unverified facts/decisions, `--archive` when handled.

Tell the agent (primer already does) to run `python3 scripts/brain.py note <kind> "<title>" "<body>"` when it learns something durable. Optional: run `scripts/digest_sessions.py` nightly to compress past sessions (pi, Claude Code, Codex CLI; set `BRAIN_SESSION_GLOBS` for others) into `digests/` and mine them for facts. Digests are redacted but git-ignored; keep them local. `python3 scripts/mine_sessions.py` then proposes learnings from them without a model: errors that recur in two or more sessions (numbers, ids, paths and quoted values masked, so the same failure matches) and user corrections. It prints a plan; `--write` adds `## [gotcha]` / `## [correction]` entries to the inbox, skipping anything the brain already says or the inbox already holds. They are leads for `brain.py compact`, not facts.

## Upkeep
`python3 scripts/maintain.py` runs the steps in `maintenance.yaml` (primer, lint, evals, freshness, weekly mutation ratchet), writes `status/maintenance.json` and optionally commits. Schedule it:
- cron: `17 3 * * *  BRAIN_DIR=$HOME/.agents/brain python3 $HOME/.agents/brain/scripts/maintain.py`
- launchd / systemd timer / GitHub Actions (`.github/workflows/maintain.yml`) all just call the same command.
`check_freshness.py` (config `freshness.yaml`) fails when a generated catalog is older than its budget. Catalog writers should use `_guard.write_json_guarded` so a partial API failure cannot overwrite good data.

## Repo readiness and skill goldens
- `python3 scripts/harness_check.py --all` scores repos under `$BRAIN_REPOS_ROOT` for agent-readiness (instructions, state routing, verification, scope, lifecycle). Heuristic.
- `python3 scripts/golden_skills.py` checks each skill in `evals/golden/skills.yaml` for frontmatter validity, pinned text, size budget and (optional, `GOLDEN_REPO_PREFIXES=acme-,svc-`) unknown repo references. `--changed origin/main` checks only edited skills.
- `scripts/apply_verdicts.py` and `scripts/apply_skill_edits.py` apply the output of a verification pass (an agent re-checking facts / skills against code) mechanically: confirmed facts get `verified_at`, doubtful ones go to `review/facts-review.md`; skill edits apply only when the `find` text is unique.

## Deliberately not included
Things that were too tied to one agent or one company to generalise, and why:
- an agent plugin/extension (tool registration, reply guards, pinning UI): agent-specific; the CLI + hooks above cover the same ground
- Cursor sessions (stored in SQLite, not JSONL) and session metrics / rule checks over one agent's log format: write an adapter on top of `digest_sessions.ADAPTERS`
- company catalogs (service topology, data lineage, repo inventory, people): build your own with the same pattern - a sync script behind `_guard`, an entry in `freshness.yaml`, a step in `maintenance.yaml`, an eval question proving the answer is findable
