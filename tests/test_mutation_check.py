"""Spec for scripts/mutation_check.py: killed mutants pass, survivors fail, stale (non-unique/missing) mutants fail."""
import contextlib, io, os, sys, tempfile, unittest
import yaml
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import mutation_check as mc  # noqa: E402


class MutationCheck(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.old = mc.ROOT; mc.ROOT = self.d
        os.makedirs(os.path.join(self.d, "scripts")); os.makedirs(os.path.join(self.d, "tests"))
        open(os.path.join(self.d, "scripts", "calc.py"), "w").write("def add(a, b):\n    return a + b\n\ndef unchecked():\n    return 1\n")
        open(os.path.join(self.d, "tests", "test_calc.py"), "w").write(
            "import os, sys, unittest\nsys.path.insert(0, os.path.join(os.environ['BRAIN_DIR'], 'scripts'))\nimport calc\n"
            "class T(unittest.TestCase):\n    def test_add(self): self.assertEqual(calc.add(1, 2), 3)\n")

    def tearDown(self): mc.ROOT = self.old

    def run_spec(self, mutants):
        p = os.path.join(self.d, "m.yaml"); yaml.safe_dump({"target": "scripts/calc.py", "tests": ["tests.test_calc"], "mutants": mutants}, open(p, "w"))
        with contextlib.redirect_stdout(io.StringIO()) as out: ok = mc.run_one(p)
        return ok, out.getvalue()

    def test_copy_includes_top_level_files_and_other_dirs_but_not_git(self):
        os.makedirs(os.path.join(self.d, "facts")); os.makedirs(os.path.join(self.d, ".git")); os.makedirs(os.path.join(self.d, ".cache"))
        open(os.path.join(self.d, "PRIMER.md"), "w").write("x"); open(os.path.join(self.d, "facts", "f.md"), "w").write("y"); open(os.path.join(self.d, ".git", "HEAD"), "w").write("z"); open(os.path.join(self.d, ".cache", "c"), "w").write("c")
        probe = ("import os; r = os.environ['BRAIN_DIR']; ok = os.path.exists(r + '/PRIMER.md') and os.path.exists(r + '/facts/f.md') and not os.path.exists(r + '/.git') and not os.path.exists(r + '/.cache'); raise SystemExit(0 if ok else 1)")
        ok, _ = mc.run_copy("def add(a, b):\n    return a + b\n", "scripts/calc.py", [sys.executable, "-c", probe]); self.assertTrue(ok)

    def test_mutants_run_with_an_isolated_home(self):
        probe = "import os; raise SystemExit(0 if os.environ['HOME'] == os.environ['BRAIN_DIR'] != %r else 1)" % os.path.expanduser("~")
        ok, _ = mc.run_copy("def add(a, b):\n    return a + b\n", "scripts/calc.py", [sys.executable, "-c", probe]); self.assertTrue(ok)

    def test_killed_passes(self):
        ok, out = self.run_spec([{"id": "sub", "old": "a + b", "new": "a - b"}]); self.assertTrue(ok); self.assertIn("1/1 mutants killed", out)

    def test_survivor_fails(self):
        ok, out = self.run_spec([{"id": "sub", "old": "a + b", "new": "a - b"}, {"id": "alive", "old": "return 1", "new": "return 2"}])
        self.assertFalse(ok); self.assertIn("survivors=['alive']", out)

    def test_custom_command_runner(self):
        p = os.path.join(self.d, "m.yaml")
        def go(cmd):
            yaml.safe_dump({"target": "scripts/calc.py", "command": cmd, "mutants": [{"id": "sub", "old": "a + b", "new": "a - b"}]}, open(p, "w"))
            with contextlib.redirect_stdout(io.StringIO()): return mc.run_one(p)
        self.assertTrue(go([sys.executable, "-c", "import sys; sys.path.insert(0,'scripts'); import calc; sys.exit(0 if calc.add(1,2)==3 else 1)"]))  # mutant makes it fail -> killed
        self.assertFalse(go([sys.executable, "-c", "pass"]))  # runner that never fails -> survivor

    def test_failing_baseline_is_an_error_not_all_killed(self):
        open(os.path.join(self.d, "tests", "test_calc.py"), "a").write("    def test_always_red(self): self.fail('red baseline')\n")
        ok, out = self.run_spec([{"id": "sub", "old": "a + b", "new": "a - b"}]); self.assertFalse(ok); self.assertIn("baseline FAILS", out); self.assertNotIn("1/1 mutants killed", out)

    def test_parallel_jobs_same_result_and_survivor_attribution(self):
        os.environ["MUTATION_JOBS"] = "3"
        try:
            ok, out = self.run_spec([{"id": "sub", "old": "a + b", "new": "a - b"}, {"id": "alive", "old": "return 1", "new": "return 2"}, {"id": "sub2", "old": "a + b", "new": "a * b"}])
        finally: del os.environ["MUTATION_JOBS"]
        self.assertFalse(ok); self.assertIn("2/3 mutants killed", out); self.assertIn("survivors=['alive']", out)

    def test_stale_or_ambiguous_fails(self):
        ok, out = self.run_spec([{"id": "gone", "old": "nope", "new": "x"}]); self.assertFalse(ok); self.assertIn("gone (matches 0x)", out)
        ok, out = self.run_spec([{"id": "twice", "old": "return", "new": "pass"}]); self.assertFalse(ok); self.assertIn("matches 2x", out)

    def test_cli_exit_code(self):
        import subprocess
        def cli(mutants):
            p = os.path.join(self.d, "m.yaml"); yaml.safe_dump({"target": "scripts/calc.py", "tests": ["tests.test_calc"], "mutants": mutants}, open(p, "w"))
            return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "mutation_check.py"), p], env={**os.environ, "MUTATION_ROOT": self.d}, capture_output=True, text=True).returncode
        self.assertEqual(cli([{"id": "sub", "old": "a + b", "new": "a - b"}]), 0)
        self.assertEqual(cli([{"id": "alive", "old": "return 1", "new": "return 2"}]), 1)


if __name__ == "__main__":
    unittest.main()
