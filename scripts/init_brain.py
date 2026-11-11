#!/usr/bin/env python3
"""One-command setup. Idempotent: running it twice changes nothing the second time.
  init_brain.py [--org NAME] [--role TEXT] [--no-examples] [--example NAME [--force]] [--claude] [--home DIR]
Always: sets org/role in brain.config.yaml, optionally removes the example fact/workstream/glossary/capability entries, builds PRIMER.md.
--claude also wires Claude Code under --home (default ~): imports PRIMER.md in .claude/CLAUDE.md, symlinks skills/* into .claude/skills/,
adds SessionStart / Stop / UserPromptSubmit hooks (session_start.py, capture_hook.py) to .claude/settings.json (merged; existing hooks kept).
--example NAME copies examples/NAME (config, glossary, capabilities, probes, facts, workstreams, decisions) into the brain, removes the placeholder
content and appends the example's eval questions. Files you already changed are never overwritten (use --force); files still identical to the shipped
template (tests/fixtures/brain) are replaced. Prints every action taken. Env: BRAIN_DIR."""
import datetime, json, os, re, shutil, subprocess, sys
import yaml
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
B = os.environ.get("BRAIN_DIR") or os.path.dirname(HERE)

def set_config(brain, org=None, role=None):
    p = os.path.join(brain, "brain.config.yaml"); text = open(p).read(); acts = []
    for key, val in (("org", org), ("role", role)):
        if val is None: continue
        new = re.sub(rf"^{key}:.*$", f"{key}: {json.dumps(val)}", text, count=1, flags=re.M)
        if new != text: acts.append(f"config {key} = {val}"); text = new
    open(p, "w").write(text); return acts

def remove_examples(brain):
    acts = []
    for rel in ("facts/example-fact.md", "workstreams/example-workstream"):
        p = os.path.join(brain, rel)
        if os.path.isdir(p): shutil.rmtree(p); acts.append(f"removed {rel}")
        elif os.path.exists(p): os.remove(p); acts.append(f"removed {rel}")
    for rel, key, val in (("glossary.yaml", "term", "Example Service"), ("capabilities.yaml", "id", "example-capability")):
        p = os.path.join(brain, rel); items = yaml.safe_load(open(p)) or []
        kept = [i for i in items if i.get(key) != val]
        if len(kept) != len(items): open(p, "w").write(yaml.safe_dump(kept, sort_keys=False) if kept else "[]\n"); acts.append(f"removed example from {rel}")
    return acts

def examples_available(brain):
    d = os.path.join(brain, "examples")
    return sorted(n for n in os.listdir(d) if os.path.isdir(os.path.join(d, n))) if os.path.isdir(d) else []

def _same(a, b):
    try: return open(a, "rb").read() == open(b, "rb").read()
    except OSError: return False

def _stamp(rel, data, today):
    """Example dates are illustrative: stamp verified_at / updated with today so a fresh example lints clean (you replace the content with your own)."""
    if not (rel.startswith(("facts" + os.sep, "workstreams" + os.sep)) and rel.endswith(".md")): return data
    return re.sub(rb"^(verified_at|updated): .*$", lambda m: m.group(1) + b": '" + today.encode() + b"'", data, count=1, flags=re.M)

def _append_list(src, dst, key, name):
    """Append the entries of YAML list `src` whose `key` is not yet in `dst` (created if missing). -> number appended."""
    if not os.path.exists(src): return 0
    new = yaml.safe_load(open(src)) or []; have = {e.get(key) for e in ((yaml.safe_load(open(dst)) if os.path.exists(dst) else None) or [])}
    add = [e for e in new if e.get(key) not in have]
    if add:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "a") as f: f.write(f"# --- example: {name} ---\n" + yaml.safe_dump(add, sort_keys=False, width=200))
    return len(add)

