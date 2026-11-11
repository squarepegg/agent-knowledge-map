#!/usr/bin/env python3
"""Apply fact-verification verdicts (JSON list from the verify workflow) to facts/*.md frontmatter. Never deletes.
confirmed    -> verified: true, verified_at: today, anchors merged (only repos that exist locally), recorded_at dropped
partly/contradicted -> stays unverified, confidence: low, proposed fix written to review/facts-review.md
unverifiable -> verify_by: human|live added; listed in review/facts-review.md for a yes/no from the user
Usage: apply_verdicts.py results.json
"""
import datetime, json, os, re, sys
import yaml

B = os.environ.get("BRAIN_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOTS = [p for p in (os.environ.get("BRAIN_REPOS_ROOT"), os.path.expanduser("~/projects")) if p]
TODAY = datetime.date.today().isoformat()

def repo_exists(r):
    return any(os.path.isdir(os.path.join(root, r, ".git")) for root in ROOTS)

def set_fm(text, updates, drop=()):
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    fm = yaml.safe_load(m.group(1)) or {}
    for k in drop: fm.pop(k, None)
    fm.update(updates)
    order = ["title", "repos", "tags", "anchors", "verified", "verified_at", "recorded_at", "verify_by", "confidence", "scope", "source"]
    out = {k: fm[k] for k in order if k in fm}
    out.update({k: v for k, v in fm.items() if k not in out})
    return "---\n" + yaml.safe_dump(out, sort_keys=False, allow_unicode=True, width=200) + "---\n" + text[m.end():]

def main():
    res = json.load(open(sys.argv[1]))
    results = res["results"] if isinstance(res, dict) else res
    review, counts = [], {}
    for r in results:
        p = os.path.join(B, "facts", os.path.basename(r["file"]))
        if not os.path.exists(p): print("skip missing", p); continue
        t = open(p).read(); v = r["verdict"]; counts[v] = counts.get(v, 0) + 1
        title = (yaml.safe_load(re.match(r"^---\n(.*?)\n---", t, re.S).group(1)) or {}).get("title", r["file"])
        if v == "confirmed":
            fm = yaml.safe_load(re.match(r"^---\n(.*?)\n---", t, re.S).group(1)) or {}
            anchors = list(dict.fromkeys((fm.get("anchors") or []) + [a for a in (r.get("anchors") or []) if "@" in a and repo_exists(a.split("@")[0])]))
            t = set_fm(t, {"verified": True, "verified_at": TODAY, "anchors": anchors}, drop=("recorded_at", "verify_by"))
        elif v in ("partly", "contradicted"):
            t = set_fm(t, {"confidence": "low", "verify_by": "human"})
            review.append(f"### {'⚠️ partly wrong' if v == 'partly' else '❌ contradicted'}: {title}\n`facts/{os.path.basename(p)}`\n- evidence: {r.get('evidence','')}\n- proposed fix:\n\n{r.get('fix','')}\n\n- [ ] apply fix   - [ ] delete fact   - [ ] keep as is\n")
        else:
            t = set_fm(t, {"verify_by": r.get("verify_by") or "human"})
            review.append(f"### ❓ {title}\n`facts/{os.path.basename(p)}` — {r.get('evidence','')}\n- [ ] still true   - [ ] wrong/obsolete → delete\n")
        open(p, "w").write(t)
    os.makedirs(os.path.join(B, "review"), exist_ok=True)
    head = f"# Facts needing your call ({TODAY})\n\nTick one box per item; then ask the agent to apply. Confirmed facts were already marked verified.\n\n"
    open(os.path.join(B, "review", "facts-review.md"), "w").write(head + "\n".join(review))
    print("applied:", counts, "| review items:", len(review))

if __name__ == "__main__":
    main()
