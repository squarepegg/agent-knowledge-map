"""recall_eval (retrieval recall@k), recall files shipped with the examples, lint additions (instinct rows, anchor repos, unverified count)."""
import glob, importlib, io, json, os, shutil, subprocess, sys, tempfile, unittest, contextlib
import yaml
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts")); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import fixture_brain, set_env
import recall_eval as re_, init_brain, brain

def mk(files):
    d = tempfile.mkdtemp()
    for rel, text in files.items():
        os.makedirs(os.path.dirname(f"{d}/{rel}"), exist_ok=True); open(f"{d}/{rel}", "w").write(text)
    return d


class Pure(unittest.TestCase):
    def test_file_order_and_rank_of(self):
        self.assertEqual(re_.file_order([("a", 1, "x"), ("a", 2, "y"), ("b", 1, "z"), ("a", 9, "w")]), ["a", "b"])
        self.assertEqual(re_.rank_of(["facts/a.md", "facts/b.md"], "b.md"), 2); self.assertEqual(re_.rank_of(["facts/a.md"], "zzz"), None); self.assertEqual(re_.rank_of([], "a"), None)

    def test_score(self):
        self.assertEqual(re_.score([1, 2, 5, 6, None]), {"n": 5, "recall@1": 0.2, "recall@5": 0.6})
        self.assertEqual(re_.score([]), {"n": 0, "recall@1": 1.0, "recall@5": 1.0}); self.assertEqual(re_.score([6])["recall@5"], 0.0); self.assertEqual(re_.score([5])["recall@5"], 1.0)

    def test_run_uses_natural_language_needs_and_file_level_ranks(self):
        d = mk({"facts/mail.md": "title: Customer emails are hashed\nstored as salted hashes\n", "facts/other.md": "unrelated text about deploys\n"}); self.addCleanup(shutil.rmtree, d)
        res = re_.run([{"q": "can I get the customer emails in the warehouse?", "expect": "facts/mail"}, {"q": "gone", "expect": "x", "needs": ["facts/nope.md"]},
                       {"q": "something unrelated nonsense qqq", "expect": "facts/mail"}], d)
        self.assertEqual([r["rank"] for r in res], [1, None]); self.assertEqual(res[0]["top"][0], "facts/mail.md")                 # the 'needs' entry is skipped, a miss has rank None


class Cli(unittest.TestCase):
    def run_cli(self, d, *a):
        return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "recall_eval.py"), *a], env={**os.environ, "BRAIN_DIR": d}, capture_output=True, text=True)

    def test_floor_exit_codes_and_miss_lines(self):
        d = mk({"facts/a.md": "alpha problem fix\n", "facts/b.md": "beta thing\n", "evals/recall.yaml": yaml.safe_dump([{"q": "alpha problem", "expect": "facts/a"}, {"q": "beta thing", "expect": "facts/zzz"}])})
        self.addCleanup(shutil.rmtree, d); r = self.run_cli(d); self.assertEqual(r.returncode, 1); self.assertIn("n=2 recall@1=0.50 recall@5=0.50 floor=0.90", r.stdout); self.assertIn("MISS 'beta thing' -> expected facts/zzz", r.stdout)
        self.assertEqual(self.run_cli(d, "--floor", "0.5").returncode, 0); self.assertEqual(self.run_cli(d, "--floor", "0.51").returncode, 1)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "recall_eval.py")], env={**os.environ, "BRAIN_DIR": d, "RECALL_FLOOR": "0.4"}, capture_output=True, text=True); self.assertEqual(r.returncode, 0)
        out = os.path.join(d, "o.json"); self.run_cli(d, "--json", out, "--floor", "0.4"); self.assertEqual(json.load(open(out))["score"]["n"], 2)
        d6 = mk({**{f"facts/f{i}.md": "common words here\n" for i in range(1, 7)}, "evals/recall.yaml": yaml.safe_dump([{"q": "common words", "expect": "facts/f5"}, {"q": "common words", "expect": "facts/f6"}])}); self.addCleanup(shutil.rmtree, d6)
        r = self.run_cli(d6, "--floor", "0"); self.assertIn("MISS 'common words' -> expected facts/f6", r.stdout); self.assertNotIn("expected facts/f5", r.stdout)       # rank 6 is a miss, rank 5 is not
        p2 = os.path.join(tempfile.mkdtemp(), "r.yaml"); open(p2, "w").write(yaml.safe_dump([{"q": "alpha problem", "expect": "facts/a"}])); self.assertEqual(self.run_cli(d, p2).returncode, 0)   # explicit file argument


