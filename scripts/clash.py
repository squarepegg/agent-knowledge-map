#!/usr/bin/env python3
"""Context-clash check: two documents (facts, skills) that give opposite directives about the same `backticked` object.
  clash.py [--strict]     Env: BRAIN_DIR. Prints one line per clash; --strict exits 1 if any.
Why: an agent that loads "use `rsync`" from a skill and "never use `rsync`" from a fact has no way to pick; stale-anchor lint cannot see it.
Heuristic with precision over recall: a directive is a sentence with a directive word (always/must/use/run/prefer = +, never/do not/don't/must not/
should not/avoid = -) followed within WINDOW characters by backticked objects; every backticked object in that sentence takes the polarity. Misses
clashes stated in prose. A `## Counterexamples` section is ignored. Docs whose `repos:` are both non-empty and disjoint are different scopes.
Resolve a deliberate pair with `clash_ok: [object]` in either document's frontmatter."""
import glob, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from _fm import frontmatter

WINDOW = 40
NEG = re.compile(r"\b(never|do not|don'?t|must not|should not|avoid)\b", re.I)
POS = re.compile(r"\b(always|must|should|use|run|prefer)\b", re.I)
TICK = re.compile(r"`([^`\n]+)`")
SPLIT = re.compile(r"[.;!?\n]+")
HEADING = re.compile(r"^#{1,6}\s+(.*)$")


def norm(obj): return " ".join(obj.lower().split())


def _without_counterexamples(text):
    out, skip = [], False
    for line in text.splitlines():
        m = HEADING.match(line)
        if m: skip = m.group(1).strip().lower().startswith("counterexample")
        if not skip: out.append(line)
    return "\n".join(out)


def directives(text):
    """-> [(polarity '+'|'-', object)] in reading order."""
    objs = []

    def mask(m):   # a backticked span is one opaque token, so a dot inside `brain.py` does not end the sentence
        objs.append(m.group(1)); return f"\0{len(objs) - 1}\0"
    masked = TICK.sub(mask, _without_counterexamples(text))
    out = []
    for sentence in SPLIT.split(masked):
        m = NEG.search(sentence); pol = "-"
        if not m: m = POS.search(sentence); pol = "+"
        if not m: continue
        rest = sentence[m.end():]
        first = re.search(r"\0(\d+)\0", rest)
        if not first or first.start() > WINDOW: continue
        out += [(pol, norm(objs[int(i)])) for i in re.findall(r"\0(\d+)\0", rest)]
    return out


def find_clashes(docs):
    """docs: [{id, text, repos:set, clash_ok:set}] -> sorted [(object, positive_doc_id, negative_doc_id)], each pair once per object."""
    seen = {}
    for d in docs:
        for pol, obj in directives(d["text"]):
            if obj in d["clash_ok"]: continue
            seen.setdefault(obj, {"+": set(), "-": set()})[pol].add(d["id"])
    by_id = {d["id"]: d for d in docs}
    out = set()
    for obj, s in seen.items():
        for p in s["+"]:
            for n in s["-"]:
                a, b = by_id[p], by_id[n]
                if p == n: continue
                if a["repos"] and b["repos"] and not a["repos"] & b["repos"]: continue
                out.add((obj, p, n))
    return sorted(out)


def load_docs(brain):
    docs = []
    for pattern in ("facts/*.md", "skills/*/SKILL.md"):
        for p in sorted(glob.glob(os.path.join(brain, pattern))):
            fm, body = frontmatter(p)
            if fm.get("_parse_error"): continue
            docs.append({"id": os.path.relpath(p, brain), "text": body,
                         "repos": {str(r) for r in fm.get("repos") or []}, "clash_ok": {norm(str(o)) for o in fm.get("clash_ok") or []}})
    return docs


def report(brain):
    return [f"CLASH `{o}`: required in {p}, forbidden in {n} - reconcile, scope with repos:, or add clash_ok: [{o}]" for o, p, n in find_clashes(load_docs(brain))]


def main(argv):
    brain = os.environ.get("BRAIN_DIR") or os.path.dirname(HERE)
    lines = report(brain)
    print("\n".join(lines) if lines else "clash: no clashes")
    return 1 if lines and "--strict" in argv else 0


if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
