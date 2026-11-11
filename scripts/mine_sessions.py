#!/usr/bin/env python3
"""Turn session digests into candidate learnings, deterministically (no model). Reads digests/*.txt written by digest_sessions.py and proposes:
  - gotcha      an error that recurs in >= --min distinct sessions (the same failure, normalised: numbers, ids, paths, hashes and quoted values removed)
  - correction  a user message that pushes back ("that's wrong", "I already told you ...") seen in any session
Candidates that look like something the brain already knows (every title word appears on a line of an existing fact/decision/skill/doc) or are already
in the inbox are dropped. Nothing is written unless --write; written entries go to the inbox as `## [kind] title`, to be verified through the normal
compaction path (`brain.py compact`) - they are leads, not facts.
  mine_sessions.py [DIGEST_DIR] [--min 2] [--write] [--top 20]
Env: BRAIN_DIR (digests default to $BRAIN_DIR/digests)."""
import glob, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import brain, capture_hook, compact
B = os.environ.get("BRAIN_DIR") or os.path.dirname(HERE)

URL = re.compile(r"https?://\S+"); UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"); HEX = re.compile(r"\b[0-9a-f]{7,}\b")
PATH = re.compile(r"(?:~|\.{1,2})?/[\w.\-@+/]+"); QUOTED = re.compile(r"""(["'`])[^"'`]*\1"""); NUM = re.compile(r"\b\d+(?:\.\d+)*\b")
MIN_LEN = 12

def normalize_error(line):
    """One ERR digest line -> a stable key for 'the same failure' ('' if too short to mean anything)."""
    body = line[4:] if line.startswith("ERR ") else line
    body = body.split("=>", 1)[1] if "=>" in body else body
    t = body.lower()
    for rx, rep in ((URL, "<url>"), (UUID, "<id>"), (QUOTED, "<q>"), (PATH, "<path>"), (HEX, "<hex>"), (NUM, "<n>")): t = rx.sub(rep, t)
    t = re.sub(r"\s+", " ", t).strip(" .:;,-")[:90]
    return t if len(t) >= MIN_LEN else ""

def parse_digest(text):
    """-> (error lines, user lines) of one digest file."""
    errs, users = [], []
    for l in text.splitlines():
        if l.startswith("ERR "): errs.append(l)
        elif l.startswith("USER: "): users.append(l[6:])
    return errs, users

def aggregate(sessions, min_sessions=2):
    """sessions: {name: digest text}. -> [{kind, title, body, count}] ordered by count desc then title."""
    err_sessions, err_example, corr = {}, {}, {}
    for name, text in sessions.items():
        errs, users = parse_digest(text)
        for l in errs:
            k = normalize_error(l)
            if k: err_sessions.setdefault(k, set()).add(name); err_example.setdefault(k, l[:200])
        for u in users:
            if capture_hook.is_correction(u):
                k = re.sub(r"\s+", " ", u).strip()[:capture_hook.MAXLEN]; corr.setdefault(k, set()).add(name)
    out = [{"kind": "gotcha", "title": f"Recurring error: {k}", "body": f"seen in {len(s)} sessions; example: {err_example[k]}", "count": len(s)} for k, s in err_sessions.items() if len(s) >= min_sessions]
    out += [{"kind": "correction", "title": k, "body": f"user pushed back in {len(s)} session(s); verify, then fix the claim it rejects", "count": len(s)} for k, s in corr.items()]
    return sorted(out, key=lambda c: (-c["count"], c["title"]))

def known(cand, brain_dir):
    """True if the brain already says it (all title words on one line of a non-inbox doc) or the inbox already has the same title."""
    title = re.sub(r"^Recurring error:\s*", "", cand["title"])
    for f in glob.glob(f"{brain_dir}/inbox/*.md"):
        if f"] {cand['title']}" in open(f, errors="ignore").read(): return True
    return compact.duplicate_of({"title": title}, brain_dir) is not None

def run(digest_dir, brain_dir=None, min_sessions=2, top=20):
    brain_dir = brain_dir or B
    sessions = {os.path.basename(p): open(p, errors="ignore").read() for p in sorted(glob.glob(os.path.join(digest_dir, "*.txt")))}
    return [c for c in aggregate(sessions, min_sessions) if not known(c, brain_dir)][:top], len(sessions)

def main(argv):
    opt = lambda k, d: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    flags_with_value = {"--min", "--top"}
    pos = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in flags_with_value)]
    ddir = pos[0] if pos else os.path.join(B, "digests")
    cands, n = run(ddir, B, int(opt("--min", 2)), int(opt("--top", 20)))
    print(f"{n} digest(s), {len(cands)} new candidate(s)")
    for c in cands: print(f"- [{c['kind']}] x{c['count']} {c['title']}")
    if "--write" in argv:
        for c in cands: brain.note(c["kind"], c["title"], c["body"], brain=B)
        print(f"wrote {len(cands)} inbox entr{'y' if len(cands) == 1 else 'ies'}" if cands else "nothing to write")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
