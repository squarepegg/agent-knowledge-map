#!/usr/bin/env python3
"""Deterministic golden checks for brain skills (no model, no network). Catches silent regressions when a skill is edited:
  - frontmatter: `name` equals the directory name, `description` present and <= 1024 chars
  - pins: substrings the skill must keep (pinned truths; delete one deliberately by editing evals/golden/skills.yaml)
  - budget: SKILL.md length <= max_chars (skills load into context; bloat costs every turn)
  - repo refs (optional): every backticked token starting with a prefix in $GOLDEN_REPO_PREFIXES (comma list, e.g. "acme-,svc-") must be a known repo (a clone under $BRAIN_REPOS_ROOT/~/projects, or repos/repos.json), unless allowed. Unset = check off
  golden_skills.py [--config evals/golden/skills.yaml] [--changed GIT_REF] [--json]   exit 1 on any failure, 2 on bad config
--changed REF checks only skills whose SKILL.md differs from REF (the cheap pre-merge path)."""
import json, os, re, subprocess, sys
import yaml

B = os.environ.get("BRAIN_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def repo_token():
    pre = [p.strip() for p in os.environ.get("GOLDEN_REPO_PREFIXES", "").split(",") if p.strip()]
    return re.compile(r"`((?:" + "|".join(re.escape(p) for p in pre) + r")[a-z0-9-]+)`") if pre else None
DESC_MAX = 1024


def split_frontmatter(text):
    if not text.startswith("---\n"): return {}, text
    end = text.find("\n---", 4)
    if end < 0: return {}, text
    try: fm = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError: fm = {}
    return (fm if isinstance(fm, dict) else {}), text[end + 4:]


def known_repos(brain=B):
    names = set()
    try: names |= {r["name"] for r in json.load(open(os.path.join(brain, "repos", "repos.json")))["repos"]}
    except (OSError, ValueError, KeyError, TypeError): pass
    try: names |= set(json.load(open(os.path.join(brain, "repos", "local-clones.json")))["clones"])
    except (OSError, ValueError, KeyError, TypeError): pass
    root = os.environ.get("BRAIN_REPOS_ROOT") or os.path.expanduser("~/projects")
    if os.path.isdir(root): names |= set(os.listdir(root))
    return names


def check_skill(entry, brain=B, repos=None):
    """-> list of failure strings for one config entry {skill, pins, max_chars, allow_repos}"""
    name = entry["skill"]; path = os.path.join(brain, "skills", name, "SKILL.md")
    if not os.path.exists(path): return [f"{name}: SKILL.md not found"]
    text = open(path).read(); fm, _ = split_frontmatter(text); out = []
    if fm.get("name") != name: out.append(f"{name}: frontmatter name is {fm.get('name')!r}")
    desc = fm.get("description")
    if not isinstance(desc, str) or not desc.strip(): out.append(f"{name}: description missing")
    elif len(desc) > DESC_MAX: out.append(f"{name}: description {len(desc)} chars > {DESC_MAX}")
    for pin in entry.get("pins") or []:
        if pin not in text: out.append(f"{name}: pinned text missing: {pin!r}")
    limit = entry.get("max_chars")
    if limit is not None and len(text) > limit: out.append(f"{name}: {len(text)} chars > budget {limit}")
    repos = known_repos(brain) if repos is None else repos
    allowed = set(entry.get("allow_repos") or [])
    rx = repo_token()
    for tok in sorted(set(rx.findall(text))) if rx else []:
        if tok not in repos and tok not in allowed: out.append(f"{name}: unknown repo `{tok}`")
    return out


def load_config(path):
    try: cfg = yaml.safe_load(open(path))
    except (OSError, yaml.YAMLError) as e: raise SystemExit(f"golden_skills: bad config {path}: {e}") from None
    if not isinstance(cfg, list) or not all(isinstance(e, dict) and isinstance(e.get("skill"), str) for e in cfg):
        raise SystemExit(f"golden_skills: {path} must be a list of {{skill: ...}} entries")
    names = [e["skill"] for e in cfg]
    if len(set(names)) != len(names): raise SystemExit("golden_skills: duplicate skill entries")
    return cfg


def changed_skills(ref, brain=B):
    out = subprocess.run(["git", "-C", brain, "diff", "--name-only", ref, "--", "skills"], capture_output=True, text=True)
    if out.returncode != 0: raise SystemExit(f"golden_skills: git diff {ref} failed: {out.stderr.strip()}")
    return {p.split("/")[1] for p in out.stdout.split("\n") if p.startswith("skills/") and p.count("/") >= 2}


def run(config, brain=B, changed=None, repos=None):
    cfg = load_config(config)
    if changed is not None: cfg = [e for e in cfg if e["skill"] in changed]
    repos = known_repos(brain) if repos is None else repos
    return {e["skill"]: check_skill(e, brain, repos) for e in cfg}


def main(argv):
    config = os.path.join(B, "evals", "golden", "skills.yaml"); changed = None; as_json = "--json" in argv
    if "--config" in argv: config = argv[argv.index("--config") + 1]
    if "--changed" in argv: changed = changed_skills(argv[argv.index("--changed") + 1])
    res = run(config, changed=changed)
    if as_json: print(json.dumps(res, indent=1))
    else:
        for s, fails in res.items(): print(("FAIL " if fails else "PASS ") + s + "".join("\n  - " + f for f in fails))
        print(f"\n{sum(1 for f in res.values() if not f)}/{len(res)} skills pass")
    return 1 if any(res.values()) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
