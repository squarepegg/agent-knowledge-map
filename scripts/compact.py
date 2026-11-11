#!/usr/bin/env python3
"""Deterministic inbox compaction helper. Reads unprocessed inbox/*.md (entries written by `brain.py note` / capture_hook.py), proposes where
each item belongs and flags probable duplicates already in the brain. It drafts; a human/agent verifies (drafts are `verified: false`).
  compact.py                 print the plan (markdown)
  compact.py --write         also create draft files: facts/<slug>.md and decisions/<date>-<slug>.md (never overwrites an existing file)
  compact.py --archive       move the inbox files to inbox/processed/ (do this after the items are handled)
Routing: gotcha|fact -> facts/ draft; decision -> decisions/ draft; capability -> capabilities.yaml snippet; workstream -> STATE.md Progress line;
correction -> facts/user-instincts.md row (the user is the authority: fix the rejected claim wherever it is stated). Env: BRAIN_DIR."""
import datetime, glob, os, re, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import brain
B = os.environ.get("BRAIN_DIR") or os.path.dirname(HERE)
ENTRY = re.compile(r"^## \[(\w+)\] (.*)$", re.M)

def parse(text):
    """-> [{kind, title, body}] in file order. Text before the first heading is ignored."""
    ms = list(ENTRY.finditer(text)); out = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        out.append({"kind": m.group(1), "title": m.group(2).strip(), "body": text[m.end():end].strip()})
    return out

def slug(s): return brain.slugify(s)

def duplicate_of(item, brain_dir):
    """Best existing line that contains every title token (prefix match), else None. Skips the inbox itself."""
    want = [t for t in brain.tokens(item["title"]) if len(t) > 2]
    docs = [d for d in brain.corpus(brain_dir) if not d[0].startswith("inbox/")]
    for p, i, t in brain.rank(docs, want, limit=5):
        ts = brain.tokens(t)
        if all(any(w.startswith(q) for w in ts) for q in want): return f"{p}:{i}"
    return None

def draft_fact(item, today):
    return (f"---\ntitle: {item['title']}\nrepos: []\ntags: []\nanchors: []\nverified: false\nrecorded_at: '{today}'\nconfidence: low\nscope: personal\n"
            f"source: inbox {today}\n---\n{item['body'] or item['title']}\n")

def draft_decision(item, today):
    return f"# {item['title']}\ndate: {today}\nstatus: accepted\n## Context\n{item['body']}\n## Decision\n## Consequences\n"

def route(item, brain_dir, today):
    """-> (target, action_text, file_to_create|None, content|None)"""
    k, t = item["kind"], item["title"]
    if k in ("gotcha", "fact"):
        f = f"facts/{slug(t)}.md"; return f, f"new fact draft {f}", f, draft_fact(item, today)
    if k == "decision":
        f = f"decisions/{today}-{slug(t)}.md"; return f, f"new decision {f}", f, draft_decision(item, today)
    if k == "capability":
        return "capabilities.yaml", f"add entry:\n  - id: {slug(t)}\n    enables: {t}\n    requires: []\n    how: {item['body'][:120] or 'TODO'}", None, None
    if k == "workstream":
        return "workstreams/*/STATE.md", f"add to Progress (with a Verification-evidence row): {t}", None, None
    if k == "correction":
        return "facts/user-instincts.md", f"fix the rejected claim wherever it is stated, then add row: **When** ... -> **do** ... _Evidence:_ user correction {today}, high.", None, None
    return "?", f"unknown kind '{k}': classify by hand", None, None

def plan(brain_dir=None, today=None, write=False):
    brain_dir = brain_dir or B; today = today or str(datetime.date.today()); lines, created = [], []
    files = brain.inbox(brain_dir)
    for f in files:
        for item in parse(open(f, errors="ignore").read()):
            target, action, newf, content = route(item, brain_dir, today)
            dup = duplicate_of(item, brain_dir)
            lines.append(f"- [{item['kind']}] {item['title']}  ({os.path.basename(f)})\n  -> {action}" + (f"\n  !! probable duplicate of {dup}: merge instead" if dup else ""))
            if write and newf and not dup and not os.path.exists(os.path.join(brain_dir, newf)):
                os.makedirs(os.path.dirname(os.path.join(brain_dir, newf)), exist_ok=True)
                open(os.path.join(brain_dir, newf), "w").write(content); created.append(newf)
    head = f"{len(lines)} item(s) from {len(files)} inbox file(s)"
    return "\n".join([head] + lines + ([f"created: {', '.join(created)}"] if created else [])), created

def archive(brain_dir=None):
    brain_dir = brain_dir or B; os.makedirs(f"{brain_dir}/inbox/processed", exist_ok=True); moved = []
    for f in brain.inbox(brain_dir):
        shutil.move(f, f"{brain_dir}/inbox/processed/{os.path.basename(f)}"); moved.append(os.path.basename(f))
    return moved

def main(argv):
    if "--archive" in argv: print("archived:", ", ".join(archive()) or "nothing"); return 0
    out, _ = plan(write="--write" in argv); print(out); return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
