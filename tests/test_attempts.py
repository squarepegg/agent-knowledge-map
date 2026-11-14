import json, os, subprocess, sys, tempfile, shutil, unittest, contextlib, io
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import _attempts, agentic_eval


def git_brain(test):
    d = tempfile.mkdtemp(); test.addCleanup(shutil.rmtree, d)
    run = lambda *a: subprocess.run(["git", "-C", d, *a], check=True, capture_output=True)  # noqa: E731
    run("init", "-q"); run("config", "user.email", "t@t"); run("config", "user.name", "t")
    os.makedirs(os.path.join(d, "facts")); open(os.path.join(d, "facts", "x.md"), "w").write("a\n")
    os.makedirs(os.path.join(d, "metrics")); open(os.path.join(d, "metrics", "agentic.json"), "w").write('{"runs": []}')
    run("add", "."); run("commit", "-qm", "init")
    return d


class Attempts(unittest.TestCase):
    def test_key_tracks_fixture_grader_brain_agent(self):
        d = git_brain(self); fx = {"id": "a", "expect": ["x"]}
        k = _attempts.Log(d, "e", "g1", "ag").key(fx)
        self.assertEqual(k, _attempts.Log(d, "e", "g1", "ag").key(dict(fx)))                 # same experiment -> same key
        self.assertNotEqual(k, _attempts.Log(d, "e", "g2", "ag").key(fx))                    # grader edit
        self.assertNotEqual(k, _attempts.Log(d, "e", "g1", "other").key(fx))                 # agent command
        self.assertNotEqual(k, _attempts.Log(d, "e", "g1", "ag").key({**fx, "expect": ["y"]}))  # gold edit
        os.makedirs(os.path.join(d, "metrics", "attempts")); open(os.path.join(d, "metrics", "attempts", "e.jsonl"), "w").write("{}\n")
        open(os.path.join(d, "metrics", "agentic.json"), "w").write('{"runs": [], "x": 1}')         # tracked metrics edit (agentic.json)
        self.assertEqual(k, _attempts.Log(d, "e", "g1", "ag").key(fx))                       # the log itself does not change the brain state
        open(os.path.join(d, "facts", "x.md"), "w").write("b\n")
        self.assertNotEqual(k, _attempts.Log(d, "e", "g1", "ag").key(fx))                    # uncommitted brain edit
        open(os.path.join(d, "facts", "new.md"), "w").write("n\n")
        k2 = _attempts.Log(d, "e", "g1", "ag").key(fx); open(os.path.join(d, "facts", "new.md"), "w").write("m\n")
        self.assertNotEqual(k2, _attempts.Log(d, "e", "g1", "ag").key(fx))                   # untracked file contents count

    def test_no_git_never_reuses(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d)
        log = _attempts.Log(d, "e", "g"); self.assertIsNone(log.key({"id": "a"}))
        log.record({"id": "a"}, {"ok": 1}, 0.1); self.assertEqual(log.cached(), {})

    def test_record_is_durable_and_torn_line_skipped(self):
        d = git_brain(self); log = _attempts.Log(d, "e", "g"); log.start()
        log.record({"id": "a"}, {"score": 1}, 0.1)
        open(log.path, "a").write('{"type": "attempt", "trunc')                                 # crash mid-write
        self.assertEqual(list(_attempts.Log(d, "e", "g").cached().values()), [{"score": 1}])

    def test_triggers(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); os.makedirs(os.path.join(d, "evals"))
        for i in range(4): open(os.path.join(d, "evals", f"e{i}.yaml"), "w").write("[]")
        self.assertEqual(_attempts.migration_triggers(d), [])
        open(os.path.join(d, "evals", "e4.yaml"), "w").write("[]")
        self.assertIn("eval types 5 >= 5", _attempts.migration_triggers(d))
        for _ in range(3): _attempts.Log(d, "x", "g").start()                                    # 3 starts, newest may be running -> 2 incomplete
        self.assertTrue(any("2 runs never finished" in t for t in _attempts.migration_triggers(d)))
        log = _attempts.Log(d, "y", "g"); log.start(); log.t0 -= 31 * 60; log.end({})
        self.assertTrue(any("y: a full run took 31 min" in t for t in _attempts.migration_triggers(d)))


class AgenticResume(unittest.TestCase):
    def test_resume_skips_paid_attempts(self):
        d = git_brain(self); os.makedirs(os.path.join(d, "evals"))
        open(os.path.join(d, "evals", "agentic.yaml"), "w").write(json.dumps([{"id": "a", "q": "hello", "expect": [["eval"]]}]))
        calls = os.path.join(d, "..", os.path.basename(d) + "-calls"); self.addCleanup(lambda: os.path.exists(calls) and os.remove(calls))
        old_b = agentic_eval.B; agentic_eval.B = d; self.addCleanup(setattr, agentic_eval, "B", old_b)
        os.environ["AGENTIC_CMD"] = f"echo x >> {calls}; cat"; self.addCleanup(os.environ.pop, "AGENTIC_CMD")
        with contextlib.redirect_stdout(io.StringIO()): agentic_eval.main(["x", "a"])
        with contextlib.redirect_stdout(io.StringIO()) as o: agentic_eval.main(["x", "--resume", "a"])
        self.assertIn("CACHED a", o.getvalue()); self.assertEqual(open(calls).read().count("x"), 1)
        with contextlib.redirect_stdout(io.StringIO()): agentic_eval.main(["x", "a"])         # without --resume it pays again
        self.assertEqual(open(calls).read().count("x"), 2)

if __name__ == "__main__": unittest.main()
