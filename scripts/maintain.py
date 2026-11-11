#!/usr/bin/env python3
"""Scheduler-agnostic upkeep runner: runs the steps in maintenance.yaml in order, records status/maintenance.json
(per-step ok|failed|skipped, failed list, timestamp), optionally commits knowledge paths. Exit 1 if any step failed.
  maintain.py [--only name ...] [--weekday N]        (cron / launchd / GitHub Actions all just call this)
A failing step never stops the others; the status file is how you notice. Env: BRAIN_DIR."""
import datetime, json, os, subprocess, sys
import yaml
B = os.environ.get("BRAIN_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def due(step, weekday): return not step.get("weekday") or int(step["weekday"]) == weekday

def run_steps(steps, weekday, only=None, cwd=None):
    res = {}
    for s in steps:
        if only and s["name"] not in only: continue
        if not due(s, weekday): res[s["name"]] = "skipped"; continue
        try: ok = subprocess.run(s["cmd"], cwd=cwd or B, timeout=s.get("timeout", 900), capture_output=True, text=True).returncode == 0
        except Exception: ok = False
        res[s["name"]] = "ok" if ok else "failed"
        print(f"{res[s['name']]:7} {s['name']}", flush=True)
    return res

def write_status(res, brain=None):
    os.makedirs(os.path.join(brain or B, "status"), exist_ok=True)
    doc = {"at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "steps": res, "failed": sorted(k for k, v in res.items() if v == "failed")}
    json.dump(doc, open(os.path.join(brain or B, "status", "maintenance.json"), "w"), indent=1)
    return doc

def commit(paths, cwd):
    existing = [p for p in paths if os.path.exists(os.path.join(cwd, p))]
    subprocess.run(["git", "add", "--", *existing], cwd=cwd, capture_output=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=cwd).returncode == 0: return False
    subprocess.run(["git", "commit", "-qm", "brain upkeep"], cwd=cwd, check=True)
    subprocess.run(["git", "push", "-q"], cwd=cwd, capture_output=True)
    return True

def main(argv):
    cfg = yaml.safe_load(open(os.path.join(B, "maintenance.yaml"))) or {}
    weekday = int(argv[argv.index("--weekday") + 1]) if "--weekday" in argv else datetime.date.today().isoweekday()
    only = [a for a in argv[1:] if not a.startswith("--") and not a.isdigit()] if "--only" in argv else None
    res = run_steps(cfg.get("steps") or [], weekday, only)
    doc = write_status(res)
    if cfg.get("commit") and not doc["failed"]: commit(cfg.get("commit_paths") or [], B)
    return 1 if doc["failed"] else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
