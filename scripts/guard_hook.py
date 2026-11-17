#!/usr/bin/env python3
"""Tool-call guard: a per-repo policy that a Claude Code PreToolUse hook enforces, and a replay of recorded sessions against it.
  guard_hook.py hook                         PreToolUse hook: JSON on stdin -> allow (no output), or ask / deny as hookSpecificOutput JSON.
  guard_hook.py stats [LOG]                  Summarise the decision log (default $GUARD_LOG or $BRAIN_DIR/metrics/guard.jsonl).
  guard_hook.py replay [--root DIR] [--policy FILE] [FILE|GLOB ...]
                                             Run every recorded tool call (pi/omp or Claude Code JSONL) through the policy and count what it would do.
                                             Only sessions whose cwd is under --root (default $BRAIN_REPOS_ROOT or ~/projects) are read, so company sessions never mix in.
Policy: `.agent-guard.yaml` in the repo (found by walking up to the git root), else `$BRAIN_DIR/guard.yaml`, else the built-in default. One file is the whole policy
(layered over the default, never merged with another file). Keys:
  rules:           {secrets, destructive, outside_workdir, indirection}: allow | ask | deny   (default deny / ask / ask / allow)
  allow_paths:     extra folders (beside the working folder) that count as inside; `~` expands
  allow_commands:  regexes; a shell command matching one skips destructive / outside_workdir / indirection (never secrets or deny_commands)
  deny_commands:   regexes; a matching shell command is denied
  secret_paths:    extra folders that count as secrets
Every judged call appends one line {ts, tool, action, rule, text?} to the log (text only when not allowed, redacted and cut to 100 chars); a log that cannot be written never changes the answer.
Rules are deterministic text checks, not a sandbox: a command can still build a path the text never shows (the `indirection` rule can ask about that). Opt in by adding
the hook to .claude/settings.json (docs/integrations.md); the plugin does not install it. A broken policy file makes the hook ask with the reason, never fail open."""
import datetime, glob, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import yaml
from digest_sessions import clean

ACTIONS = ("allow", "ask", "deny")
RULES = ("secrets", "destructive", "outside_workdir", "indirection")
KEYS = ("rules", "allow_paths", "allow_commands", "deny_commands", "secret_paths")
FILE = ".agent-guard.yaml"
SHELL = {"bash"}
PATH_TOOLS = {"read", "write", "edit", "multiedit", "notebookedit", "glob", "grep"}
PATH_KEYS = ("file_path", "path", "notebook_path")
HASHLINE = re.compile(r"^\[([^\]#\n]+)#[0-9A-Fa-f]{4}\]", re.M)
ROOTS = frozenset("etc usr var tmp private Users home opt bin sbin Library System Volumes dev root mnt srv Applications nix".split())
DOTDOT = re.compile(r"(^|/)\.\.(/|$)")
SPLIT = re.compile(r"[\s;|&<>()]+")
SECRET_DIRS = ("~/.ssh", "~/.aws", "~/.gnupg", "~/.config/gh", "~/.kube", "~/.docker/config.json")
SECRET_NAMES = re.compile(r"(\.env(\.(?!example$|sample$|template$)[\w.-]+)?|id_rsa|id_ed25519|\.netrc|[\w.-]+\.pem)$")
CMD = r"(?:^|[;&|(`\n]|\$\()\s*"
DESTRUCTIVE = [re.compile(p) for p in (
    CMD + r"rm\s+(?:-\S+\s+)*-\S*[rRf]", CMD + r"git\s+push\b[^;&|]*?(?:\s--force(?![-\w])|\s-f\b)", CMD + r"git\s+reset\s+[^;&|]*--hard", CMD + r"git\s+clean\b[^;&|]*\s-\w*f",
    CMD + r"git\s+checkout\b[^;&|]*\s--(?:\s|$)", CMD + r"git\s+restore\b", CMD + r"git\s+stash\b(?!\s+(?:list|show)\b)", CMD + r"sudo\b", CMD + r"(?:chmod|chown)\s+(?:-\S+\s+)*-\S*R",
    r"\b(?:curl|wget)\b[^;&]*\|\s*(?:sudo\s+)?(?:ba|z)?sh\b", r"(?i)\b(?:drop\s+(?:table|database|schema)|truncate\s+table)\b", CMD + r"kubectl\s+delete\b", CMD + r"terraform\s+destroy\b")]
