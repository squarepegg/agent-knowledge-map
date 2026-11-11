#!/usr/bin/env python3
"""Apply reviewed skill edits: exact, unique find->replace per skill, then stamp metadata.verified_at. Edits whose `find` is missing or
non-unique are skipped and reported (never fuzzy-applied).
Input JSON: {"skills": [{"skill": name, "summary": str, "edits": [{"find": str, "replace": str}], "unresolved": [..]}], "missing": [..]}
(optionally wrapped in {"result": ...}). Usage: apply_skill_edits.py result.json. Env: BRAIN_DIR."""
import datetime, json, os, re, sys
import yaml

B = os.environ.get("BRAIN_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def apply_edits(text, edits):
    """-> (new_text, applied, skip_reasons). An edit applies only if `find` occurs exactly once and actually changes the text."""
    applied, skipped = 0, []
    for e in edits:
        n = text.count(e["find"])
        if n == 1 and e["find"] != e["replace"]: text = text.replace(e["find"], e["replace"]); applied += 1
        else: skipped.append(("not found" if n == 0 else f"{n} matches") if e["find"] != e["replace"] else "no-op")
    return text, applied, skipped

def stamp(text, today, unresolved):
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    fm = yaml.safe_load(m.group(1)) or {}
    md = fm.get("metadata") or {}
    md.update({"verified_at": today, "source": f"verified {today}", "unresolved": unresolved})
    fm["metadata"] = md
    return "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=1000) + "---\n" + text[m.end():]

def main(argv=None):
    argv = argv or sys.argv
    d = json.load(open(argv[1])); d = d.get("result", d); today = datetime.date.today().isoformat(); report = []
    for s in d["skills"]:
        p = os.path.join(B, "skills", s["skill"], "SKILL.md")
        if not os.path.exists(p): report.append(f"{s['skill']}: missing file"); continue
        t, applied, skipped = apply_edits(open(p).read(), s.get("edits", []))
        for why in skipped: report.append(f"  skip ({why}) {s['skill']}")
        t = stamp(t, today, len(s.get("unresolved", [])))
        open(p, "w").write(t)
        report.insert(0, f"{s['skill']}: {applied} edits applied, {len(skipped)} skipped, {len(s.get('unresolved', []))} unresolved — {s.get('summary', '')[:140]}")
    print("\n".join(report)); print("missing:", d.get("missing"))

if __name__ == "__main__":
    main()
