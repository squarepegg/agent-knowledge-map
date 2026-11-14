# Evals

| file | runner | cost |
|---|---|---|
| `questions.yaml` | `scripts/eval_run.py` | free, deterministic (CI gate) |
| `recall.yaml` | `scripts/recall_eval.py` | free, deterministic |
| `agentic.yaml` | `scripts/agentic_eval.py [--resume]` | model tokens |

## Attempt log

Every graded attempt is appended to `metrics/attempts/<eval>.jsonl` (gitignored) as it finishes. Its key covers
the fixture (including gold answers), the grader source, the brain state (HEAD, uncommitted diff and untracked files, not counting
`metrics/`) and the agent command. Change any of those and the key changes, so scores from an old grader are never mixed with a new one.
`agentic_eval.py --resume` reuses attempts with a matching key, so a crashed or stopped run is not paid for twice.

## Migration gate: one shared harness

There are three runners, each with its own loop. Merging them into one harness (fixture + grader per eval) is an option we have
**not** taken yet. The runners print `migration trigger fired: ...` when any of these checks pass:

| trigger | check | threshold (env) |
|---|---|---|
| eval types | `evals/*.yaml` count | >= 5 (`EVAL_TRIGGER_TYPES`) |
| runs too slow or expensive | a finished run's duration in the attempt log | > 30 min (`EVAL_TRIGGER_RUN_MIN`) |
| paid for twice | runs with a `run_start` but no `run_end` (crash or abort), newest excluded | >= 2 (`EVAL_TRIGGER_INCOMPLETE`) |

Not automated: drift in copied loop code (a fix landing in one runner but not the others). Check it by hand when you touch a runner.
