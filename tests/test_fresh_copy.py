"""End-to-end smoke: the README quick start, run in a throwaway copy of the working tree with an isolated HOME. If this passes, a new user's first run works."""
import json, os, shutil, site, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import fixture_brain

class FreshCopy(unittest.TestCase):
    def setUp(self):   # a fresh copy per test: tests must not depend on each other
        self.b = fixture_brain(full=True); self.h = tempfile.mkdtemp(); self.d = self.b; self.addCleanup(shutil.rmtree, self.b); self.addCleanup(shutil.rmtree, self.h)
        self.env = {**os.environ, "BRAIN_DIR": self.b, "HOME": self.h, "PYTHONUSERBASE": site.getuserbase(), "PYTHONDONTWRITEBYTECODE": "1"}

    def sh(self, *a, ok=True, stdin=None):
        r = subprocess.run([sys.executable, f"{self.b}/scripts/{a[0]}", *a[1:]], env=self.env, capture_output=True, text=True, cwd=self.b, input=stdin)
        if ok: self.assertEqual(r.returncode, 0, f"{a}: {r.stdout}\n{r.stderr}")
        return r

    def test_quick_start_sequence(self):
        r = self.sh("brain.py", "init", "--org", "Acme", "--no-examples", "--claude", "--home", self.h); self.assertIn("PRIMER.md", r.stdout)
        self.assertIn("# Acme primer", open(f"{self.b}/PRIMER.md").read())
        self.assertIn(f"@{self.b}/PRIMER.md", open(f"{self.h}/.claude/CLAUDE.md").read())
        self.sh("brain.py", "init", "--org", "Acme", "--no-examples", "--claude", "--home", self.h)                        # idempotent re-run
        self.assertEqual(open(f"{self.h}/.claude/CLAUDE.md").read().count("PRIMER.md"), 1)
        self.sh("brain.py", "ws", "new", "first-job", "My first job"); self.assertIn("first-job\tactive", self.sh("brain.py", "ws", "list").stdout)
        self.sh("brain.py", "note", "gotcha", "Widget needs restart", "restart it after config changes")
        plan = self.sh("brain.py", "compact", "--write").stdout; self.assertIn("1 item(s)", plan); self.assertTrue(os.path.exists(f"{self.b}/facts/widget-needs-restart.md"))
        self.assertIn("Widget", self.sh("brain.py", "search", "widget", "restart").stdout)
        self.sh("brain.py", "decision", "pick-db", "Pick a database")
        self.sh("lint_facts.py", "--strict")                                                                                   # drafts are valid unverified facts
        self.sh("brain.py", "compact", "--archive"); self.assertEqual(self.sh("brain.py", "inbox").stdout.strip(), "inbox empty")
        self.sh("brain.py", "primer")
        s = self.sh("session_start.py", "--no-probes").stdout; self.assertIn("Brain context for", s)

    def test_hooks_installed_by_init_actually_run(self):
        self.sh("brain.py", "init", "--claude", "--home", self.h); hooks = json.load(open(f"{self.h}/.claude/settings.json"))["hooks"]
        for event, payload in (("SessionStart", ""), ("UserPromptSubmit", json.dumps({"prompt": "that's wrong"})), ("Stop", json.dumps({"session_id": "s"}))):
            cmds = [h["command"] for g in hooks[event] for h in g["hooks"]]; self.assertEqual(len(cmds), 1, cmds)
            r = subprocess.run(cmds[0], shell=True, env=self.env, input=payload, capture_output=True, text=True); self.assertEqual(r.returncode, 0, f"{event}: {r.stderr}")

    def test_every_example_installs_clean_in_a_whole_repo_copy(self):
        import glob
        for ex in sorted(os.path.basename(p) for p in glob.glob(f"{ROOT}/examples/*") if os.path.isdir(p)):
            b = fixture_brain(full=True); self.addCleanup(shutil.rmtree, b); env = {**self.env, "BRAIN_DIR": b}
            run = lambda *a: subprocess.run([sys.executable, f"{b}/scripts/{a[0]}", *a[1:]], env=env, capture_output=True, text=True, cwd=b)  # noqa: E731
            self.assertEqual(run("brain.py", "init", "--example", ex).returncode, 0, ex)
            lint = run("lint_facts.py", "--strict"); self.assertIn("-- 0 issue(s), 0 hard", lint.stdout, f"{ex}: {lint.stdout}")
            ev = run("eval_run.py"); self.assertEqual(ev.returncode, 0, f"{ex}: {ev.stdout}"); self.assertNotIn("FAIL", ev.stdout)

    def test_the_copy_passes_its_own_gates(self):
        self.sh("lint_facts.py", "--strict"); self.assertNotIn("FAIL", self.sh("eval_run.py").stdout)
        self.sh("brain.py", "init", "--no-examples"); out = self.sh("eval_run.py").stdout; self.assertIn("SKIP", out); self.assertNotIn("FAIL", out)      # deleting the examples must not break the evals
        for m in ("brain", "compact"): self.sh("mutation_check.py", f"tests/mutants/{m}.yaml")
        self.sh("maintain.py", "--only", "lint", "evals", "--weekday", "2")

if __name__ == "__main__": unittest.main()