class ExampleRecall(unittest.TestCase):
    """The floor for every shipped example: this is what keeps the example facts findable by someone who has not read them."""
    FLOOR1 = {"data-team": 0.9, "web-app": 0.9, "solo-dev": 0.75, "platform-infra": 0.9}

    def test_recall_per_example(self):
        for ex in sorted(os.path.basename(p) for p in glob.glob(f"{ROOT}/examples/*") if os.path.isdir(p)):
            d = fixture_brain(); self.addCleanup(shutil.rmtree, d); shutil.copytree(f"{ROOT}/tests/fixtures", f"{d}/tests/fixtures", dirs_exist_ok=True)
            acts = init_brain.apply_example(d, ex); self.assertTrue(any(a.startswith("appended") and "recall" in a for a in acts), ex)
            res = re_.run(yaml.safe_load(open(f"{d}/evals/recall.yaml")), d); sc = re_.score([r["rank"] for r in res])
            self.assertGreaterEqual(sc["n"], 8, ex); self.assertGreaterEqual(sc["recall@5"], 0.9, f"{ex}: {[r for r in res if r['rank'] is None or r['rank'] > 5]}"); self.assertGreaterEqual(sc["recall@1"], self.FLOOR1[ex], ex)
            r = subprocess.run([sys.executable, f"{d}/scripts/recall_eval.py"], env={**os.environ, "BRAIN_DIR": d}, capture_output=True, text=True); self.assertEqual(r.returncode, 0, r.stdout)

    def test_template_recall_is_skipped_without_the_placeholders(self):
        d = fixture_brain(); self.addCleanup(shutil.rmtree, d); shutil.copy(f"{ROOT}/evals/recall.yaml", f"{d}/evals/recall.yaml") if os.path.isdir(f"{d}/evals") else (os.makedirs(f"{d}/evals"), shutil.copy(f"{ROOT}/evals/recall.yaml", f"{d}/evals/recall.yaml"))
        res = re_.run(yaml.safe_load(open(f"{d}/evals/recall.yaml")), d); self.assertTrue(all(r["rank"] is not None and r["rank"] <= 5 for r in res)); self.assertEqual(len(res), 2)
        init_brain.remove_examples(d); self.assertEqual(re_.run(yaml.safe_load(open(f"{d}/evals/recall.yaml")), d), [])

    def test_second_example_adds_its_own_recall_queries(self):
        d = fixture_brain(); self.addCleanup(shutil.rmtree, d); shutil.copytree(f"{ROOT}/tests/fixtures", f"{d}/tests/fixtures", dirs_exist_ok=True)
        init_brain.apply_example(d, "web-app"); a = init_brain.apply_example(d, "solo-dev"); self.assertIn("appended 8 recall query(ies)", a)
        self.assertEqual(len(yaml.safe_load(open(f"{d}/evals/recall.yaml"))), 16)

    def test_recall_queries_are_appended_once(self):
        d = fixture_brain(); self.addCleanup(shutil.rmtree, d); shutil.copytree(f"{ROOT}/tests/fixtures", f"{d}/tests/fixtures", dirs_exist_ok=True)
        a = init_brain.apply_example(d, "web-app"); self.assertIn("appended 8 recall query(ies)", a); self.assertEqual(init_brain.apply_example(d, "web-app"), [])
        self.assertEqual(init_brain._append_list(f"{ROOT}/examples/web-app/evals/recall.yaml", f"{d}/evals/recall.yaml", "q", "web-app"), 0); self.assertEqual(init_brain._append_list("/no/such", "/tmp/x", "q", "n"), 0)


