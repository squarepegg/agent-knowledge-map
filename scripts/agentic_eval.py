#!/usr/bin/env python3
"""Agentic eval: ask a FRESH agent session real questions with the brain loaded; grade the final answer. Costs model tokens, so run it
weekly/manually, not per push. Agent-agnostic: set AGENTIC_CMD to any command that takes the prompt and prints the answer.
  AGENTIC_CMD='claude -p {prompt}'        # {prompt} is replaced by the (shell-quoted) prompt; without it the prompt is sent on stdin
  AGENTIC_CMD='codex exec {prompt}'       # likewise for other CLIs
  agentic_eval.py [--resume] [id ...]     # --resume reuses attempts already in metrics/attempts/ with the same key; default file evals/agentic.yaml (AGENTIC_YAML overrides, for A/B against an older brain)
Entry: id, q, expect: [[any-of], [any-of]] (every group needs one hit), expect_re: [regex], forbid: [substr], max_words.
Score per question = mean of {correct, concise}. Appends to metrics/agentic.json; exit 1 if score < AGENTIC_MIN (0.75) or dropped >= 0.15."""
import datetime, json, os, re, shlex, subprocess, sys, time
import yaml

B = os.environ.get("BRAIN_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import _attempts
PREFIX = "(Eval question - answer from what you can look up; do not modify anything.) "

def ask(q, timeout=240, cmd=None, cwd=None, env=None):
    cmd = cmd or os.environ.get("AGENTIC_CMD")
    if not cmd: sys.exit("set AGENTIC_CMD, e.g. AGENTIC_CMD='claude -p {prompt}'")
    prompt = PREFIX + q
    try: return _run(cmd, prompt, timeout, cwd, env)
    except subprocess.TimeoutExpired: return ""

def _run(cmd, prompt, timeout, cwd, env):
    if "{prompt}" in cmd: p = subprocess.run(cmd.replace("{prompt}", shlex.quote(prompt)), shell=True, capture_output=True, text=True, timeout=timeout, cwd=cwd or B, env=env)
    else: p = subprocess.run(cmd, shell=True, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=cwd or B, env=env)
    return p.stdout.strip()

def grade(item, text):
    low = text.lower()
    groups = all(any(str(a).lower() in low for a in g) for g in item.get("expect", []))
    pats = all(re.search(p, text, re.I) for p in item.get("expect_re", []))
    forbidden = any(f.lower() in low for f in item.get("forbid", []))
    checks = {"correct": groups and pats and not forbidden, "concise": len(re.findall(r"\w+", text)) <= item.get("max_words", 150)}
    return checks, sum(checks.values()) / len(checks)

def main(argv):
    yml = os.environ.get("AGENTIC_YAML") or os.path.join(B, "evals", "agentic.yaml")
    items = yaml.safe_load(open(yml)) or []
    only = [a for a in argv[1:] if not a.startswith("--")]; results = []
    log = _attempts.Log(B, os.path.splitext(os.path.basename(yml))[0], _attempts.grader_version(grade), agent=_attempts._h(os.environ.get("AGENTIC_CMD", ""), PREFIX)); log.start()
    cache = log.cached() if "--resume" in argv else {}
    for it in items:
        if only and it["id"] not in only: continue
        hit = cache.get(log.key(it))
        if hit: results.append(hit); print(f"CACHED {it['id']}: {hit['score']:.2f}"); continue
        t0 = time.time(); text = ask(it["q"]); checks, score = grade(it, text)
        results.append({"id": it["id"], "score": round(score, 2), **checks, "answer": text[:600]})
        log.record(it, results[-1], time.time() - t0)
        print(f"{'PASS' if score == 1 else 'PART' if score >= .5 else 'FAIL'} {it['id']}: {score:.2f} {checks}")
    total = round(sum(r["score"] for r in results) / max(1, len(results)), 3)
    path = os.path.join(B, "metrics", "agentic.json"); os.makedirs(os.path.dirname(path), exist_ok=True)
    hist = json.load(open(path)) if os.path.exists(path) else {"runs": []}
    prev = hist["runs"][-1]["score"] if hist["runs"] else None
    if not only:
        hist["runs"] = (hist["runs"] + [{"at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "score": total, "n": len(results), "results": results}])[-26:]
        json.dump(hist, open(path, "w"), indent=1)
    log.end({"score": total, "n": len(results)}); _attempts.report_triggers(B)
    print(f"agentic eval: {total:.2f} over {len(results)}" + (f", previous {prev:.2f}" if prev is not None else ""))
    return 1 if total < float(os.environ.get("AGENTIC_MIN", 0.75)) or (prev is not None and prev - total >= 0.15) else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
