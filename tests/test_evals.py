import json, os, sys, tempfile, shutil, unittest, contextlib, io
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import eval_run, agentic_eval, _guard


class EvalRun(unittest.TestCase):
    def test_check_expect_first_line_forbid(self):
        ok, m, f, h = eval_run.check({"expect": ["a", "b"]}, "a only"); self.assertFalse(ok); self.assertEqual(m, ["b"])
        ok, *_ = eval_run.check({"expect": ["a"]}, "xa"); self.assertTrue(ok)
        ok, _, f, _ = eval_run.check({"first_line": "top"}, "\nnot it\ntop"); self.assertFalse(ok); self.assertFalse(f)
        ok, *_ = eval_run.check({"first_line": "top"}, "\n\ntop one\nrest"); self.assertTrue(ok)   # blank lines are skipped
        ok, *_ = eval_run.check({"first_line": "top"}, ""); self.assertFalse(ok)                    # empty output never satisfies first_line
        ok, _, _, h = eval_run.check({"expect": ["a"], "forbid": ["bad"]}, "a bad"); self.assertFalse(ok); self.assertEqual(h, ["bad"])

    def test_run_tiers_and_exit_code(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d)
        os.makedirs(os.path.join(d, "facts")); open(os.path.join(d, "facts", "x.md"), "w").write("the widget lives in zeta\n")
        eval_run.B = d; qd = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, qd)
        def go(qs):
            p = os.path.join(qd, "q.yaml"); open(p, "w").write(json.dumps(qs))
            with contextlib.redirect_stdout(io.StringIO()) as o: rc = eval_run.main(["x", p])
            return rc, o.getvalue()
        rc, out = go([{"id": "a", "q": "?", "run": {"search": "widget"}, "expect": ["zeta"]}]); self.assertEqual(rc, 0); self.assertIn("PASS", out)
        rc, out = go([{"id": "a", "q": "?", "run": {"search": "widget"}, "expect": ["nope"]}]); self.assertEqual(rc, 1); self.assertIn("FAIL", out)
        rc, out = go([{"id": "a", "q": "?", "run": {"search": "widget"}, "expect": ["nope"], "tier": "coverage"}]); self.assertEqual(rc, 0); self.assertIn("GAP", out)
        rc, out = go([{"id": "a", "q": "?", "run": {"cmd": ["echo", "hi"]}, "expect": ["hi"]}]); self.assertEqual(rc, 0)
        rc, out = go([{"id": "a", "q": "?", "expect": []}]); self.assertEqual(rc, 1); self.assertIn("error=", out)
        rc, out = go([{"id": "a", "q": "?", "run": {"search": "widget"}, "expect": ["nope"], "needs": ["facts/gone.md"]}]); self.assertEqual(rc, 0); self.assertIn("SKIP", out); self.assertIn("must: 0/0   coverage: 0/0   skipped: 1", out)
        rc, out = go([{"id": "a", "q": "?", "run": {"search": "widget"}, "expect": ["nope"], "needs": ["facts/x.md"]}]); self.assertEqual(rc, 1)             # needs present: evaluated normally
        rc, out = go([{"id": "a", "q": "?", "run": {"search": "widget"}, "expect": ["zeta"], "needs": ["facts/x.md", "facts/gone.md"]}]); self.assertIn("SKIP", out)  # ALL needs must exist   # bad entry is a failure, not a pass


class Agentic(unittest.TestCase):
    def test_grade(self):
        it = {"expect": [["gitops", "argo"], ["pr"]], "forbid": ["kubectl apply"], "max_words": 5}
        c, s = agentic_eval.grade(it, "Open a PR to gitops"); self.assertTrue(c["correct"]); self.assertTrue(c["concise"]); self.assertEqual(s, 1)
        c, s = agentic_eval.grade(it, "gitops only"); self.assertFalse(c["correct"]); self.assertEqual(s, 0.5)       # second group missing
        c, _ = agentic_eval.grade(it, "PR gitops kubectl apply"); self.assertFalse(c["correct"])
        c, _ = agentic_eval.grade(it, "PR gitops one two three four five"); self.assertFalse(c["concise"])
        c, _ = agentic_eval.grade({"expect_re": [r"\d+ files"]}, "12 files"); self.assertTrue(c["correct"])
        c, _ = agentic_eval.grade({"expect_re": [r"\d+ files"]}, "many files"); self.assertFalse(c["correct"])

    def test_ask_prompt_placeholder_and_stdin(self):
        os.environ["AGENTIC_CMD"] = "echo {prompt}"; self.assertIn("Eval question", agentic_eval.ask("hello world"))
        os.environ["AGENTIC_CMD"] = "cat"; self.assertIn("hello", agentic_eval.ask("hello"))
        del os.environ["AGENTIC_CMD"]
        with self.assertRaises(SystemExit): agentic_eval.ask("x")


class Guard(unittest.TestCase):
    def test_shrink(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); p = os.path.join(d, "c.json")
        n = lambda o: len(o["items"])  # noqa: E731
        _guard.write_json_guarded(p, {"items": list(range(100))}, n, "t")
        with self.assertRaises(SystemExit) as e: _guard.write_json_guarded(p, {"items": list(range(10))}, n, "t")
        self.assertEqual(e.exception.code, 3); self.assertEqual(len(json.load(open(p))["items"]), 100)
        _guard.write_json_guarded(p, {"items": list(range(80))}, n, "t"); self.assertEqual(len(json.load(open(p))["items"]), 80)
        small = os.path.join(d, "s.json"); _guard.write_json_guarded(small, {"items": list(range(5))}, n, "t")
        _guard.write_json_guarded(small, {"items": [1]}, n, "t"); self.assertEqual(len(json.load(open(small))["items"]), 1)   # tiny baselines may shrink
        os.environ["BRAIN_ALLOW_SHRINK"] = "1"; self.addCleanup(os.environ.pop, "BRAIN_ALLOW_SHRINK")
        _guard.write_json_guarded(p, {"items": [1]}, n, "t"); self.assertEqual(len(json.load(open(p))["items"]), 1)

if __name__ == "__main__": unittest.main()
