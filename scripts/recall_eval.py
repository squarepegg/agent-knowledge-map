#!/usr/bin/env python3
"""Retrieval recall eval: natural-language symptom queries -> the file that should come back. Measures the search itself (recall@1, recall@5),
which a handful of substring checks cannot. Deterministic, no model.
  recall_eval.py [evals/recall.yaml] [--floor 0.9] [--json out.json]
Entry: {q: "what a person would type when stuck", expect: "facts/some-fact.md" (path substring), needs: [paths] (skip if missing)}.
Prints `n=.. recall@1=.. recall@5=..` then a MISS line per query whose file is not in the top 5. Exit 1 if recall@5 < floor (env RECALL_FLOOR, default 0.9).
Caveat (learned the hard way): queries written by someone who has just read the fact titles are optimistic. Phrase them as symptoms, not titles,
and have a second person add queries over time. Env: BRAIN_DIR."""
import json, os, sys
import yaml
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import brain
B = os.environ.get("BRAIN_DIR") or os.path.dirname(HERE)

def file_order(rows):
    """[(path, line, text)] in rank order -> unique paths, first occurrence kept."""
    seen, out = set(), []
    for p, _, _ in rows:
        if p not in seen: seen.add(p); out.append(p)
    return out

def rank_of(paths, expect):
    """1-based position of the first path containing `expect`, or None."""
    for i, p in enumerate(paths, 1):
        if expect in p: return i
    return None

def score(ranks):
    n = len(ranks)
    return {"n": n, "recall@1": (sum(1 for r in ranks if r == 1) / n) if n else 1.0, "recall@5": (sum(1 for r in ranks if r is not None and r <= 5) / n) if n else 1.0}

def run(entries, brain_dir=None, docs=None):
    brain_dir = brain_dir or B; docs = docs if docs is not None else brain.corpus(brain_dir); res = []
    for e in entries:
        if any(not os.path.exists(os.path.join(brain_dir, n)) for n in e.get("needs") or []): continue
        paths = file_order(brain.rank(docs, brain.query_words(e["q"]), limit=200))
        res.append({"q": e["q"], "expect": e["expect"], "rank": rank_of(paths, e["expect"]), "top": paths[:3]})
    return res

def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--") and a not in (argv[argv.index("--floor") + 1] if "--floor" in argv else None, argv[argv.index("--json") + 1] if "--json" in argv else None)]
    path = args[0] if args else os.path.join(B, "evals", "recall.yaml")
    floor = float(argv[argv.index("--floor") + 1]) if "--floor" in argv else float(os.environ.get("RECALL_FLOOR", 0.9))
    res = run(yaml.safe_load(open(path)) or []); sc = score([r["rank"] for r in res])
    print(f"n={sc['n']} recall@1={sc['recall@1']:.2f} recall@5={sc['recall@5']:.2f} floor={floor:.2f}")
    for r in res:
        if r["rank"] is None or r["rank"] > 5: print(f"MISS {r['q']!r} -> expected {r['expect']}, got {r['top']}")
    if "--json" in argv: json.dump({"score": sc, "results": res}, open(argv[argv.index("--json") + 1], "w"), indent=1)
    return 0 if sc["recall@5"] >= floor else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv))