EXPAND = re.compile(r"\$[A-Za-z_({]|`|\b(?:ba|z)?sh\s+-c\b|\bpython3?\s+-c\b|\bnode\s+-e\b|\bperl\s+-e\b|\b(?:python3?|node|perl|ruby)\s+-(?:\s|$)")
CMDWORD = re.compile(r"(?:^|[;&|\n]\s*)(eval|source|pushd|xargs|base64|\.)\b\s")


HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)(\w+)\1([^\n]*)\n(.*?)\n[ \t]*\2[ \t]*(?=\n|$)", re.S)
SHELL_READER = re.compile(r"\b(?:ba|z|k)?sh\b|\beval\b|\bsource\b")


class PolicyError(ValueError): pass


def _strip_heredocs(text):
    """A heredoc body is data (a file being written), not commands, unless a shell reads it: drop it so a path quoted in it is not checked."""
    def one(m):
        before = text[text.rfind("\n", 0, m.start()) + 1:m.start()]
        return m.group(0) if SHELL_READER.search(before) else m.group(3)
    return HEREDOC.sub(one, text)


def default_policy(): return {"rules": {"secrets": "deny", "destructive": "ask", "outside_workdir": "ask", "indirection": "allow"}, "allow_paths": [], "allow_commands": [], "deny_commands": [], "secret_paths": []}


def merge(user):
    """A policy mapping layered over the default -> a complete policy. Raises PolicyError on anything it does not understand."""
    if not isinstance(user, dict): raise PolicyError("policy must be a mapping")
    p = default_policy()
    for k, v in user.items():
        if k not in KEYS: raise PolicyError(f"unknown key '{k}'")
        if k == "rules":
            if not isinstance(v, dict): raise PolicyError("rules must be a mapping")
            for r, a in v.items():
                if r not in RULES: raise PolicyError(f"unknown rule '{r}'")
                if a not in ACTIONS: raise PolicyError(f"rule '{r}': action must be allow, ask or deny, not {a!r}")
                p["rules"][r] = a
        else:
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v): raise PolicyError(f"{k} must be a list of strings")
            if k.endswith("commands"):
                for x in v:
                    try: re.compile(x)
                    except re.error as e: raise PolicyError(f"{k}: bad regex {x!r}: {e}")
            p[k] = list(v)
    return p


def load_policy(cwd, brain):
    d = os.path.abspath(cwd)
    while True:
        f = os.path.join(d, FILE)
        if os.path.isfile(f): return merge(yaml.safe_load(open(f)) or {})
        if os.path.exists(os.path.join(d, ".git")) or os.path.dirname(d) == d: break
        d = os.path.dirname(d)
    f = os.path.join(brain, "guard.yaml")
    return merge(yaml.safe_load(open(f)) or {}) if os.path.isfile(f) else default_policy()


def _expand(p, home): return home + p[1:] if p == "~" or p.startswith("~/") else p
def _within(p, folder): return p == folder or p.startswith(folder.rstrip("/") + "/")


def _resolve(tok, cwd, home):
    t = _expand(tok, home)
    return os.path.normpath(t if t.startswith("/") else os.path.join(cwd, t))


def _tokens(text):
    out = []
    for t in SPLIT.split(text):
        t = t.strip("'\"")
        if t.startswith("-"): t = t.partition("=")[2].strip("'\"")   # --out=/etc/x: the value is the path
        if t: out.append(t)
    return out


def _pathish(tok):
    """Does this word name a place? Only well-known roots, `~` and `..` components count, so a sed address `/foo/p` or a URL does not."""
    if "://" in tok: return False
    if tok == "~" or tok.startswith("~/") or DOTDOT.search(tok): return True
    return tok.startswith("/") and tok.split("/")[1] in ROOTS


def _targets(call, cwd, home):
    """-> (kind, [(token, resolved path)], command text) for the call; kind is shell | path | other."""
    n, a = call["name"].lower(), call.get("args") or {}
    if n in SHELL:
        text = _strip_heredocs(str(a.get("command") or ""))
        eff = cwd if not a.get("cwd") else _resolve(str(a["cwd"]), cwd, home)
        return "shell", [(t, _resolve(t, eff, home)) for t in _tokens(text)], text, eff
    if n in PATH_TOOLS:
        raw = [str(a[k]) for k in PATH_KEYS if a.get(k)] + HASHLINE.findall(str(a.get("input") or ""))
        return "path", [(t, _resolve(t, cwd, home)) for t in raw], "", cwd
    return "other", [], "", cwd


