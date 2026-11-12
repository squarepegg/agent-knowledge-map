"""Packaging invariants: versions agree, plugin manifests are valid, plugin hooks point at real scripts, docs mention every script."""
import glob, json, os, re, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rd = lambda p: open(os.path.join(ROOT, p)).read()  # noqa: E731

class Packaging(unittest.TestCase):
    def test_versions_agree(self):
        v = rd("VERSION").strip(); self.assertRegex(v, r"^\d+\.\d+\.\d+$")
        self.assertEqual(json.loads(rd(".claude-plugin/plugin.json"))["version"], v)
        self.assertRegex(rd("CHANGELOG.md"), rf"## \[{re.escape(v)}\]")

    def test_manifests(self):
        p = json.loads(rd(".claude-plugin/plugin.json")); self.assertEqual(p["name"], "agent-knowledge-map"); self.assertTrue(p["description"])
        m = json.loads(rd(".claude-plugin/marketplace.json")); self.assertEqual(m["plugins"][0]["name"], p["name"]); self.assertEqual(m["plugins"][0]["source"], "./")

    def test_plugin_hooks_reference_real_scripts_and_match_init(self):
        h = json.loads(rd("hooks/hooks.json"))["hooks"]; self.assertEqual(set(h), {"SessionStart", "Stop", "UserPromptSubmit"})
        for event, groups in h.items():
            for g in groups:
                for hook in g["hooks"]:
                    script = re.search(r"CLAUDE_PLUGIN_ROOT\}/(scripts/\w+\.py)", hook["command"]).group(1); self.assertTrue(os.path.exists(os.path.join(ROOT, script)), script)
                    self.assertIn("BRAIN_DIR", hook["command"])
        import sys; sys.path.insert(0, os.path.join(ROOT, "scripts")); import init_brain, tempfile, shutil
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); os.makedirs(d + "/skills")
        init_brain.wire_claude(d, d); wired = json.dumps(json.load(open(d + "/.claude/settings.json"))["hooks"])
        plug = json.dumps(h).replace('\\"', "")
        for script in ("session_start.py", "capture_hook.py stop", "capture_hook.py prompt"): self.assertIn(script, wired); self.assertIn(script, plug)   # same three hooks both ways

    def test_every_script_is_documented(self):
        docs = rd("README.md") + rd("docs/integrations.md") + rd("skills/brain/SKILL.md")
        for p in glob.glob(f"{ROOT}/scripts/*.py"):
            name = os.path.basename(p)
            if name.startswith("_"): continue
            self.assertIn(name[:-3], docs, f"{name} is not mentioned in README / docs / skill")

    def test_skill_and_readme_links(self):
        for md in ("README.md", "docs/integrations.md"):
            for link in re.findall(r"\]\(((?!http|#)[^)]+)\)", rd(md)): self.assertTrue(os.path.exists(os.path.join(ROOT, os.path.dirname(md), link)), f"{md}: broken link {link}")

if __name__ == "__main__": unittest.main()


class DefaultBrainDir(unittest.TestCase):
    """A clone works wherever it lives: with BRAIN_DIR unset every script uses the directory it sits in, never ~/.agents/brain."""
    def test_every_script_defaults_to_its_own_repo(self):
        import shutil, subprocess, sys, tempfile
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); b = os.path.join(d, "somewhere-else"); shutil.copytree(ROOT, b, ignore=shutil.ignore_patterns(".git", "__pycache__", "PRIMER.md"))
        env = {k: v for k, v in os.environ.items() if k not in ("BRAIN_DIR", "BRAIN_REPOS_ROOT")}; env["HOME"] = d
        env["PYTHONUSERBASE"] = __import__("site").getuserbase()
        for mod, attr in (("brain", "B"), ("build_primer", "B"), ("lint_facts", "B"), ("apply_verdicts", "B"), ("apply_skill_edits", "B"), ("digest_sessions", "OUT"), ("init_brain", "B"), ("compact", "B"), ("recall_eval", "B"), ("eval_run", "B"), ("session_start", "B"), ("maintain", "B"), ("check_freshness", "B")):
            r = subprocess.run([sys.executable, "-c", f"import {mod}; print({mod}.{attr})"], cwd=os.path.join(b, "scripts"), env=env, capture_output=True, text=True)
            self.assertEqual(os.path.realpath(r.stdout.strip().split("\n")[-1]), os.path.realpath(b if attr == "B" else os.path.join(b, "digests")), f"{mod}: {r.stdout} {r.stderr}")
