# Changelog

## [0.7.0]
- `mine_sessions.py`: proposes inbox entries (recurring errors, user corrections) from session digests, deterministically; dedupes against the brain and the inbox.
- `style.md`: new "Search before you answer" rule, adopted because it moved the measured score: 16/20 -> 19/20 correct with the brain (twice: 19/20 on both runs), fixing exactly the "stopped at the primer" failures (`docs/benchmarks.md`).
- `agentic_ab.py --style FILE` and `--no-baseline` for testing a working-style rule.

## [0.6.0]
- `agentic_ab.py EXAMPLE`: asks a fresh agent the example's `evals/agentic.yaml` questions with and without the brain and prints both scores. Measured with Claude Code (haiku): 17/20 correct with the brain vs 6/20 without across the four examples (`docs/benchmarks.md`).
- Fix: every script now defaults `BRAIN_DIR` to the directory it lives in (it used `~/.agents/brain`, so a clone elsewhere silently read another brain).
- `agentic_eval.ask` takes `cmd`, `cwd` and `env`, returns "" on timeout; `agentic_ab` retries an empty answer once, flags unreliable runs, and strips inherited brain variables.
- Search: the file-level ranker and its benchmark (v0.5.0) are unchanged.

## [0.5.0]
- Search is now file-level: a file scores its best line plus 1.5x the weight of query words found in its head (file name, `title:` / `name:` / `description:` / `tags:` / `aliases:` / `# ` lines), with idf over files and at most 3 lines per file. On a private 48-query benchmark from a production brain this moved recall@5 from 45/48 to 48/48 and recall@1 from 36 to 38; the production brain's own search scores 47/48 and 37 (see `docs/benchmarks.md`).
- More stop words (`now`, `still`, ...); example recall is now recall@1 0.88-1.0 and recall@5 1.0 for all four examples.

## [0.4.0]
Ideas taken from a mature production brain that does these better:
- `recall_eval.py` + `evals/recall.yaml`: retrieval recall@1/@5 over symptom-style queries (measures the search itself; every example ships 8 queries, recall@5 = 1.0).
- Search: stop-word removal for natural-language questions, a tiny deterministic stemmer, at most 3 lines per file, file-name boost.
- Lint: instinct-row format (`tags: [instincts]`), `--anchor-repos` for CI, unverified count in the summary.
- Example facts carry alias tags for the words people actually type.

## [0.3.0]
- Four example brains under `examples/` (data-team, web-app, platform-infra, solo-dev), applied with `brain.py init --example NAME [--force]`. Tested: complete, lint-clean, pass their own evals, and their evals fail without them. Example dates are stamped with the install date.
- Search indexes whole lines and shows a snippet around the first hit (long lines were truncated before indexing, hiding matches).
- Tests restore env vars they set (`tests/helpers.set_env`).

## [0.2.1]
- CI: mutation gate runs one job per mutants file (parallel, 15 min cap); fresh-clone job works on private repos.
- Hooks verified in a real Claude Code session (`docs/trial-claude-code.md`).

## [0.2.0]
- BM25-style deterministic search (coverage, rarity, length, title boost); skills and docs are searchable.
- `brain.py init` (idempotent setup incl. Claude Code wiring), `brain.py compact` (deterministic inbox plan, drafts, duplicate detection).
- `capture_hook.py`: Stop and UserPromptSubmit hooks for automatic capture of learnings and corrections.
- Codex CLI sessions in `digest_sessions.py`.
- Eval `needs:` (skip questions about deleted examples); tests use pristine fixtures instead of user content.
- Mutation runs isolate `HOME`; hand-written mutants for every script (no grandfathered scripts).
- Claude Code plugin manifest + hooks; CI matrix for Python 3.9-3.13 and a fresh-clone smoke job.

## [0.1.0]
- Initial generic brain: facts/workstreams/decisions/inbox, primer, lint, tours, evals, mutation gate, auto-mutation ratchet, session_start, maintain, freshness, golden skills, harness check, verification appliers.