def apply_example(brain, name, force=False, today=None):
    """Copy examples/<name> into the brain. -> list of action strings. Raises SystemExit on an unknown example."""
    src = os.path.join(brain, "examples", name)
    today = today or datetime.date.today().isoformat()
    if name not in examples_available(brain): raise SystemExit(f"unknown example '{name}'. available: {', '.join(examples_available(brain)) or 'none'}")
    acts = []; pristine = os.path.join(brain, "tests", "fixtures", "brain")
    for dp, _, fns in sorted(os.walk(src)):
        for fn in sorted(fns):
            s_path = os.path.join(dp, fn); rel = os.path.relpath(s_path, src)
            if rel.startswith("evals" + os.sep): continue
            d_path = os.path.join(brain, rel); data = _stamp(rel, open(s_path, "rb").read(), today)
            if not os.path.exists(d_path): action = "added"
            elif open(d_path, "rb").read() == data: continue
            elif force or _same(d_path, os.path.join(pristine, rel)): action = "replaced"
            else: acts.append(f"kept your {rel} (use --force to overwrite)"); continue
            os.makedirs(os.path.dirname(d_path), exist_ok=True); open(d_path, "wb").write(data); acts.append(f"{action} {rel}")
    acts += remove_examples(brain)   # placeholders (also those left inside files you kept)
    for fname, key, label in (("questions.yaml", "id", "eval question(s)"), ("recall.yaml", "q", "recall query(ies)")):
        n = _append_list(os.path.join(src, "evals", fname), os.path.join(brain, "evals", fname), key, name)
        if n: acts.append(f"appended {n} {label}")
    return acts

def wire_claude(brain, home):
    cdir = os.path.join(home, ".claude"); os.makedirs(os.path.join(cdir, "skills"), exist_ok=True); acts = []
    md = os.path.join(cdir, "CLAUDE.md"); line = f"@{os.path.join(brain, 'PRIMER.md')}"
    cur = open(md).read() if os.path.exists(md) else ""
    if line not in cur.splitlines():
        open(md, "w").write(cur + ("" if not cur or cur.endswith("\n") else "\n") + line + "\n"); acts.append(f"CLAUDE.md imports {line}")
    sk = os.path.join(brain, "skills")
    for name in sorted(os.listdir(sk)) if os.path.isdir(sk) else []:
        src, dst = os.path.join(sk, name), os.path.join(cdir, "skills", name)
        if os.path.isdir(src) and not os.path.lexists(dst): os.symlink(src, dst); acts.append(f"linked skill {name}")
    sp = os.path.join(cdir, "settings.json")
    try: settings = json.load(open(sp))
    except Exception: settings = {}
    py = "python3 " + os.path.join(brain, "scripts")
    wanted = {"SessionStart": f"{py}/session_start.py", "Stop": f"{py}/capture_hook.py stop", "UserPromptSubmit": f"{py}/capture_hook.py prompt"}
    hooks = settings.setdefault("hooks", {})
    for event, cmd in wanted.items():
        groups = hooks.setdefault(event, [])
        if not any(h.get("command") == cmd for g in groups for h in g.get("hooks", [])):
            groups.append({"hooks": [{"type": "command", "command": cmd}]}); acts.append(f"hook {event}")
    if acts and any(a.startswith("hook") for a in acts): json.dump(settings, open(sp, "w"), indent=2)
    return acts

def main(argv):
    opt = lambda k: argv[argv.index(k) + 1] if k in argv else None  # noqa: E731
    acts = set_config(B, opt("--org"), opt("--role"))
    if "--example" in argv: acts += apply_example(B, opt("--example"), "--force" in argv)
    elif "--no-examples" in argv: acts += remove_examples(B)
    if "--claude" in argv: acts += wire_claude(B, os.path.expanduser(opt("--home") or "~"))
    r = subprocess.run([sys.executable, os.path.join(HERE, "build_primer.py")], capture_output=True, text=True, env={**os.environ, "BRAIN_DIR": B})
    acts.append(r.stdout.strip() or "primer failed: " + r.stderr.strip())
    print("\n".join(acts) or "nothing to do")
    if "--claude" not in argv: print("Next: import PRIMER.md in your agent's global instructions (see docs/integrations.md), or re-run with --claude.")
    return 0 if r.returncode == 0 else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
