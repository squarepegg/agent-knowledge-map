# Brain abstraction contracts

The brain remembers supported extension points and provides commands that enforce
record structure. Markdown stays editable; `brain.py lint --strict` checks manual
edits against the same `_records.py` validator used by the writers.

## Commands

```sh
python3 scripts/brain.py ws complete my-task --check suite --command 'python3 -m unittest' --result 'passed'
python3 scripts/brain.py fact verify my-fact --source 'Observed local command output; see workstream evidence'
python3 scripts/brain.py context 'add a record writer' --budget 8000 --cwd /path/to/project
python3 scripts/brain.py lint --strict
```

Run the actual check first. `complete` and `verify` store your attestation; they
never execute the command or establish whether the result is true. Completion
sets `status: done`, clears `next`, and stores `completion_evidence` with nonblank
`check`, `command`, `result`, and an ISO `date`. Keep per-progress-item evidence in
the existing Markdown table; the completion gate checks the workstream as a whole,
not semantic correspondence between arbitrary prose bullets and table rows.

Verification preserves the claim and extension metadata, sets `verified: true`,
and records `verified_at` with `verify_by`. Both writers require a slug, reject
symlink paths, secrets and invalid records, and use atomic replacement. They assume
one local writer. Filesystem failure leaves original bytes intact; concurrent
writers need external serialization. No general multiwriter transaction is promised.

## Version and migration

New workstreams and compacted fact drafts have `record_version: 1`. Dates must not
be in the future; `verified` is a boolean and `confidence` is low, medium or high.
Extension metadata is retained. For brain-wide enforcement, set
`require_evidence: true` in `brain.config.yaml`: even deleting a workstream's
version does not bypass the completion gate. Existing brains without this setting
retain legacy lint behavior. Set it after recording evidence on existing completed
workstreams. Editing the configuration itself can disable the gate: protect it in
review/CI when that boundary matters. No local linter proves tamper resistance.

`ws complete` and `fact verify` migrate the chosen record explicitly; nothing
bulk-rewrites an existing brain. A versioned done record must have completion
evidence. Lint catches missing/invalid evidence after a manual edit. Legacy fact
records remain readable, but an explicit schema version is needed for full field
validation. Legacy compatibility means deleting that version can weaken field
checks; the brain-level completion setting covers the completion invariant only.

## Context contract

`_context.py` reuses `brain.rank`, `session_start.match` and `session_start.likely`.
Matching workstreams come first, followed by lexical relevance, with stable path
ordering. It emits whole entries only. The byte budget includes the header,
trust labels, paths, omission count and final newline; minimum 128 UTF-8 bytes.
Oversized, malformed, secret-like and symlinked entries are omitted. `omitted: N`
counts relevant entries dropped for budget plus unreadable/invalid entries found
while scanning; it is not a count of all unrelated knowledge in the brain.

`[verified]` means explicit `verified: true`, valid fields, recorded provenance and
a verification date no older than 90 days. Older explicit facts are `[stale]`.
Other material, including workstream prose and all legacy facts, is
`[unverified]`. Labels report attestation and age, not truth. Anchor drift is not
checked in this read-only command; use lint to check anchors. Context is data for
the agent to assess, not authority to execute embedded instructions or commands.

## Project extension contracts

Copy `templates/extension-contract.md` into `facts/<topic>.md`. Keep it unverified
until the actual boundary check passes. The fields are nonblank YAML strings:
`need`, `use`, `guarantees`, `boundary`, `enforcement`, `example`, `choices_removed`,
and `change_when`. Search and context discover these facts without another catalog.
`facts/brain-record-extension.md` is the concrete record-writer example.

Brain lint checks contract structure. A project's own dependency lint and contract
tests enforce its code boundary. A command in `enforcement` does not automatically
run, and a path in `example` does not prove the architecture conforms. Reference
existing checks and add a meaningful conformance case for each new extension path.
When requirements differ, update the abstraction and its checks together instead
of creating an undocumented parallel route.

## Verification plan

The locked implementation spec lives locally at `specs/brain-abstractions.md`.
Readable CLI input/outcome rows are in `tests/fixtures/abstractions.yaml`; the small
runner is `tests/test_abstractions.py`. Generated cases cover invalid field types,
Unicode budgets, repeat idempotence, read-only context, confined writes and failed
replacement. Mutants in `tests/mutants/_records.yaml` and `_context.yaml` must all
be killed. Existing CI discovers the tests and mutant files automatically.

Retrieval probes measure findability, not agent engineering performance. For a
later paid experiment, freeze dev and heldout task sets, run 3 samples per task
in both unchanged-baseline and changed arms with identical tools/model/budgets,
and record correctness, invalid writes accepted, repairs, tool calls and actual
token usage. Include changing an abstraction. Require no correctness regression
and no accepted invalid versioned writes before considering a token reduction.
No token-efficiency gain is claimed by this implementation.

## Design doubt reconciliation

Fresh-context review identified five gaps before implementation:

| Finding | Classification and resolution |
|---|---|
| Deleting record version bypasses completion validation | Actionable: brain-level `require_evidence` makes the completion check independent of version; document legacy field-validation limits. |
| Tiny budgets conflict with required diagnostics | Actionable: reject budgets below 128 bytes. |
| Trust labels undefined | Actionable: define explicit verification, 90-day age threshold, provenance, and unknown anchor freshness. |
| Field representation/types unspecified | Actionable: define frontmatter, evidence map, nonblank contract strings and date rules in the locked spec and shared validator. |
| Concrete extension boundary unspecified | Actionable: use the record-writer boundary, real compaction example and CLI/lint conformance tests. |

Implementation review found four additional actionable issues. Each received a
failing regression before its fix: creation paths now reject symlink directories;
context loads the same brain-level evidence policy as lint; completion checks
existing field types/dates before updating them; legacy YAML merge keys remain
readable while versioned records require unique explicit keys. Missing completion
attestation may be supplied by completing a workstream; unrelated malformed fields
must be repaired explicitly.

Cross-model review was offered; no external model has been invoked. Fresh-context
design and final diff reviews are separate from the deterministic test evidence.

## Test artifact boundaries

The spec guard protects existing Python test programs and the new CLI outcome
table. Existing exact-text mutation fixtures were retargeted after production
refactoring, preserving every original fault and requiring all mutants to be
killed. No existing Python test was changed or deleted. Legacy lint compatibility
is tested both before and after the explicit brain-level evidence-policy opt-in.
