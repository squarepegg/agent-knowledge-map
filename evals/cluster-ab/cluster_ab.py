#!/usr/bin/env python3
"""Do the `~~` annotations from compact.py help a model group an inbox? A/B on all of evals/cluster.yaml (35 items, one inbox).
  plain      the numbered items
  annotated  the same items plus "(may be the same problem as [a], [b])" from cluster.py (precision ~0.5 on the blind split, so some hints are wrong)
Task: group the items that are the same recurring problem; answer a JSON array of arrays of item numbers. Graded deterministically: pairwise
precision / recall / F1 against the gold groups. Fresh `claude -p` per run, no tools, temp cwd.
  cluster_ab.py --selftest                      free: grader and arm builder
  cluster_ab.py --model haiku --n 5 [--out ledger/run.jsonl]   costs tokens
Reports per-arm means and, since n is small, the per-run values. No verdict is computed: read the table."""
import itertools, json, os, re, statistics, subprocess, sys, tempfile
import yaml
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cluster, cluster_eval

def load(): return yaml.safe_load(open(os.path.join(ROOT, "evals", "cluster.yaml")))

def build(items, arm):
    hints = {}
    if arm == "annotated":
        for g in cluster.cluster(items):
            for i in g:
                if len(g) > 1: hints[i] = [j for j in g if j != i]
    lines = []
    for i, it in enumerate(items, 1):
        h = f"  (may be the same problem as {', '.join('[%d]' % (j + 1) for j in hints[i - 1])})" if i - 1 in hints else ""
        lines.append(f"[{i}] {it['kind']}: {it['title']} - {it['body']}{h}")
    return ("Below are notes from an agent's inbox. Group the notes that describe the same recurring problem (same underlying cause or fix), "
            "even when worded differently. Notes about merely related topics are NOT the same problem. Every note appears in exactly one group; "
            "a note with no match is a group of one. Do not use tools. Answer with only a JSON array of arrays of note numbers.\n\n" + "\n".join(lines))

def parse(text, n):
    m = re.search(r"\[\s*\[.*\]\s*\]", text, re.S)
    if not m: return None
    try: groups = json.loads(m.group(0))
    except ValueError: return None
    flat = [x for g in groups if isinstance(g, list) for x in g]
    if not all(isinstance(x, int) for x in flat) or sorted(flat) != list(range(1, n + 1)) or len(flat) != n: return None
    return [[x - 1 for x in g] for g in groups]

def score(items, groups):
    if groups is None: return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "valid": False}
    return {**cluster_eval.prf(cluster_eval.pairs(groups), cluster_eval.pairs(cluster_eval.gold_groups(items))), "valid": True}

def ask(prompt, model):
    with tempfile.TemporaryDirectory() as d:
        return subprocess.run(["claude", "-p", "--model", model], input=prompt, capture_output=True, text=True, timeout=240, cwd=d).stdout

def selftest():
    items = load(); n = len(items); gold = [[i + 1 for i in g] for g in cluster_eval.gold_groups(items)]
    assert parse("```json\n" + json.dumps(gold) + "\n```", n) is not None
    assert score(items, parse(json.dumps(gold), n))["f1"] == 1.0
    assert score(items, parse(json.dumps([[i] for i in range(1, n + 1)]), n))["recall"] == 0.0
    assert parse("[[1,2],[3]]", n) is None and parse("no json", n) is None                      # incomplete / unparseable
    assert parse(json.dumps(gold + [[1]]), n) is None                                         # duplicated note
    assert score(items, None)["f1"] == 0.0
    assert "same problem as" not in build(items, "plain") and "same problem as" in build(items, "annotated")
    print("selftest ok")

def main(argv):
    if "--selftest" in argv: return selftest()
    opt = lambda k, d: argv[argv.index(k) + 1] if k in argv else d
    model, n, out = opt("--model", None), int(opt("--n", 5)), opt("--out", None)
    if not model: sys.exit("pin the model: --model haiku")
    items = load(); rows = []
    for k in range(n):
        for arm in ("plain", "annotated"):
            r = {"arm": arm, "run": k, "model": model, **score(items, parse(ask(build(items, arm), model), len(items)))}
            rows.append(r); print(json.dumps(r), flush=True)
            if out: open(out, "a").write(json.dumps(r) + "\n")
    for arm in ("plain", "annotated"):
        rs = [r for r in rows if r["arm"] == arm]
        print(f"{arm}: n={len(rs)} valid={sum(r['valid'] for r in rs)} precision={statistics.mean(r['precision'] for r in rs):.2f} "
              f"recall={statistics.mean(r['recall'] for r in rs):.2f} f1={statistics.mean(r['f1'] for r in rs):.2f}")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
