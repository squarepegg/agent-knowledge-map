#!/usr/bin/env python3
"""Shared attempt log for the eval runners (eval_run, recall_eval, agentic_eval).
Every graded attempt is appended to metrics/attempts/<eval>.jsonl as soon as it finishes, with a key over
everything that decides the result: eval name, fixture contents, grader source, brain state (git HEAD + uncommitted
diff + untracked files, metrics/ excluded so the runs' own outputs do not change it), and the agent command. Same key = same experiment, so `--resume` can reuse it instead of paying again.
A run writes a run_start and a run_end line; a start with no end is a crashed or aborted run.
migration_triggers() computes the deterministic gate for moving to one shared harness (see evals/README.md)."""
import datetime, hashlib, inspect, json, os, subprocess, time, uuid

def _h(*parts):
    return hashlib.sha256("\x00".join(str(p) for p in parts).encode()).hexdigest()[:16]

def grader_version(*fns):
    """Hash of the grading functions' source: a grader edit changes every key, so old scores are never mixed with new ones."""
    return _h(*(inspect.getsource(f) for f in fns))

def brain_state(brain_dir):
    """Content hash of the brain worktree, or None when it is not a git repo (then nothing is ever reused)."""
    def git(*a):
        p = subprocess.run(["git", "-C", brain_dir, *a], capture_output=True, text=True, timeout=30)
        if p.returncode: raise RuntimeError(p.stderr)
        return p.stdout
    try:
        head, diff = git("rev-parse", "HEAD").strip(), git("diff", "HEAD", "--binary", "--", ".", ":(exclude)metrics")
        untracked = []
        for f in sorted(git("ls-files", "--others", "--exclude-standard", "-z", "--", ".", ":(exclude)metrics").split("\0")):
            if f:
                try: untracked.append(f + ":" + hashlib.sha256(open(os.path.join(brain_dir, f), "rb").read()).hexdigest())
                except OSError: untracked.append(f + ":?")
        return _h(head, diff, *untracked)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return None

class Log:
    def __init__(self, brain_dir, name, grader, agent=""):
        self.brain_dir, self.name, self.grader, self.agent = brain_dir, name, grader, agent
        self.dir = os.path.join(brain_dir, "metrics", "attempts"); self.path = os.path.join(self.dir, f"{name}.jsonl")
        self.state = brain_state(brain_dir); self.run_id = uuid.uuid4().hex[:12]; self.t0 = time.time()

    def _write(self, rec):
        os.makedirs(self.dir, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n"); f.flush(); os.fsync(f.fileno())

    def _now(self):
        return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    def key(self, fixture):
        if self.state is None: return None
        return _h(self.name, json.dumps(fixture, sort_keys=True, default=str), self.grader, self.state, self.agent)

    def start(self):
        self._write({"type": "run_start", "run": self.run_id, "at": self._now(), "eval": self.name, "grader": self.grader, "brain": self.state, "agent": self.agent})

    def end(self, summary):
        self._write({"type": "run_end", "run": self.run_id, "at": self._now(), "secs": round(time.time() - self.t0, 1), "summary": summary})

    def record(self, fixture, result, secs):
        self._write({"type": "attempt", "run": self.run_id, "at": self._now(), "key": self.key(fixture), "id": fixture.get("id") or fixture.get("q"),
                     "secs": round(secs, 2), "result": result})

    def cached(self):
        """key -> last recorded result for this eval (only keyed attempts; a None key never matches)."""
        out = {}
        for r in read(self.path):
            if r.get("type") == "attempt" and r.get("key"): out[r["key"]] = r["result"]
        return out

def read(path):
    if not os.path.exists(path): return []
    out = []
    for line in open(path):
        try: out.append(json.loads(line))
        except ValueError: pass   # a torn last line from a crash is skipped, not fatal
    return out

def migration_triggers(brain_dir, eval_types_max=None, run_minutes_max=None, incomplete_max=None):
    """Deterministic gate: which triggers for migrating to one shared harness have fired. Thresholds via env
    EVAL_TRIGGER_TYPES (5), EVAL_TRIGGER_RUN_MIN (30), EVAL_TRIGGER_INCOMPLETE (2)."""
    types_max = eval_types_max or int(os.environ.get("EVAL_TRIGGER_TYPES", 5))
    minutes_max = run_minutes_max or float(os.environ.get("EVAL_TRIGGER_RUN_MIN", 30))
    inc_max = incomplete_max or int(os.environ.get("EVAL_TRIGGER_INCOMPLETE", 2))
    fired = []
    ev = os.path.join(brain_dir, "evals")
    n = len([f for f in os.listdir(ev) if f.endswith(".yaml")]) if os.path.isdir(ev) else 0
    if n >= types_max: fired.append(f"eval types {n} >= {types_max}")
    adir = os.path.join(brain_dir, "metrics", "attempts")
    for f in sorted(os.listdir(adir)) if os.path.isdir(adir) else []:
        if not f.endswith(".jsonl"): continue
        recs = read(os.path.join(adir, f)); ended = {r["run"]: r for r in recs if r.get("type") == "run_end"}
        starts = [r for r in recs if r.get("type") == "run_start"]
        incomplete = [r for r in starts[:-1] if r["run"] not in ended]   # the newest start may still be running
        if len(incomplete) >= inc_max: fired.append(f"{f[:-6]}: {len(incomplete)} runs never finished (crash/abort) >= {inc_max}")
        slow = [r for r in ended.values() if r.get("secs", 0) / 60 > minutes_max]
        if slow: fired.append(f"{f[:-6]}: a full run took {max(r['secs'] for r in slow) / 60:.0f} min > {minutes_max:.0f}")
    return fired

def report_triggers(brain_dir):
    for t in migration_triggers(brain_dir): print(f"migration trigger fired: {t} (see evals/README.md)")