class LintAdditions(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d); os.makedirs(f"{self.d}/facts"); set_env(self, BRAIN_DIR=self.d, BRAIN_REPOS_ROOT=self.d)
        import lint_facts; self.lf = importlib.reload(lint_facts)

    def fact(self, name, fm, body="x"):
        open(f"{self.d}/facts/{name}.md", "w").write("---\ntitle: t\nconfidence: high\nverified_at: '%s'\nsource: s\n%s---\n%s\n" % (__import__("datetime").date.today(), fm, body))

    def test_instinct_rows(self):
        good = "- **When** a deploy fails -> **do** roll back. _Evidence:_ 2025-01-02, said so. high."
        self.fact("i", "tags: [instincts]\n", good); self.assertEqual(self.lf.lint(), [])
        for conf in ("medium", "low"): self.fact("i", "tags: [instincts]\n", good.replace("high", conf)); self.assertEqual(self.lf.lint(), [], conf)
        for bad in ("- **When** a -> roll back. _Evidence:_ x. high.", "- **When** a -> **do** b. high.", "- **When** a -> **do** b. _Evidence:_ x. certain.", "- **When** a -> **do** b. _Evidence:_ x. high"):
            self.fact("i", "tags: [instincts]\n", "intro\n" + bad); r = self.lf.lint(); self.assertEqual(len(r), 1, bad); self.assertTrue(r[0].startswith("INSTINCT facts/i.md:2:"), r)
        self.fact("i", "tags: [other]\n", "- **When** nonsense"); self.assertEqual(self.lf.lint(), [])          # only facts tagged instincts are checked
        self.fact("i", "tags: [instincts]\n", "plain line\n- not a when row"); self.assertEqual(self.lf.lint(), [])

    def test_anchor_repos_and_unverified_count(self):
        self.fact("a", "anchors: ['svc@f.txt', 'other@x', '@orphan']\n"); self.fact("b", "anchors: ['svc@g']\n"); self.fact("c", "")
        self.assertEqual(self.lf.anchor_repos(self.d), ["other", "svc"])
        self.fact("many", "anchors: ['zeta@a', 'alpha@a', 'mid@a', 'beta@a', 'omega@a', 'gamma@a']\n"); self.assertEqual(self.lf.anchor_repos(self.d), sorted(["other", "svc", "zeta", "alpha", "mid", "beta", "omega", "gamma"])); os.remove(f"{self.d}/facts/many.md")
        run = lambda *a: subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "lint_facts.py"), *a], env={**os.environ, "BRAIN_DIR": self.d, "BRAIN_REPOS_ROOT": self.d}, capture_output=True, text=True)  # noqa: E731
        self.assertEqual(run("--anchor-repos").stdout.split(), ["other", "svc"]); self.assertEqual(run("--anchor-repos").returncode, 0)
        for n in ("a", "b", "c"): os.remove(f"{self.d}/facts/{n}.md")
        open(f"{self.d}/facts/u1.md", "w").write("---\ntitle: t\nconfidence: low\nverified: false\nrecorded_at: '%s'\nsource: s\n---\nx\n" % __import__("datetime").date.today())
        open(f"{self.d}/facts/u2.md", "w").write("---\ntitle: t\nconfidence: low\nverified: false\nrecorded_at: '%s'\nsource: s\n---\nx\n" % __import__("datetime").date.today())
        self.assertIn("-- 0 issue(s), 0 hard; unverified: 2 facts", run().stdout); self.lf.lint(); self.assertEqual(self.lf.unverified_facts[0], 2); self.lf.lint(); self.assertEqual(self.lf.unverified_facts[0], 2)   # recounted per call, not accumulated

if __name__ == "__main__": unittest.main()
