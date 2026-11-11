#!/usr/bin/env python3
"""Agent-readiness check for a repo (idea from walkinglabs/learn-harness-engineering validate-harness).
Usage: harness_check.py [DIR ...] [--all] [--min N] [--json]
--all scans every git repo directly under $BRAIN_REPOS_ROOT (default ~/projects). Exit 1 if any repo scores below --min (default 60).
Five subsystems, 2 checks each (10 points -> %). Heuristic: keyword/file presence, not proof."""
import json, os, re, sys
from pathlib import Path

def rd(p):
    try: return p.read_text(errors="ignore")
    except Exception: return ""

def has(t, *words): return any(re.search(w, t, re.I) for w in words)

def check(repo: Path):
    ins = next((rd(repo / n) for n in ("AGENTS.md", "CLAUDE.md") if (repo / n).exists()), "")
    ci = "\n".join(rd(p) for p in (repo / ".github/workflows").glob("*.y*ml"))   # glob on a missing dir yields nothing
    readme = rd(repo / "README.md")
    entry = any((repo / n).exists() for n in ("init.sh", "Makefile", "justfile", "package.json", "gradlew", "pyproject.toml", "tox.ini"))
    c = {
        "instructions": [("AGENTS.md/CLAUDE.md exists", bool(ins)),
                         ("states build/test commands", has(ins, r"\b(test|pytest|gradlew|npm|make|cargo|dotnet)\b"))],
        "state": [("progress/handoff routed (STATE/progress/handoff)", has(ins, "STATE.md", "progress", "handoff")),
                  ("docs/ or openspec/ present", (repo / "docs").is_dir() or (repo / "openspec").is_dir())],
        "verification": [("single verify entrypoint (init.sh/Makefile/package.json/gradlew/pyproject)", entry),
                         ("tests run in CI", has(ci, r"\b(test|pytest|gradlew|unittest|npm)\b"))],
        "scope": [("definition of done / scope documented", has(ins, "definition of done", "done when", "scope", "do not", "never")),
                  ("CODEOWNERS or README ownership", (repo / ".github/CODEOWNERS").exists() or (repo / "CODEOWNERS").exists() or has(readme, "owner"))],
        "lifecycle": [("init.sh (green-baseline check before editing)", (repo / "init.sh").exists()),
                      ("end-of-session / evidence rule", has(ins, "evidence", "end of session", "before (ending|finishing)", "clean state"))],
    }
    sub = {k: sum(p for _, p in v) for k, v in c.items()}
    return {"repo": repo.name, "score": sum(sub.values()) * 10, "sub": sub,
            "missing": [f"{k}: {m}" for k, v in c.items() for m, p in v if not p]}

def parse(a):
    """argv -> (dirs, min, all, json). Raises SystemExit(2) on a bad --min."""
    mn, dirs, skip = 60, [], False
    for i, x in enumerate(a):
        if skip: skip = False; continue
        if x == "--min":
            try: mn = int(a[i + 1])
            except (IndexError, ValueError): sys.exit("harness_check: --min needs an integer")
            skip = True
        elif not x.startswith("--"): dirs.append(x)
    return dirs, mn, "--all" in a, "--json" in a

def run(a, home=None):
    """Returns (exit_code, output). Deterministic: sorted by (score, repo name); no clock, no network."""
    dirs, mn, all_, js = parse(a)
    if all_:
        base = Path(os.environ["BRAIN_REPOS_ROOT"]).expanduser() if os.environ.get("BRAIN_REPOS_ROOT") else (home or Path.home()) / "projects"
        dirs += [str(p) for p in base.iterdir() if (p / ".git").exists()]
    for d in dirs or ["."]:
        if not Path(d).expanduser().is_dir(): return 2, f"harness_check: not a directory: {d}"
    res = sorted((check(Path(d).expanduser()) for d in (dirs or ["."])), key=lambda r: (r["score"], r["repo"]))
    out = json.dumps(res, indent=1, sort_keys=True) if js else "\n".join(
        f"{r['score']:3d}  {r['repo']:50s} " + "; ".join(r["missing"][:3]) for r in res)
    return (1 if any(r["score"] < mn for r in res) else 0), out

if __name__ == "__main__":
    code, out = run(sys.argv[1:])
    print(out)
    sys.exit(code)
