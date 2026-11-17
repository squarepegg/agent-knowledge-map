#!/usr/bin/env python3
"""Deterministic inbox compaction helper. Reads unprocessed inbox/*.md (entries written by `brain.py note` / capture_hook.py), proposes where
each item belongs and flags probable duplicates already in the brain. It drafts; a human/agent verifies (drafts are `verified: false`).
  compact.py                 print the plan (markdown)
  compact.py --write         also create draft files: facts/<slug>.md and decisions/<date>-<slug>.md (never overwrites an existing file)
  compact.py --archive       move the inbox files to inbox/processed/ (do this after the items are handled)
Items that cluster.py judges to be the same recurring problem are annotated (`~~`) and each draft lists its siblings' own title and body under
"Related attempts": nothing is merged or dropped (grouping is a suggestion; evals/cluster.yaml measures how good). Routing: gotcha|fact -> facts/ draft; decision -> decisions/ draft; capability -> capabilities.yaml snippet; workstream -> STATE.md Progress line;
correction -> facts/user-instincts.md row (the user is the authority: fix the rejected claim wherever it is stated). Env: BRAIN_DIR."""
import datetime, glob, os, re, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import brain, cluster
import _records
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

def related(items):
    """-> {index: [sibling indexes]} for items that cluster.py puts in the same recurring-problem group."""
    return {i: [j for j in g if j != i] for g in cluster.cluster(items) if len(g) > 1 for i in g}

def attempts_text(siblings):
    """Every sibling's own title and body, verbatim: grouping must never drop an attempt's rationale or outcome."""
    return "\n\n## Related attempts (same recurring problem; verify each)\n" + "\n".join(
        f"- [{s['kind']}] {s['title']}" + (f": {s['body']}" if s['body'] else "") for s in siblings) + "\n"

def draft_fact(item, today, siblings=()):
    fm = dict(record_version=1, title=item['title'], repos=[], tags=[], anchors=[], verified=False,
              recorded_at=today, confidence='low', scope='personal', source=f'inbox {today}')
    errors = _records.validate(fm, 'fact', _records.date(today))
    if errors: raise _records.RecordError('; '.join(errors))
    text = _records.render(fm, (item['body'] or item['title']) + ('\n' + attempts_text(siblings).rstrip('\n') if siblings else '') + '\n')
    if _records.SECRET.search(text): raise _records.RecordError('refusing secret-like content')
    return text

def draft_decision(item, today, siblings=()):
    return (f"# {item['title']}\ndate: {today}\nstatus: accepted\n## Context\n{item['body']}\n## Decision\n## Consequences\n## Predicted outcome\n## Observed\n"
            + (attempts_text(siblings) if siblings else ""))

def route(item, brain_dir, today, siblings=()):
    """-> (target, action_text, file_to_create|None, content|None)"""
    k, t = item["kind"], item["title"]
    if k in ("gotcha", "fact"):
        f = f"facts/{slug(t)}.md"; return f, f"new fact draft {f}", f, draft_fact(item, today, siblings)
    if k == "decision":
        f = f"decisions/{today}-{slug(t)}.md"; return f, f"new decision {f}", f, draft_decision(item, today, siblings)
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
    items = [(f, it) for f in files for it in parse(open(f, errors="ignore").read())]
    rel = related([it for _, it in items])
    dups = [duplicate_of(it, brain_dir) for _, it in items]   # before any draft is written: this run's own drafts list their siblings
    for n, (f, item) in enumerate(items):
        sib = [items[j][1] for j in rel.get(n, [])]
        target, action, newf, content = route(item, brain_dir, today, sib)
        dup = dups[n]
        lines.append(f"- [{item['kind']}] {item['title']}  ({os.path.basename(f)})\n  -> {action}" + (f"\n  !! probable duplicate of {dup}: merge instead" if dup else "")
                     + (f"\n  ~~ same recurring problem as: {'; '.join(s['title'] for s in sib)}" if sib else ""))
        if write and newf and not dup and not os.path.exists(os.path.join(brain_dir, newf)):
            _records.contained_path(brain_dir, os.path.join(brain_dir, newf))
            os.makedirs(os.path.dirname(os.path.join(brain_dir, newf)), exist_ok=True)
            open(os.path.join(brain_dir, newf), "w").write(content); created.append(newf)
    groups = len({tuple(sorted([n] + v)) for n, v in rel.items()})
    head = f"{len(lines)} item(s) from {len(files)} inbox file(s)" + (f"; {groups} recurring-problem group(s)" if groups else "")
    return "\n".join([head] + lines + ([f"created: {', '.join(created)}"] if created else [])), created

def archive(brain_dir=None):
    brain_dir = brain_dir or B; os.makedirs(f"{brain_dir}/inbox/processed", exist_ok=True); moved = []
    for f in brain.inbox(brain_dir):
        shutil.move(f, f"{brain_dir}/inbox/processed/{os.path.basename(f)}"); moved.append(os.path.basename(f))
    return moved

def main(argv):
    if "--archive" in argv: print("archived:", ", ".join(archive()) or "nothing"); return 0
    try:
        out, _ = plan(write="--write" in argv); print(out); return 0
    except (OSError, _records.RecordError) as e:
        print('refusing: ' + str(e), file=sys.stderr); return 2

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
