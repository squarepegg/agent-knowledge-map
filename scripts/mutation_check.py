#!/usr/bin/env python3
"""Mutation gate: apply each hand-written mutant (exact old->new text swap) to a script in a throwaway copy of the repo,
run that script's tests, and require the tests to FAIL (mutant killed). Survivors = untested behaviour -> exit 1.
  mutation_check.py tests/mutants/<script>.yaml          (yaml: target, tests: [modules] | command: [argv...], mutants: [{id, old, new}])
Every `old` must match exactly once (a stale mutant is an error, not a pass)."""
import concurrent.futures, os, shutil, site, subprocess, sys, tempfile
import yaml

ROOT = os.environ.get("MUTATION_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


SKIP_COPY = {".git", ".cache", "node_modules", "digests"}


def run_copy(new_src, target, cmd):
    """Copy the brain to a temp dir, write new_src over target, run the test command there -> (passed, output)."""
    tmp = tempfile.mkdtemp()
    try:
        for name in os.listdir(ROOT):   # everything the tests may read (facts, glossary, PRIMER.md, status...) except VCS/cache dirs
            if name in SKIP_COPY: continue
            src, dst = os.path.join(ROOT, name), os.path.join(tmp, name)
            if os.path.isdir(src): shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else: shutil.copy2(src, dst)
        open(os.path.join(tmp, target), "w").write(new_src)
        env = {**os.environ, "BRAIN_DIR": tmp, "HOME": tmp, "PYTHONUSERBASE": site.getuserbase(), "PYTHONDONTWRITEBYTECODE": "1"}   # HOME too: a mutant must never be able to touch the real home directory
        r = subprocess.run(cmd, cwd=tmp, env=env, capture_output=True, text=True, timeout=300)
        return r.returncode == 0, (r.stdout + r.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_one(spec_path):
    spec = yaml.safe_load(open(spec_path))
    target, mutants = spec["target"], spec["mutants"]
    cmd = spec.get("command") or [sys.executable, "-m", "unittest", *spec["tests"]]  # command: any test runner (e.g. node --test) run in the copy
    src = open(os.path.join(ROOT, target)).read()
    survivors, stale, killed = [], [], 0
    base_ok, base_out = run_copy(src, target, cmd)  # unmutated copy must pass, else every mutant would look 'killed'
    if not base_ok:
        print(f"{target}: baseline FAILS in a clean copy; mutation results would be meaningless:\n{base_out[-1500:]}")
        return False
    live = []
    for m in mutants:
        if src.count(m["old"]) != 1: stale.append(f"{m['id']} (matches {src.count(m['old'])}x)")
        else: live.append(m)
    jobs = max(1, int(os.environ.get("MUTATION_JOBS") or min(4, os.cpu_count() or 1)))
    with concurrent.futures.ThreadPoolExecutor(jobs) as ex:  # each mutant runs in its own throwaway copy, so they are independent
        results = list(ex.map(lambda m: run_copy(src.replace(m["old"], m["new"]), target, cmd)[0], live))
    for m, ok in zip(live, results):
        if ok: survivors.append(m["id"])
        else: killed += 1
    print(f"{target}: {killed}/{len(mutants)} mutants killed; survivors={survivors or 'none'}; stale={stale or 'none'}")
    return not survivors and not stale


if __name__ == "__main__":
    sys.exit(0 if all([run_one(p) for p in sys.argv[1:]]) else 1)
