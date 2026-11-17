# Negative results

Brain edits that did not move any eval question. Log them and drop the change, so nobody retries them blind.

| date | change | question(s) tried | result |
|---|---|---|---|
| 2026-11-17 | Inbox clustering (`scripts/cluster.py`) from arXiv 2611.18856 (group attempts by recurring problem) | `evals/cluster.yaml` dev 12 / heldout 11 / blind 12 items | Single-link, Jaccard 0.1: dev P 1.00, heldout P 0.71 (chained on one topic word). Average-link + 2 shared tokens: dev and heldout 1.00 but blind P 0.50 (related-topic items such as "base image" / "table lock" merged). Gate precision relaxed from 0.9 to 0.5 after seeing this, because clusters only annotate drafts. Not shown: that annotations help a human compact faster. Retry with a better similarity (idf, titles weighted) only against a fresh split |
| 2026-11-14 | Swap `brain.rank` (idf-weighted lexical + head weight) for BM25, per arXiv 2609.00006 (Hermes FTS5) | `examples/*/evals/recall.yaml`, 32 queries | Not run: no headroom. Current recall@1 0.969 (31/32), recall@5 1.0; best case +1 query, not a clear win. Retry only once a recall set has ≥ 5 misses |
