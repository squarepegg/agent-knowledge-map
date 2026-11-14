# Negative results

Brain edits that did not move any eval question. Log them and drop the change, so nobody retries them blind.

| date | change | question(s) tried | result |
|---|---|---|---|
| 2026-11-14 | Swap `brain.rank` (idf-weighted lexical + head weight) for BM25, per arXiv 2609.00006 (Hermes FTS5) | `examples/*/evals/recall.yaml`, 32 queries | Not run: no headroom. Current recall@1 0.969 (31/32), recall@5 1.0; best case +1 query, not a clear win. Retry only once a recall set has ≥ 5 misses |
