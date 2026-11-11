# Search benchmarks

`scripts/recall_eval.py` measures retrieval: for each symptom-style query, where does the file that should answer it land (recall@1 = first, recall@5 = top five files)?

## Method
- A private 48-query set written for a mature production brain (84 facts, 8,700 indexed lines): "kubectl unauthorized token has expired silently" -> the fact about SSO expiry. The queries and facts are not in this repo.
- The ranker under test searches the same brain directory; a hit is the first file whose path is the expected fact. Files are deduplicated, so a file with three matching lines counts once.
- The production brain's own search (a separate TypeScript implementation: idf-weighted line scores, a title boost, three lines per file) was run on the same set as the baseline.

## Results
| ranker | recall@1 | recall@5 |
|---|---|---|
| this repo, v0.2 (line-level BM25, term-coverage first) | 36/48 | 45/48 |
| production brain search | 37/48 | 47/48 |
| this repo, v0.5 (file-level, head boost, stemming, stop words) | **38/48** | **48/48** |

What moved the number: scoring **files** by their best line plus a boost for words found in the file's head (name, title, description, tags) did most of it (recall@5 42 -> 48 when the head boost was switched on); idf over files instead of lines and stemming did the rest.

## Caveats
- One benchmark, one brain, 48 queries. A difference of one query is noise. The head weight (1.5) was taken from the production brain, not fitted to this set; 2.0 gives one more recall@1 here and was not adopted.
- The set was written by someone who had seen the fact titles, so absolute numbers are optimistic. Add queries from real sessions over time.
- The four example brains ship 8 recall queries each. Their alias `tags:` were added after seeing misses, so they are a regression guard, not an independent measurement.

# Does the brain help an agent? (`scripts/agentic_ab.py`)

Same questions, a fresh Claude Code session (model: haiku), two conditions per example:
- **with the brain**: the example applied, its `PRIMER.md` appended to the system prompt, tools `Bash,Read,Grep,Glob`, working directory = the brain;
- **without**: no primer, no tools, an empty directory.
Your own `CLAUDE.md` is disabled (`CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`) and MCP servers are off in both. The example facts are invented, so a correct answer without the brain is a lucky guess (or common knowledge).

| example | with brain | without | gain |
|---|---|---|---|
| web-app | 5/5 | 2/5 | +3 |
| platform-infra | 5/5 | 2/5 | +3 |
| data-team | 4/5 | 1/5 | +3 |
| solo-dev | 3/5 | 1/5 | +2 |
| **total** | **17/20** | **6/20** | **+11** |

## What the misses show
- Stopping at the primer: asked for two facts, the agent found one in the primer ("daily_core by 07:00") and said it had no information on the second instead of searching. Same for "what time do backups run".
- Answering from general knowledge: "why would a commit use the wrong email?" got a generic git answer; the brain-specific cause (`includeIf` by directory) was one search away.
- Both are agent-behaviour failures, not retrieval failures (`recall_eval` finds the right file for these questions). Possible fixes to test with this tool: a stronger "search before answering from memory" rule in `style.md`, or primer lines that say which topics have facts.

## Caveats and how this was measured
- 5 questions per example, one run each, one model: a difference of one answer is noise. The pooled +11 over 20 questions is the number to trust.
- A first run with four examples in parallel produced empty baseline answers (timeouts under load), which inflated the gain to +4/+5. That run is discarded. The tool now retries an empty answer once and prints a warning if any answer is still empty; the numbers above are sequential runs with no empty answers.
- Two expected-answer lists were widened after seeing correct answers that the first strings rejected (`D-4` for rollup finality, `pause` for the error budget); those two examples were then re-run in full.

## Testing a working-style rule (eval delta)
Hypothesis from the misses above: agents stop at the primer instead of searching. Rule tested (replacing "Use local lookups first"): *Search before you answer: never answer ... from memory or from this primer alone; if the primer gives only part of the answer, search for the rest before saying you don't know.* Same 20 questions, with-brain condition only (`agentic_ab.py EXAMPLE --no-baseline [--style FILE]`), examples run one at a time:

| style | web-app | platform-infra | data-team | solo-dev | total |
|---|---|---|---|---|---|
| old rule (run 1) | 5 | 5 | 4 | 3 | 17/20 |
| old rule (run 2) | 5 | 4 | 4 | 3 | 16/20 |
| new rule (run 1) | 5 | 5 | 5 | 4 | 19/20 |
| new rule (run 2) | 5 | 5 | 5 | 4 | 19/20 |

The old-rule failures were the stop-at-the-primer answers (daily_core SLA found, dashboard refresh "not available"; backup frequency found, time "not specified") plus one grader-strict miss; both stop-early answers now search and pass. The remaining miss (wrong commit email) is an answer from general knowledge that the rule did not fix. Four runs of 20 questions on one model is small: the evidence is consistent (no example got worse, three got better, repeated) but not strong. Adopted because it is cheap and targets an observed mechanism; revert it if a larger run says otherwise.
