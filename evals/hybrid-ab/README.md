# Hybrid A/B: commands for the mechanics, the model for judgment

`inbox_ab.py` compares three ways to process the brain inbox on a 12-item fixture (new facts, duplicates, decision, capability,
workstream progress, correction, glossary term, noise, a planted secret). Grading is deterministic (markers on disk + lint);
`--selftest` pins the grader (reference solution passes, untouched brain does not) and costs no tokens.

| arm | skill | tooling |
|---|---|---|
| manual | `skills/brain` (8 KB) minus the `compact` sentence | `compact.py` removed |
| short | `skills/brain-inbox-short` (1.9 KB, same judgment rules) | `compact.py` removed |
| hybrid | `skills/brain-inbox` (1.8 KB) | `compact` / `--write` / `--archive` / `lint` |

Result (sonnet-5-5 medium, n=8 per arm, `ledger/inbox.jsonl`): accuracy 8/8 in every arm (ceiling), cost per run
$0.114 / $0.096 / $0.077, wall 34 / 31 / 27 s. Half the saving is the shorter skill, half is the tooling.
Caveats: one task, one model; three grader checks were relaxed after seeing runs (merging a gotcha into an existing fact
counts as captured; a source note "10% to 5%" is not a stale claim); all rows were re-graded with the final grader.
