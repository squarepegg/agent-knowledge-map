#!/usr/bin/env python3
"""Fail (exit 1) if any generated catalog is older than its budget - proves the job that refreshes it is still running.
Config freshness.yaml: a list of {name, file (relative to the brain), key (dotted path to an ISO timestamp, default 'synced'), budget_hours}.
A missing file or unparseable timestamp counts as stale. Env: BRAIN_DIR."""
import datetime, json, os, sys
import yaml
B = os.environ.get("BRAIN_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def parse_ts(v):
    try:
        t = datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)
    except Exception: return None

def dig(obj, dotted):
    for k in dotted.split("."):
        if not isinstance(obj, dict): return None
        obj = obj.get(k)
    return obj

def evaluate(entries, now, brain=None):
    """-> list of (name, age_hours|None, budget_hours, ok)"""
    out = []
    for e in entries:
        try: data = json.load(open(os.path.join(brain or B, e["file"])))
        except Exception: data = None
        ts = parse_ts(dig(data, e.get("key", "synced"))) if data is not None else None
        age = None if ts is None else (now - ts).total_seconds() / 3600
        out.append((e["name"], age, e["budget_hours"], age is not None and age <= e["budget_hours"]))
    return out

def main():
    p = os.path.join(B, "freshness.yaml")
    entries = (yaml.safe_load(open(p)) or []) if os.path.exists(p) else []
    res = evaluate(entries, datetime.datetime.now(datetime.timezone.utc))
    for name, age, budget, ok in res: print(f"{'ok   ' if ok else 'STALE'} {name}: " + ("missing/unparseable" if age is None else f"{age:.0f}h old") + f" (budget {budget}h)")
    return 0 if all(r[3] for r in res) else 1

if __name__ == "__main__":
    sys.exit(main())
