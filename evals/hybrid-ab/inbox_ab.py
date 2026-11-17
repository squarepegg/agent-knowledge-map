#!/usr/bin/env python3
"""A/B: does moving the mechanics of inbox compaction into commands (hybrid) beat the prose protocol (manual)?
Costs tokens (laptop only). Grading is deterministic (marker strings on disk + lint), never a model.

  python3 evals/hybrid-ab/inbox_ab.py --selftest                 grader pinned both ways, no model
  EVAL_PI_ARGS='["--model","p/id"]' python3 evals/hybrid-ab/inbox_ab.py [--n 5] [--jobs 3] [--out results/hybrid-ab/inbox.jsonl]
  python3 evals/hybrid-ab/inbox_ab.py --report results/hybrid-ab/inbox.jsonl

Arms (each a fresh `pi --mode rpc` session with cwd = a throwaway brain; same prompt):
  manual  skills/brain/SKILL.md with the `brain.py compact` sentence removed, and scripts/compact.py deleted
  short   evals/hybrid-ab/skills/brain-inbox-short: hybrid-length prose, same judgment rules, no compact (isolates tooling from skill length)
  hybrid  evals/hybrid-ab/skills/brain-inbox/SKILL.md: compact/--write/--archive/lint do the mechanics, the agent judges
Task: a 12-item inbox (2 new facts, 2 duplicates of existing facts, decision, capability, workstream progress, correction of an
existing claim, glossary-type term, noise, and one secret). Gold = marker strings in specific files (see grade()).
Resumable: a (arm, i) already in --out is skipped.
"""
import concurrent.futures as cf, datetime, glob, importlib.util, json, os, re, shutil, subprocess, sys, tempfile, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
HAB = os.environ.get("HAB_RUN", os.path.expanduser("~/projects/me/agent-toolkit-public/evals/harness-ab"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
ARMS = ("manual", "short", "hybrid")
LOCK = threading.Lock()
TODAY = str(datetime.date.today())
SECRET_VALUE = "hunter2hunter2hunter2xx"   # matches brain.SECRET (token: <16+ chars>)

INBOX = f"""
## [gotcha] Playwright trace upload fails for traces over 50 MB
CI drops the artifact silently. Set `PW_TRACE_LIMIT_MB=45` in the e2e job so the trace is trimmed before upload.

## [gotcha] Advisory lock held across migrations blocks the deploy
Migrations that take `pg_advisory_lock(7731)` and run inside the same transaction as the backfill deadlock the canary step. Release the lock before the backfill.

## [gotcha] Purge the CDN for /static after a deploy that changes asset names
Also purge `/manifest.json`, the PWA manifest is cached for 1 hour and references old asset names.

## [gotcha] New feature flags default to off in production and are removed within 30 days
The `flag-audit` job also posts the stale-flag list to `#eng-flags` every Monday.

## [decision] Adopt trunk-based branching for shop-web
Short-lived branches (max 2 days) merged to main behind flags; release branches are retired. Chosen over gitflow because the canary already gates risk.

## [capability] Query staging logs via Loki
`logcli query '{{app="shop-api"}}' --addr=$LOKI_STAGING_URL` after connecting to the VPN; read-only.

## [workstream] checkout-redesign: payment step implemented
Payment step behind `checkout_single_page`; `pnpm test:e2e` passes 41/41 on chromium+webkit.

## [correction] The canary is 5 percent, not 10
User: "the canary rollout is 5% of traffic, we changed it last month". The deploy-canary fact says 10%.

## [gotcha] Staging deploy key rotation
Rotated; new value is token: {SECRET_VALUE}

## [fact] Fixed a typo in the README
Changed 'recieve' to 'receive' in README.md (zz-typo-readme).

## [fact] Bento is our internal design system
Bento = the shared React component library for shop-web and shop-api admin screens.

## [gotcha] Safari ITP expires first-party cookies after 7 days
Set the session cookie server-side with `Max-Age=2592000`; `document.cookie` writes are capped at 7 days in Safari.
"""

PROMPT = ("The current directory is the brain root ($B). The inbox has unprocessed items. Process the inbox following your brain skill "
          "and leave the brain lint-clean with the inbox archived. Do not ask questions; decide yourself. "
          "Finish with a 3-line summary: added / merged / discarded.")


def build(r, arm):
    """Throwaway brain in r (r exists, empty) -> skill dir for the arm"""
    import helpers
    src = helpers.fixture_brain()
    for n in os.listdir(src):
        s, d = os.path.join(src, n), os.path.join(r, n)
        shutil.copytree(s, d) if os.path.isdir(s) else shutil.copy(s, d)
    env = {**os.environ, "BRAIN_DIR": r}
    subprocess.run([sys.executable, os.path.join(r, "scripts", "init_brain.py"), "--example", "web-app"], env=env, cwd=r, check=True, capture_output=True)
    for n in ("skills", "examples", "docs", "evals"):
        shutil.rmtree(os.path.join(r, n), ignore_errors=True)
    os.makedirs(os.path.join(r, "inbox"), exist_ok=True)
    open(os.path.join(r, "inbox", f"{TODAY}-1001.md"), "w").write(INBOX)
    arm_dir = tempfile.mkdtemp(prefix=f"arm-{arm}-")
    if arm in ("hybrid", "short"):
        shutil.copy(os.path.join(HERE, "skills", "brain-inbox" if arm == "hybrid" else "brain-inbox-short", "SKILL.md"), arm_dir)
        if arm == "short": os.remove(os.path.join(r, "scripts", "compact.py"))
    else:
        text = open(os.path.join(ROOT, "skills", "brain", "SKILL.md")).read()
        text, n = re.subn(r" `brain\.py compact` prints a deterministic plan.*?Drafts still need the verification below\.", " Drafts need verification below.", text, flags=re.S)
        assert n == 1, "manual arm: compact sentence not found"
        text = re.sub(r" Same-problem items get `~~`.*?\n", "\n", text)
        assert "brain.py compact" not in text, "manual arm still mentions compact"
        open(os.path.join(arm_dir, "SKILL.md"), "w").write(text)
        os.remove(os.path.join(r, "scripts", "compact.py"))
    return arm_dir


def _read(r, rel):
    try: return open(os.path.join(r, rel), errors="ignore").read()
    except OSError: return ""


def _files(r, pat):
    return [p for p in glob.glob(os.path.join(r, pat), recursive=True) if os.path.isfile(p)]


def grade(r):
    """-> checks {name: bool}. Markers are natural content the agent has no reason to drop."""
    pre = {"cdn-purge-after-deploy.md", "db-migrations-expand-contract.md", "deploy-canary.md", "e2e-safari-flaky.md",
           "error-budget-policy.md", "feature-flags-default-off.md"}
    facts = {os.path.basename(p): _read(r, os.path.relpath(p, r)) for p in _files(r, "facts/*.md")}
    new_facts = {k: v for k, v in facts.items() if k not in pre}
    curated = "".join(facts.values()) + "".join(_read(r, os.path.relpath(p, r)) for p in _files(r, "decisions/*.md")) \
        + _read(r, "capabilities.yaml") + _read(r, "glossary.yaml") + "".join(_read(r, os.path.relpath(p, r)) for p in _files(r, "workstreams/**/*.md"))
    outside_inbox = "".join(_read(r, os.path.relpath(p, r)) for p in _files(r, "**/*") if "/inbox/" not in p and "/.git/" not in p and "/__pycache__/" not in p)
    cdn, flags, canary = facts.get("cdn-purge-after-deploy.md", ""), facts.get("feature-flags-default-off.md", ""), facts.get("deploy-canary.md", "")
    state = _read(r, "workstreams/checkout-redesign/STATE.md")
    progress = state.split("## Progress", 1)[-1].split("## Verification evidence", 1)[0]
    evidence = state.split("## Verification evidence", 1)[-1].split("## Next steps", 1)[0]
    instincts = facts.get("user-instincts.md", "")
    lint = subprocess.run([sys.executable, os.path.join(r, "scripts", "brain.py"), "lint"], env={**os.environ, "BRAIN_DIR": r}, cwd=r, capture_output=True, text=True)
    left = [p for p in glob.glob(os.path.join(r, "inbox", "*.md")) if not p.endswith("README.md")]
    return {
        "fact_trace_captured": any("PW_TRACE_LIMIT_MB" in v for v in facts.values()),   # merging into the existing e2e fact is also valid
        "fact_lock_captured": any("pg_advisory_lock(7731)" in v for v in facts.values()),   # merging into the existing migrations fact is also valid
        "new_fact_safari": any("Max-Age=2592000" in v for v in new_facts.values()),
        "dup_cdn_merged": "/manifest.json" in cdn and not any("/manifest.json" in v for v in new_facts.values()),
        "dup_flags_merged": "#eng-flags" in flags and not any("#eng-flags" in v for v in new_facts.values()),
        "decision_written": any("trunk-based" in _read(r, os.path.relpath(p, r)).lower() for p in _files(r, "decisions/*.md")),
        "capability_added": "logcli" in _read(r, "capabilities.yaml"),
        "workstream_progress": "payment" in progress.lower(),
        "workstream_evidence_row": "41/41" in evidence,
        "correction_applied": "5%" in canary and "canaries at 10%" not in canary and "10% of traffic" not in canary,   # a source note "from 10% to 5%" is fine
        "term_captured": "Bento" in _read(r, "glossary.yaml") or any("Bento" in v for v in new_facts.values()),
        "secret_absent": SECRET_VALUE not in outside_inbox and SECRET_VALUE not in "".join(_read(r, os.path.relpath(p, r)) for p in _files(r, "inbox/processed/*")),
        "noise_discarded": "zz-typo-readme" not in curated and "recieve" not in curated,
        "inbox_archived": not left and bool(_files(r, "inbox/processed/*.md")),
        "lint_clean": lint.returncode == 0,
    }


def reference(r):
    """a correct manual solution, applied by script: pins the grader (all checks must pass)"""
    import yaml
    def w(rel, t, mode="w"):
        p = os.path.join(r, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, mode).write(t)
    fm = lambda title: f"---\ntitle: {title}\nrepos: []\ntags: []\nanchors: []\nverified: true\nverified_at: '{TODAY}'\nconfidence: medium\nscope: personal\nsource: inbox {TODAY}\n---\n"
    w("facts/playwright-trace-limit.md", fm("Playwright trace upload fails over 50 MB") + "Set `PW_TRACE_LIMIT_MB=45`.\n")
    w("facts/advisory-lock-migrations.md", fm("Advisory lock blocks deploy") + "Release `pg_advisory_lock(7731)` before the backfill.\n")
    w("facts/safari-cookie-cap.md", fm("Safari ITP caps cookies") + "Use `Max-Age=2592000` server-side.\n")
    w("facts/cdn-purge-after-deploy.md", "Also purge `/manifest.json`.\n", "a")
    w("facts/feature-flags-default-off.md", "Stale list posts to `#eng-flags`.\n", "a")
    w("decisions/2026-01-01-trunk.md", "# Adopt trunk-based branching\ndate: 2026-01-01\nstatus: accepted\n## Context\nx\n## Decision\ntrunk-based\n## Consequences\n## Predicted outcome\n## Observed\n")
    caps = yaml.safe_load(_read(r, "capabilities.yaml")) or []
    caps.append({"id": "staging-logs", "enables": "Query staging logs", "requires": ["vpn"], "how": "`logcli query`"})
    w("capabilities.yaml", yaml.safe_dump(caps))
    gl = yaml.safe_load(_read(r, "glossary.yaml")) or []
    gl.append({"term": "Bento", "kind": "system", "one_liner": "Internal React design system", "repos": ["shop-web"]})
    w("glossary.yaml", yaml.safe_dump(gl))
    s = _read(r, "workstreams/checkout-redesign/STATE.md")
    s = s.replace("- Address step implemented behind the flag", "- Address step implemented behind the flag\n- Payment step implemented behind the flag")
    s = s.replace("| e2e passes on chromium+webkit | `pnpm test:e2e` | 38/38 (1 retry) | 2025-01-15 |", f"| e2e passes on chromium+webkit | `pnpm test:e2e` | 38/38 (1 retry) | 2025-01-15 |\n| payment step e2e | `pnpm test:e2e` | 41/41 | {TODAY} |")
    w("workstreams/checkout-redesign/STATE.md", s)
    c = _read(r, "facts/deploy-canary.md").replace("10%", "5%")
    w("facts/deploy-canary.md", c)
    w("facts/user-instincts.md", fm("User instincts").replace("tags: []", "tags: [instincts]") + f"- **When** quoting a rollout percentage -> **do** check it against the current config. _Evidence:_ {TODAY}, user corrected 10% to 5%. high.\n")
    for p in glob.glob(os.path.join(r, "inbox", "*.md")):
        if not p.endswith("README.md"):
            os.makedirs(os.path.join(r, "inbox", "processed"), exist_ok=True)
            shutil.move(p, os.path.join(r, "inbox", "processed", os.path.basename(p).replace(SECRET_VALUE, "")))
    pr = os.path.join(r, "inbox", "processed")
    for p in glob.glob(pr + "/*.md"):
        t = open(p).read().replace(SECRET_VALUE, "REDACTED"); open(p, "w").write(t)


def selftest():
    for arm in ARMS:
        r = tempfile.mkdtemp(prefix="selftest-"); build(r, arm)
        null = grade(r)
        assert null["lint_clean"] and not null["inbox_archived"] and not null["fact_trace_captured"], null
        reference(r); g = grade(r)
        bad = [k for k, v in g.items() if not v]
        assert not bad, f"{arm}: reference fails {bad}"
    r = tempfile.mkdtemp(prefix="selftest-"); build(r, "hybrid")
    p = subprocess.run([sys.executable, os.path.join(r, "scripts", "brain.py"), "compact"], env={**os.environ, "BRAIN_DIR": r}, cwd=r, capture_output=True, text=True)
    assert p.returncode == 2 and "secret" in p.stderr, ("compact should refuse on the planted secret", p.returncode, p.stderr)
    print(f"selftest ok: {len(g)} checks; null brain passes only lint; reference passes all; compact refuses the planted secret")


def run_one(arm, i, session, out, model, turn_timeout):
    base = tempfile.mkdtemp(prefix=f"inbox-{arm}-{i}-"); r = os.path.join(base, "brain"); os.makedirs(r)
    arm_dir = build(r, arm)
    t0 = time.time()
    log, usage, finished = session(r, arm_dir, PROMPT, lambda n, t: None, turn_timeout)
    if usage["assistant_msgs"] == 0: raise RuntimeError(f"{arm} #{i}: no assistant message; check EVAL_PI_ARGS")
    checks = grade(r)
    tools = [c for x in log for c in x["tools"]]
    row = {"arm": arm, "i": i, "model": model, "date": TODAY, "finished": finished, "checks": checks, "passed": sum(checks.values()), "n_checks": len(checks),
           "all_pass": all(checks.values()), "cost_usd": round(usage["cost"], 4), "output_tokens": usage["output"],
           "input_tokens": usage["input"] + usage["cacheRead"] + usage["cacheWrite"], "assistant_msgs": usage["assistant_msgs"],
           "tool_calls": len(tools), "wall_s": round(time.time() - t0), "workdir": base,
           "final": (log[-1]["assistant"] if log else "")[-1500:]}
    with LOCK:
        with open(out, "a") as f: f.write(json.dumps(row) + "\n")
        print(f"{arm} #{i}: {row['passed']}/{row['n_checks']} ${row['cost_usd']:.3f} {row['wall_s']}s tools={row['tool_calls']} fails={[k for k, v in checks.items() if not v]}", flush=True)


def report(path):
    import statistics as st
    rows = [json.loads(l) for l in open(path)]
    print("| arm | n | accuracy (mean checks) | all-pass runs | cost $ (mean) | wall s (mean) | tool calls | output tok | input tok |\n|---|---|---|---|---|---|---|---|---|")
    for arm in ARMS:
        rs = [x for x in rows if x["arm"] == arm]
        if not rs: continue
        m = lambda k: st.mean(x[k] for x in rs)
        print(f"| {arm} | {len(rs)} | {st.mean(x['passed'] / x['n_checks'] for x in rs):.3f} | {sum(x['all_pass'] for x in rs)}/{len(rs)} | {m('cost_usd'):.3f} | {m('wall_s'):.0f} | {m('tool_calls'):.1f} | {m('output_tokens'):.0f} | {m('input_tokens'):.0f} |")
    fails = {}
    for x in rows:
        for k, v in x["checks"].items():
            if not v: fails.setdefault(k, {}).setdefault(x["arm"], 0); fails[k][x["arm"]] += 1
    print("\nfailed checks (count of runs):", json.dumps(fails, sort_keys=True))


def main(a):
    if "--selftest" in a: return selftest()
    opt = lambda k, d: a[a.index(k) + 1] if k in a else d
    if "--report" in a: return report(opt("--report", None))
    pi_args = os.environ.get("EVAL_PI_ARGS", "[]")
    if "--model" not in json.loads(pi_args): raise SystemExit("pin the model: EVAL_PI_ARGS='[\"--model\",\"provider/id\"]'")
    sys.path.insert(0, HAB)
    spec = importlib.util.spec_from_file_location("hab_run", os.path.join(HAB, "run.py")); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    out = opt("--out", os.path.join(ROOT, "results", "hybrid-ab", "inbox.jsonl")); os.makedirs(os.path.dirname(out), exist_ok=True)
    done = {(x["arm"], x["i"]) for x in map(json.loads, open(out))} if os.path.exists(out) else set()
    n, jobs = int(opt("--n", 5)), int(opt("--jobs", 3))
    todo = [(arm, i) for i in range(n) for arm in ARMS if (arm, i) not in done]   # interleaved: drift hits both arms
    with cf.ThreadPoolExecutor(jobs) as ex:
        fs = [ex.submit(run_one, arm, i, m.session, out, pi_args, 900) for arm, i in todo]
        for f in fs: f.result()
    report(out)


if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
