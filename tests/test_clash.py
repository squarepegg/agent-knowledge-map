"""Specs for clash.py: two documents that give opposite directives about the same backticked object (context clash).
Precision over recall: only `backticked` objects, only directive words, one sentence at a time."""
import importlib, os, shutil, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts")); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import set_env
import clash


def doc(id, text, repos=None, ok=()): return {"id": id, "text": text, "repos": set(repos or ()), "clash_ok": {clash.norm(o) for o in ok}}


class Directives(unittest.TestCase):
    def test_positive_and_negative(self):
        self.assertEqual(clash.directives("Always use `uv` here."), [("+", "uv")])
        self.assertEqual(clash.directives("Never use `pip`."), [("-", "pip")])
        self.assertEqual(clash.directives("Do not run `rm -rf`."), [("-", "rm -rf")])

    def test_negation_wins_inside_one_sentence(self):
        for s in ("You must not call `x`.", "We should not use `x`.", "Don't use `x`.", "Avoid `x`."): self.assertEqual(clash.directives(s), [("-", "x")], s)

    def test_sentences_are_independent(self):
        self.assertEqual(sorted(clash.directives("Never use `pip`; use `uv` instead.\nAlways run `make`.")), [("+", "make"), ("+", "uv"), ("-", "pip")])

    def test_object_must_be_backticked_and_near_the_directive(self):
        self.assertEqual(clash.directives("Never use pip."), [])
        self.assertEqual(clash.directives("Never " + "x" * 60 + " `pip`."), [])
        self.assertEqual(clash.directives("Use `a` or `b`."), [("+", "a"), ("+", "b")])   # a directive covers every object in its sentence

    def test_dots_inside_backticks_do_not_end_the_sentence(self):
        self.assertEqual(clash.directives("Never run `brain.py note` with secrets."), [("-", "brain.py note")])

    def test_object_is_case_and_space_normalised(self):
        self.assertEqual(clash.directives("Use ` Docker  Compose `."), [("+", "docker compose")])

    def test_counterexamples_section_is_not_a_directive(self):
        t = "## Meaning\nUse `a`.\n## Counterexamples\nNever use `a` when b.\n## Change when\nAvoid `c`.\n"
        self.assertEqual(sorted(clash.directives(t)), [("+", "a"), ("-", "c")])


class Find(unittest.TestCase):
    def test_opposite_directives_in_two_docs_clash(self):
        r = clash.find_clashes([doc("facts/a.md", "Use `rsync` for deploys."), doc("facts/b.md", "Do not use `rsync` for deploys.")])
        self.assertEqual(r, [("rsync", "facts/a.md", "facts/b.md")])

    def test_same_doc_same_polarity_and_other_objects_do_not_clash(self):
        self.assertEqual(clash.find_clashes([doc("a", "Never use `pip`; use `uv`.")]), [])
        self.assertEqual(clash.find_clashes([doc("a", "Use `x` locally. Never use `x` in prod.")]), [])   # scoping inside one doc is the author's business
        self.assertEqual(clash.find_clashes([doc("a", "Use `x`."), doc("b", "Always use `x`.")]), [])
        self.assertEqual(clash.find_clashes([doc("a", "Use `x`."), doc("b", "Never use `y`.")]), [])

    def test_disjoint_repos_are_different_scopes(self):
        a, b = "Use `x`.", "Never use `x`."
        self.assertEqual(clash.find_clashes([doc("a", a, ["r1"]), doc("b", b, ["r2"])]), [])
        self.assertEqual(len(clash.find_clashes([doc("a", a, ["r1", "r2"]), doc("b", b, ["r2"])])), 1)
        self.assertEqual(len(clash.find_clashes([doc("a", a, ["r1"]), doc("b", b)])), 1)   # unscoped doc applies everywhere

    def test_clash_ok_on_either_side_resolves_that_object_only(self):
        a, b = "Use `x` and `y`.", "Never use `x` or `y`."
        self.assertEqual([c[0] for c in clash.find_clashes([doc("a", a, ok=["X"]), doc("b", b)])], ["y"])
        self.assertEqual([c[0] for c in clash.find_clashes([doc("a", a), doc("b", b, ok=["y"])])], ["x"])

    def test_result_is_sorted_and_each_pair_reported_once(self):
        docs = [doc("b", "Never use `x`."), doc("a", "Use `x`."), doc("c", "Use `x`.")]
        self.assertEqual(clash.find_clashes(docs), [("x", "a", "b"), ("x", "c", "b")])
        many = [doc(n, "Use `x`.") for n in "fcaedb"] + [doc("z", "Never use `x`.")]
        self.assertEqual(clash.find_clashes(many), [("x", n, "z") for n in "abcdef"])


class Brain(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d)
        for n in ("facts", "skills/s"): os.makedirs(f"{self.d}/{n}")
        set_env(self, BRAIN_DIR=self.d, BRAIN_REPOS_ROOT=self.d)

    def put(self, rel, fm, body): open(f"{self.d}/{rel}", "w").write(f"---\n{fm}---\n{body}")

    def cli(self, *a):
        return subprocess.run([sys.executable, f"{ROOT}/scripts/clash.py", *a], capture_output=True, text=True, env={**os.environ, "BRAIN_DIR": self.d})

    def test_fact_against_skill_is_found_from_the_cli_and_by_lint(self):
        self.put("facts/deploy.md", "title: t\nrepos: [r]\n", "Never use `rsync` to deploy.\n")
        self.put("skills/s/SKILL.md", "name: s\ndescription: d\n", "Use `rsync` to deploy.\n")
        r = self.cli(); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("`rsync`", r.stdout); self.assertIn("skills/s/SKILL.md", r.stdout); self.assertIn("facts/deploy.md", r.stdout)
        self.assertEqual(self.cli("--strict").returncode, 1)
        import lint_facts; lf = importlib.reload(lint_facts)
        self.assertEqual([i.split()[0] for i in lf.lint() if i.startswith("CLASH")], ["CLASH"])
        self.assertNotIn("CLASH", lf.HARD)   # advisory: lint --strict must not fail on a heuristic

    def test_frontmatter_clash_ok_silences_it(self):
        self.put("facts/a.md", "title: t\nclash_ok: [rsync]\n", "Never use `rsync` to deploy.\n")
        self.put("facts/b.md", "title: t\n", "Use `rsync` to deploy.\n")
        r = self.cli("--strict"); self.assertEqual(r.returncode, 0); self.assertIn("no clashes", r.stdout)

    def test_unparseable_frontmatter_is_skipped_not_fatal(self):
        open(f"{self.d}/facts/bad.md", "w").write("---\na: [x\n---\nUse `x`.\n")
        self.put("facts/b.md", "title: t\n", "Never use `x`.\n")
        r = self.cli("--strict"); self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__": unittest.main()
