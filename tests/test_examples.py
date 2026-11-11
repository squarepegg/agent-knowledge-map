"""Every shipped example brain is complete, lint-clean, passes its own evals, and its evals are meaningful (they fail without the example)."""
import glob, io, os, re, shutil, sys, tempfile, unittest, contextlib, importlib
import yaml
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts")); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import fixture_brain, set_env
import init_brain, eval_run
from _fm import frontmatter

EXAMPLES = sorted(os.path.basename(p) for p in glob.glob(f"{ROOT}/examples/*") if os.path.isdir(p))
BANNED = [b.strip() for b in os.environ.get("TEMPLATE_BANNED", "@gmail,@acme.com").split(",") if b.strip()]
def env(tc, d): set_env(tc, BRAIN_DIR=d, BRAIN_REPOS_ROOT=d)

def evals(d, path=None):
    eval_run.B = d
    with contextlib.redirect_stdout(io.StringIO()) as o: rc = eval_run.main(["x", path or os.path.join(d, "evals", "questions.yaml")])
    return rc, o.getvalue()


class Shape(unittest.TestCase):
    def test_four_examples_ship(self): self.assertEqual(EXAMPLES, ["data-team", "platform-infra", "solo-dev", "web-app"])

    def test_each_example_is_complete(self):
        for ex in EXAMPLES:
            base = f"{ROOT}/examples/{ex}"
            for f in ("brain.config.yaml", "glossary.yaml", "capabilities.yaml", "probes.yaml", "evals/questions.yaml"): self.assertTrue(os.path.exists(f"{base}/{f}"), f"{ex}/{f}")
            facts = glob.glob(f"{base}/facts/*.md"); self.assertGreaterEqual(len(facts), 5, ex)
            self.assertGreaterEqual(len(glob.glob(f"{base}/workstreams/*/STATE.md")), 1, ex); self.assertGreaterEqual(len(glob.glob(f"{base}/decisions/*.md")), 1, ex)
            qs = yaml.safe_load(open(f"{base}/evals/questions.yaml")); self.assertGreaterEqual(len(qs), 6, ex); self.assertEqual(len({q["id"] for q in qs}), len(qs), f"{ex}: duplicate eval ids")
            self.assertTrue(any(q.get("first_line") for q in qs), f"{ex}: no ranking assertion")
            cfg = yaml.safe_load(open(f"{base}/brain.config.yaml")); self.assertTrue(cfg["org"] and cfg["routes"] and cfg["access"], ex)
            self.assertTrue(any(g.get("core") for g in yaml.safe_load(open(f"{base}/glossary.yaml"))), f"{ex}: nothing in the primer")
            for p in facts:
                fm, body = frontmatter(p); self.assertTrue(fm.get("title") and fm.get("source") and fm.get("verified_at") and fm.get("confidence"), p); self.assertGreater(len(body.strip()), 80, p)

    def test_examples_are_distinct_and_generic(self):
        titles = {}
        for ex in EXAMPLES:
            for p in glob.glob(f"{ROOT}/examples/{ex}/**/*", recursive=True):
                if os.path.isfile(p):
                    low = open(p, errors="ignore").read().lower()
                    for b in BANNED: self.assertNotIn(b, low, f"{p}: {b}")
            for p in glob.glob(f"{ROOT}/examples/{ex}/facts/*.md"): titles.setdefault(frontmatter(p)[0]["title"], []).append(ex)
        self.assertEqual({t: e for t, e in titles.items() if len(e) > 1}, {})
        self.assertEqual(len({open(f"{ROOT}/examples/{e}/brain.config.yaml").read() for e in EXAMPLES}), len(EXAMPLES))