def _is_secret(tok, resolved, dirs, home):
    return any(_within(resolved, _resolve(d, "/", home)) for d in dirs) or bool(SECRET_NAMES.match(os.path.basename(tok.rstrip("/"))))


def decide(call, cwd, policy, home):
    """-> (action, rule, reason). Strictest triggered rule wins (deny > ask > allow); ties go to the earlier of deny_commands, secrets, destructive, outside_workdir, indirection."""
    kind, toks, text, eff = _targets(call, cwd, home)
    if kind == "other": return "allow", "", ""
    hits, rules = [], policy["rules"]
    for rx in policy["deny_commands"] if kind == "shell" else ():
        m = re.search(rx, text)
        if m: hits.append(("deny", "deny_commands", f"command matches deny_commands `{m.group(0)}`"))
    secret_dirs = SECRET_DIRS + tuple(policy["secret_paths"])
    for tok, res in toks:
        if _is_secret(tok, res, secret_dirs, home): hits.append((rules["secrets"], "secrets", f"`{tok}` is a secret location")); break
    shell_free = kind == "shell" and any(re.search(rx, text) for rx in policy["allow_commands"])
    if kind == "shell" and not shell_free:
        for rx in DESTRUCTIVE:
            m = rx.search(text)
            if m: hits.append((rules["destructive"], "destructive", f"destructive command `{m.group(0).strip(' ;&|(`$')}`")); break
    inside = [cwd] + [_resolve(p, cwd, home) for p in policy["allow_paths"]]
    if not shell_free:
        out = None
        if kind == "shell" and not any(_within(eff, f) for f in inside): out = f"working folder `{eff}` is outside `{cwd}`"
        for tok, res in toks:
            if out: break
            if (kind == "path" or _pathish(tok)) and res != "/dev/null" and not any(_within(res, f) for f in inside): out = f"`{tok}` is outside the working folder"
        if out: hits.append((rules["outside_workdir"], "outside_workdir", out))
    if kind == "shell" and not shell_free:
        s = re.sub(r"'[^']*'", "''", text).replace('"$PWD"', "").replace("$PWD", "")
        m = EXPAND.search(s) or CMDWORD.search(s) or CMDWORD.search(re.sub(r"\|", "; ", s))
        if m: hits.append((rules["indirection"], "indirection", f"`{m.group(0).strip(' ;|&')}` can build a path the text does not show"))
    hits = [h for h in hits if h[0] != "allow"]
    if not hits: return "allow", "", ""
    worst = max(ACTIONS.index(h[0]) for h in hits)
    return next(h for h in hits if ACTIONS.index(h[0]) == worst)[0:3]


