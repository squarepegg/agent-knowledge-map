# cluster-ab: do the `compact.py --group` hints help a model group an inbox?

`cluster_ab.py` gives a fresh `claude -p` session all 35 items of `evals/cluster.yaml` as one inbox and asks it to group the notes that are the same
recurring problem. Arm `plain` shows the notes; arm `annotated` adds "(may be the same problem as [a], [b])" from `cluster.py`. Graded by pairwise
precision/recall/F1 against the gold groups. `--selftest` (also in `tests/test_cluster.py`) pins the grader and costs nothing.

Result (haiku, n=5 per arm, `ledger/haiku.jsonl`, every run valid):

| arm | precision | recall | F1 |
|---|---|---|---|
| plain | 0.97 | 0.93 | 0.95 |
| annotated | 0.84 | 0.98 | 0.90 |

The hints recover pairs the model missed and add false merges (the clusterer's blind-split precision is ~0.5), a net loss. Hence `--group` is opt-in.
Caveats: one model, one fixture written by the same author as the clusterer, n=5 (no significance test; paired by run: 3 favour `plain`, 1 favours `annotated` by 0.006, 1 tie).
A human timing study was not run.
