#!/usr/bin/env python3
"""Session-start context for any agent: environment probes + the workstreams and fact titles that match the current repo/branch.
Print to stdout; wire it as a SessionStart hook (Claude Code) or run it from your agent's startup script.
  session_start.py [--cwd DIR] [--no-probes]
Matching: a workstream is relevant when status is active|blocked and (its `repos:` lists the repo, or the branch matches one of its `branches:` globs
or contains the slug). If exactly one matching workstream has branch evidence it is marked LIKELY; recency is never used to guess.
Probes come from probes.yaml: {id, label, cmd: [argv], okWhen: exit0|stdoutNonEmpty, fix, timeout}. Env: BRAIN_DIR."""
import fnmatch, glob, os, subprocess, sys
import yaml
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from _fm import frontmatter
B = os.environ.get("BRAIN_DIR") or os.path.dirname(HERE)

def as_list(v): return [str(x) for x in v] if isinstance(v, list) else ([str(v)] if v else [])

def load_workstreams(brain=None):
    out = []
    for p in glob.glob(f"{brain or B}/workstreams/*/STATE.md"):
        fm, _ = frontmatter(p)
        out.append({"slug": str(fm.get("slug") or os.path.basename(os.path.dirname(p))), "title": str(fm.get("title") or ""),
                    "status": str(fm.get("status") or "active").lower(), "repos": as_list(fm.get("repos")), "branches": as_list(fm.get("branches")),
                    "updated": str(fm.get("updated") or ""), "next": as_list(fm.get("next")), "file": p})
    return sorted(out, key=lambda w: w["updated"], reverse=True)

def branch_evidence(w, branch):
    if not branch or branch in ("main", "master"): return False
    if any(fnmatch.fnmatchcase(branch, g) for g in w["branches"]): return True
    return len(w["slug"]) >= 6 and w["slug"].lower() in branch.lower()

def match(workstreams, repo, branch):
    repo = (repo or "").lower()
    return [w for w in workstreams if w["status"] in ("active", "blocked") and (any(r.lower() == repo for r in w["repos"]) or branch_evidence(w, branch))]

def likely(matches, branch):
    ev = [w for w in matches if branch_evidence(w, branch)]
    return ev[0] if len(ev) == 1 else None

def run_probe(p):
    try:
        r = subprocess.run(p["cmd"], capture_output=True, text=True, timeout=p.get("timeout", 4))
    except Exception as e:
        return False, type(e).__name__
    ok = bool(r.stdout.strip()) if p.get("okWhen") == "stdoutNonEmpty" else r.returncode == 0
    return ok, (r.stdout.strip().splitlines() or [""])[0][:60]

def load_probes(brain=None):
    p = os.path.join(brain or B, "probes.yaml")
    return (yaml.safe_load(open(p)) or []) if os.path.exists(p) else []

def git_info(cwd):
    def g(*a):
        r = subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else ""
    top = g("rev-parse", "--show-toplevel")
    return (os.path.basename(top) if top else os.path.basename(os.path.abspath(cwd))), (g("symbolic-ref", "--short", "-q", "HEAD") or g("rev-parse", "--abbrev-ref", "HEAD"))

def fact_titles(repo, brain=None):
    out = []
    for p in sorted(glob.glob(f"{brain or B}/facts/*.md")):
        fm, _ = frontmatter(p)
        if repo.lower() in [r.lower() for r in as_list(fm.get("repos"))]:
            out.append(("(unverified) " if fm.get("verified") is False else "") + str(fm.get("title") or os.path.basename(p)))
    return out

def render(repo, branch, matches, pick, probes, facts):
    L = [f"Brain context for {repo}" + (f" @ {branch}" if branch else "")]
    if probes: L += ["Environment:"] + [f"  {'ok' if ok else 'FAIL'} {p['label'] if 'label' in p else p['id']}" + ("" if ok else f" -> fix: {p.get('fix', '-')}") for p, ok in probes]
    if matches:
        L.append("Workstreams (read STATE.md before working):")
        for w in matches:
            nxt = f" | next: {w['next'][0]}" if w["next"] else ""
            L.append(f"  {'* LIKELY ' if w is pick else '- '}{w['slug']} [{w['status']}] {w['file']}{nxt}")
        if not pick and len(matches) > 1: L.append("  Several match: ask the user which one this session belongs to.")
    if facts: L += [f"Facts for this repo ({len(facts)}; `brain.py search` for bodies):"] + [f"  - {t}" for t in facts[:15]]
    return "\n".join(L)

def main(argv):
    cwd = argv[argv.index("--cwd") + 1] if "--cwd" in argv else os.getcwd()
    repo, branch = git_info(cwd)
    ms = match(load_workstreams(), repo, branch); pick = likely(ms, branch)
    probes = [] if "--no-probes" in argv else [(p, run_probe(p)[0]) for p in load_probes()]
    print(render(repo, branch, ms, pick, probes, fact_titles(repo)))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