def _verdict(action, reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": action, "permissionDecisionReason": reason}}


def hook(raw, brain, home):
    """stdin text -> (JSON text to print ('' = no opinion), log record or None when the event is not a judged PreToolUse)."""
    try: ev = json.loads(raw)
    except ValueError: return "", None
    if not isinstance(ev, dict) or ev.get("hook_event_name") != "PreToolUse": return "", None
    cwd = ev.get("cwd") or os.getcwd()
    tool = str(ev.get("tool_name") or "")
    try: policy = load_policy(cwd, brain)
    except (PolicyError, yaml.YAMLError, OSError) as e: return json.dumps(_verdict("ask", f"guard policy invalid: {e}")), {"tool": tool, "action": "ask", "rule": "policy"}
    call = {"name": tool, "args": ev.get("tool_input") if isinstance(ev.get("tool_input"), dict) else {}}
    action, rule, reason = decide(call, cwd, policy, home)
    rec = {"tool": tool, "action": action, "rule": rule}
    if action == "allow": return "", rec
    rec["text"] = clean(call_text(call), 100)   # only what was not allowed: the log is for tuning the policy, not a transcript
    return json.dumps(_verdict(action, f"guard[{rule}]: {reason}")), rec


def log_path(brain): return os.environ.get("GUARD_LOG") or os.path.join(brain, "metrics", "guard.jsonl")


def log_line(rec, ts): return json.dumps({"ts": ts, **rec}, sort_keys=True)


def append_log(path, rec, ts):
    """Best effort: a log that cannot be written never changes what the hook answers."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a") as f: f.write(log_line(rec, ts) + "\n")
    except OSError: pass


def summarize(records):
    """Log records -> the same shape replay returns (without sessions): total, actions, rules, samples."""
    r = {"total": 0, "actions": dict.fromkeys(ACTIONS, 0), "rules": {}, "samples": []}
    for x in records:
        if not isinstance(x, dict) or x.get("action") not in ACTIONS: continue
        r["total"] += 1; r["actions"][x["action"]] += 1
        if x["action"] != "allow": r["rules"][x.get("rule", "")] = r["rules"].get(x.get("rule", ""), 0) + 1; r["samples"].append((x.get("rule", ""), x["action"], str(x.get("text", ""))))
    return r


def report(r, header):
    a = r["actions"]
    print(header)
    print("  ".join(f"{k} {a[k]}" for k in ACTIONS))
    print("rules: " + (", ".join(f"{k} {v}" for k, v in sorted(r["rules"].items())) or "none"))
    seen = {}
    for rule, action, text in r["samples"]:
        key = (rule, action, " ".join(text.split()[:2])); seen[key] = seen.get(key, 0) + 1
    for (rule, action, head), n in sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))[:15]: print(f"  {n:4d} {action:4s} {rule:16s} {head}")


def _stats_cli(argv):
    path = argv[0] if argv else log_path(os.environ.get("BRAIN_DIR") or os.path.dirname(HERE))
    if not os.path.isfile(path): print(f"no log at {path}"); return 1
    rows = []
    for line in open(path, errors="ignore"):
        try: rows.append(json.loads(line))
        except ValueError: pass
    r = summarize(rows); report(r, f"{r['total']} calls logged ({path})"); return 0


def session_calls(path):
    """pi/omp or Claude Code JSONL -> (cwd, [call]). Unreadable lines are skipped."""
    cwd, calls = "", []
    for line in open(path, errors="ignore"):
        try: e = json.loads(line)
        except ValueError: continue
        if not isinstance(e, dict): continue
        cwd = cwd or str(e.get("cwd") or "")
        m = e.get("message") if isinstance(e.get("message"), dict) else {}
        for b in m.get("content") or [] if m.get("role") == "assistant" else []:
            if not isinstance(b, dict): continue
            if b.get("type") == "toolCall": calls.append({"name": str(b.get("name")), "args": b.get("arguments") or {}})
            elif b.get("type") == "tool_use": calls.append({"name": str(b.get("name")), "args": b.get("input") or {}})
    return cwd, calls


def call_text(c): a = c["args"]; return str(a.get("command") or a.get("file_path") or a.get("path") or a.get("input") or "")


def replay(files, root, policy, home):
    root = os.path.abspath(root); r = {"total": 0, "sessions": 0, "skipped": 0, "actions": dict.fromkeys(ACTIONS, 0), "rules": {}, "samples": []}
    for f in files:
        cwd, calls = session_calls(f)
        if not cwd or not _within(os.path.abspath(cwd), root): r["skipped"] += 1; continue
        r["sessions"] += 1
        for c in calls:
            action, rule, _ = decide(c, cwd, policy, home)
            r["total"] += 1; r["actions"][action] += 1
            if action != "allow": r["rules"][rule] = r["rules"].get(rule, 0) + 1; r["samples"].append((rule, action, clean(call_text(c), 100)))
    return r


def _replay_cli(argv):
    root, policy, files, i = os.environ.get("BRAIN_REPOS_ROOT") or os.path.expanduser("~/projects"), None, [], 0
    while i < len(argv):
        if argv[i] == "--root": root = argv[i + 1]; i += 2
        elif argv[i] == "--policy": policy = merge(yaml.safe_load(open(argv[i + 1])) or {}); i += 2
        else: files += sorted(glob.glob(os.path.expanduser(argv[i]))); i += 1
    if not files: files = sorted(sum((glob.glob(os.path.expanduser(g)) for g in ("~/.omp/agent/sessions/*/*.jsonl", "~/.pi/agent/sessions/*/*.jsonl", "~/.claude/projects/*/*.jsonl")), []))
    r = replay(files, root, policy or default_policy(), os.path.expanduser("~"))
    report(r, f"{r['total']} calls in {r['sessions']} sessions ({r['skipped']} skipped: cwd outside {root})")
    return 0


def main(argv):
    if argv[:1] == ["hook"]:
        brain = os.environ.get("BRAIN_DIR") or os.path.dirname(HERE)
        out, rec = hook(sys.stdin.read(), brain, os.path.expanduser("~"))
        if rec: append_log(log_path(brain), rec, datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        if out: print(out)
        return 0
    if argv[:1] == ["replay"]: return _replay_cli(argv[1:])
    if argv[:1] == ["stats"]: return _stats_cli(argv[1:])
    print(__doc__.split("Policy:")[0]); return 2


if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
