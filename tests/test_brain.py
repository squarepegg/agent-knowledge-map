import os, sys, tempfile, shutil, unittest, datetime, importlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import brain, build_primer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import fixture_brain, set_env

def make_brain():
    return fixture_brain()

class T(unittest.TestCase):
    def setUp(self): self.d = make_brain()
    def tearDown(self): shutil.rmtree(self.d)

    def test_note_writes_inbox_and_rejects_secrets(self):
        p = brain.note("gotcha", "x breaks y", "use z", brain=self.d)
        self.assertIn("[gotcha] x breaks y", open(p).read())
        with self.assertRaises(SystemExit): brain.note("gotcha", "k", "api_key=abcdefghijklmnopqrstuvwx", brain=self.d)
        with self.assertRaises(SystemExit): brain.note("bogus", "t", brain=self.d)

    def test_search_ranks_more_terms_first(self):
        brain.note("fact", "alpha beta", brain=self.d); brain.note("fact", "alpha only", brain=self.d)
        r = brain.search(["alpha", "beta"], brain=self.d)
        self.assertIn("alpha beta", r[0])

    def test_search_is_case_insensitive_and_skips_processed(self):
        open(os.path.join(self.d, "facts", "c.md"), "w").write("UPPER Marker line\n")
        self.assertTrue(brain.search(["marker"], brain=self.d))
        os.makedirs(os.path.join(self.d, "inbox", "processed")); open(os.path.join(self.d, "inbox", "processed", "old.md"), "w").write("archived zebra\n")
        self.assertEqual(brain.search(["zebra"], brain=self.d), [])

    def test_frontmatter(self):
        import _fm
        p = os.path.join(self.d, "f.md"); open(p, "w").write("---\na: 1\n---\nbody\n"); self.assertEqual(_fm.frontmatter(p), ({"a": 1}, "body\n"))
        open(p, "w").write("no fm"); self.assertEqual(_fm.frontmatter(p), ({}, "no fm"))

    def test_ws_new_list_and_no_overwrite(self):
        p = brain.ws_new("My Thing", brain=self.d)
        self.assertTrue(p.endswith("my-thing/STATE.md"))
        self.assertIn(str(datetime.date.today()), open(p).read())
        self.assertTrue(any(l.startswith("my-thing\tactive") for l in brain.ws_list(brain=self.d)))
        with self.assertRaises(SystemExit): brain.ws_new("my-thing", brain=self.d)

    def test_decision_append_only(self):
        p = brain.decision_new("pick-db", brain=self.d)
        self.assertIn(f"date: {datetime.date.today()}", open(p).read())
        with self.assertRaises(SystemExit): brain.decision_new("pick-db", brain=self.d)

    def test_primer_builds_within_budget_and_has_routes(self):
        out, over = build_primer.build(self.d)
        self.assertFalse(over); self.assertIn("Need → use", out); self.assertIn("Example Service", out)

    def test_lint_clean_on_template_and_catches_secret(self):
        set_env(self, BRAIN_DIR=self.d)
        import lint_facts; importlib.reload(lint_facts)
        self.assertEqual([i for i in lint_facts.lint() if i.split()[0] in lint_facts.HARD], [])
        open(os.path.join(self.d, "facts", "bad.md"), "w").write("---\ntitle: t\nconfidence: low\nverified_at: '2025-01-01'\nsource: s\n---\npassword: abcdefghijklmnopqrstuvwxyz\n")
        self.assertTrue(any(i.startswith("SECRET") for i in lint_facts.lint()))

    def test_requires_accepts_ids_declared_in_probes_yaml(self):
        set_env(self, BRAIN_DIR=self.d)
        import lint_facts; importlib.reload(lint_facts)
        open(os.path.join(self.d, "capabilities.yaml"), "w").write("- {id: c, enables: e, requires: [vault, gh, 'aws:prod'], how: h}\n")
        self.assertEqual([i.split()[0] for i in lint_facts.lint() if "REQ" in i], ["REQ"])   # 'vault' unknown
        open(os.path.join(self.d, "probes.yaml"), "w").write("- {id: vault, cmd: ['true']}\n")
        self.assertEqual([i for i in lint_facts.lint() if i.startswith("REQ")], [])

if __name__ == "__main__": unittest.main()
