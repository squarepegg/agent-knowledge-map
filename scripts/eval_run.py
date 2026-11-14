#!/usr/bin/env python3
"""Deterministic brain evals (no model, free, CI-safe): a question an agent would ask -> a local lookup -> substrings the answer must contain.
  eval_run.py [evals/questions.yaml] [--json out.json]
Each entry: id, q, run: {search: "kw kw"} | {cmd: [argv...]}, expect: [substr...], first_line: substr (top-ranked result), forbid: [substr...],
tier: must (default; exit 1 on failure) | coverage (known gap; reported, never fails). Promote coverage -> must once the brain answers it.
needs: [paths relative to the brain]: SKIP the question (not counted) if any is missing - for questions about content a user may delete (the shipped examples).
Why: a brain edit only counts if some question gets answered better or at least no worse. This is the regression gate for that."""
import json, os, subprocess, sys, time
import yaml

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
B = os.environ.get("BRAIN_DIR") or os.path.dirname(HERE)
import _attempts

def answer(q):
    r = q.get("run") or {}
    if "search" in r:
        import brain
        return "\n".join(brain.search(brain.query_words(str(r["search"])), brain=B))
    if "cmd" in r:
        p = subprocess.run(r["cmd"], cwd=B, capture_output=True, text=True, timeout=60, env={**os.environ, "BRAIN_DIR": B})
        return p.stdout + p.stderr
    raise ValueError(f"{q.get('id')}: run needs 'search' or 'cmd'")

def check(q, out):
    """Pure grading -> (passed, missing, first_ok, forbidden_hit)."""
    missing = [s for s in q.get("expect", []) if s not in out]
    lines = [l for l in out.splitlines() if l.strip()]
    first_ok = (not q.get("first_line")) or (bool(lines) and q["first_line"] in lines[0])
    hit = [s for s in q.get("forbid", []) if s in out]
    return (not missing and first_ok and not hit), missing, first_ok, hit

def run(path):
    qs = yaml.safe_load(open(path)) or []; res = []
    log = _attempts.Log(B, os.path.splitext(os.path.basename(path))[0], _attempts.grader_version(check), agent=_attempts.grader_version(answer)); log.start()
    for q in qs:
        if any(not os.path.exists(os.path.join(B, n)) for n in q.get("needs") or []):
            res.append({"id": q["id"], "tier": "skip", "pass": True, "q": q.get("q", ""), "missing": [], "first_ok": True, "forbidden": [], "error": ""}); continue
        t0 = time.time()
        try: out, err = answer(q), ""
        except Exception as e: out, err = "", str(e)
        ok, missing, first_ok, hit = check(q, out)
        res.append({"id": q["id"], "tier": q.get("tier", "must"), "pass": ok and not err, "q": q.get("q", ""), "missing": missing,
                    "first_ok": first_ok, "forbidden": hit, "error": err})
        log.record(q, res[-1], time.time() - t0)
    log.end({"n": len(res), "passed": sum(r["pass"] for r in res if r["tier"] != "skip")})
    return res

def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--") and a != (argv[argv.index("--json") + 1] if "--json" in argv else None)]
    path = args[0] if args else os.path.join(B, "evals", "questions.yaml")
    res = run(path)
    for r in res:
        tag = "SKIP" if r["tier"] == "skip" else "PASS" if r["pass"] else ("FAIL" if r["tier"] == "must" else "GAP ")
        extra = "" if r["pass"] else f"  missing={r['missing']}" + ("" if r["first_ok"] else " wrong-top-result") + (f" forbidden={r['forbidden']}" if r["forbidden"] else "") + (f" error={r['error']}" if r["error"] else "")
        print(f"{tag} [{r['tier']}] {r['id']} - {r['q']}{extra}")
    must = [r for r in res if r["tier"] == "must"]; cov = [r for r in res if r["tier"] not in ("must", "skip")]
    print(f"\nmust: {sum(r['pass'] for r in must)}/{len(must)}   coverage: {sum(r['pass'] for r in cov)}/{len(cov)}   skipped: {sum(r['tier'] == 'skip' for r in res)}")
    _attempts.report_triggers(B)
    if "--json" in argv: json.dump(res, open(argv[argv.index("--json") + 1], "w"), indent=1)
    return 0 if all(r["pass"] for r in must) else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv))