class Applied(unittest.TestCase):
    def apply(self, ex):
        d = fixture_brain(); self.addCleanup(shutil.rmtree, d); os.makedirs(f"{d}/evals", exist_ok=True)
        shutil.copy(f"{ROOT}/evals/questions.yaml", f"{d}/evals/questions.yaml"); shutil.copytree(f"{ROOT}/tests/fixtures", f"{d}/tests/fixtures", dirs_exist_ok=True)
        return d, init_brain.apply_example(d, ex)

    def test_lint_primer_and_evals_pass_for_every_example(self):
        for ex in EXAMPLES:
            d, acts = self.apply(ex); env(self, d); import lint_facts; lf = importlib.reload(lint_facts)
            issues = lf.lint(); hard = [i for i in issues if i.split()[0] in lf.HARD]; self.assertEqual(hard, [], ex)
            self.assertEqual(issues, [], f"{ex}: a freshly applied example must lint completely clean")
            import build_primer; out, over = build_primer.build(d); self.assertFalse(over, ex); org = yaml.safe_load(open(f"{d}/brain.config.yaml"))["org"]; self.assertIn(org, out)
            self.assertFalse(os.path.exists(f"{d}/facts/example-fact.md"), "placeholder removed")
            rc, out = evals(d); self.assertEqual(rc, 0, f"{ex}:\n{out}"); n = len(yaml.safe_load(open(f"{ROOT}/examples/{ex}/evals/questions.yaml")))
            self.assertGreaterEqual(out.count("PASS"), n); self.assertNotIn("FAIL", out)

    def test_example_evals_fail_without_the_example(self):
        for ex in EXAMPLES:
            d = fixture_brain(); self.addCleanup(shutil.rmtree, d); env(self, d)
            rc, out = evals(d, f"{ROOT}/examples/{ex}/evals/questions.yaml"); self.assertEqual(rc, 1, f"{ex}: evals pass without the example, so they prove nothing")
            qs = yaml.safe_load(open(f"{ROOT}/examples/{ex}/evals/questions.yaml")); self.assertEqual(out.count("FAIL"), len(qs), f"{ex}: every question must need the example")

    def test_apply_is_idempotent_and_respects_user_edits(self):
        d, first = self.apply("web-app"); self.assertTrue(any(a.startswith("added facts/") for a in first)); self.assertIn("appended 7 eval question(s)", first)
        again = init_brain.apply_example(d, "web-app"); self.assertEqual(again, [])
        open(f"{d}/glossary.yaml", "w").write("- {term: Mine, kind: concept, one_liner: mine}\n"); open(f"{d}/facts/deploy-canary.md", "w").write("edited")
        acts = init_brain.apply_example(d, "web-app"); self.assertIn("kept your glossary.yaml (use --force to overwrite)", acts); self.assertIn("kept your facts/deploy-canary.md (use --force to overwrite)", acts)
        self.assertEqual(open(f"{d}/facts/deploy-canary.md").read(), "edited")
        acts = init_brain.apply_example(d, "web-app", force=True); self.assertIn("replaced glossary.yaml", acts); self.assertNotEqual(open(f"{d}/facts/deploy-canary.md").read(), "edited")

    def test_untouched_template_files_are_replaced_and_other_examples_coexist(self):
        d, acts = self.apply("data-team"); self.assertIn("replaced brain.config.yaml", acts); self.assertIn("replaced glossary.yaml", acts); self.assertIn("Acme Data", open(f"{d}/brain.config.yaml").read())
        acts2 = init_brain.apply_example(d, "solo-dev"); self.assertIn("kept your brain.config.yaml (use --force to overwrite)", acts2)       # the first example's config is now "yours"
        self.assertTrue(os.path.exists(f"{d}/facts/dotfiles-bootstrap.md")); self.assertTrue(os.path.exists(f"{d}/facts/daily-core-sla.md"))

    def test_dates_are_stamped_with_today_so_examples_never_look_stale(self):
        d, _ = self.apply("data-team"); today = str(__import__("datetime").date.today())
        for p in glob.glob(f"{d}/facts/*.md"): self.assertEqual(str(frontmatter(p)[0]["verified_at"]), today, p)
        self.assertEqual(str(frontmatter(f"{d}/workstreams/revenue-metric-v2/STATE.md")[0]["updated"]), today)
        self.assertEqual(open(f"{d}/decisions/2025-01-10-use-metric-layer.md").read(), open(f"{ROOT}/examples/data-team/decisions/2025-01-10-use-metric-layer.md").read())   # only facts/workstreams are stamped
        d2 = fixture_brain(); self.addCleanup(shutil.rmtree, d2); init_brain.apply_example(d2, "data-team", today="2030-02-03")
        self.assertEqual(str(frontmatter(f"{d2}/facts/daily-core-sla.md")[0]["verified_at"]), "2030-02-03")

    def test_stamp_scope(self):
        st = lambda rel, t: init_brain._stamp(rel, t, "2030-01-01")  # noqa: E731
        self.assertEqual(st("facts/a.md", b"x\nverified_at: '2020-01-01'\n"), b"x\nverified_at: '2030-01-01'\n"); self.assertEqual(st("workstreams/w/STATE.md", b"updated: 2020-01-01\n"), b"updated: '2030-01-01'\n")
        self.assertEqual(st("decisions/d.md", b"updated: 2020-01-01\n"), b"updated: 2020-01-01\n"); self.assertEqual(st("facts/a.yaml", b"verified_at: 1\n"), b"verified_at: 1\n")
        self.assertEqual(st("facts/a.md", b"verified_at: 1\nupdated: 2\n"), b"verified_at: '2030-01-01'\nupdated: 2\n")          # first occurrence only (frontmatter)

    def test_stray_files_are_not_examples_and_base_questions_survive(self):
        d, _ = self.apply("web-app"); open(f"{d}/examples/NOTES.md", "w").write("x"); self.assertNotIn("NOTES.md", init_brain.examples_available(d))
        ids = [q["id"] for q in yaml.safe_load(open(f"{d}/evals/questions.yaml"))]; self.assertIn("deploy-path", ids); self.assertIn("deploy", ids); self.assertEqual(len(ids), len(set(ids)))

    def test_placeholders_are_cleaned_from_files_you_kept(self):
        d = fixture_brain(); self.addCleanup(shutil.rmtree, d)
        open(f"{d}/glossary.yaml", "w").write("- {term: Example Service, kind: system, one_liner: p}\n- {term: Mine, kind: concept, one_liner: mine}\n")
        acts = init_brain.apply_example(d, "solo-dev"); self.assertIn("kept your glossary.yaml (use --force to overwrite)", acts); self.assertIn("removed example from glossary.yaml", acts)
        self.assertEqual([g["term"] for g in yaml.safe_load(open(f"{d}/glossary.yaml"))], ["Mine"])

    def test_cli_example_flags(self):
        import subprocess, site
        d = fixture_brain(); h = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); self.addCleanup(shutil.rmtree, h)
        e = {**os.environ, "BRAIN_DIR": d, "HOME": h, "PYTHONUSERBASE": site.getuserbase()}
        run = lambda *a: subprocess.run([sys.executable, f"{d}/scripts/brain.py", "init", *a], env=e, capture_output=True, text=True)  # noqa: E731
        r = run("--example", "web-app", "--org", "Zed Shop"); self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("added facts/deploy-canary.md", r.stdout); self.assertIn('org: "Zed Shop"', open(f"{d}/brain.config.yaml").read())
        open(f"{d}/facts/deploy-canary.md", "w").write("mine")
        run("--example", "web-app"); self.assertEqual(open(f"{d}/facts/deploy-canary.md").read(), "mine")                  # no --force: kept
        run("--example", "web-app", "--force"); self.assertNotEqual(open(f"{d}/facts/deploy-canary.md").read(), "mine")      # --force: replaced
        bad = run("--example", "nope"); self.assertNotEqual(bad.returncode, 0); self.assertIn("web-app", bad.stderr)
        plain = run(); self.assertEqual(plain.returncode, 0); self.assertTrue(os.path.exists(f"{d}/facts/deploy-canary.md"))   # without --example nothing is applied or removed

    def test_unknown_example_lists_the_available_ones(self):
        d = fixture_brain(); self.addCleanup(shutil.rmtree, d)
        with self.assertRaises(SystemExit) as e: init_brain.apply_example(d, "nope")
        self.assertIn("data-team, platform-infra, solo-dev, web-app", str(e.exception)); self.assertEqual(init_brain.examples_available(tempfile.gettempdir() + "/none-xyz"), [])

if __name__ == "__main__": unittest.main()
