"""Specs for lint_facts.py, build_primer.py and _fm.py."""
import datetime, importlib, os, shutil, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import set_env
import _fm, build_primer
TODAY = datetime.date.today()
def ago(n): return str(TODAY - datetime.timedelta(days=n))


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d)
        for n in ("facts", "workstreams", "skills"): os.makedirs(f"{self.d}/{n}")
        set_env(self, BRAIN_DIR=self.d, BRAIN_REPOS_ROOT=self.d)
        import lint_facts; self.lf = importlib.reload(lint_facts)

    def fact(self, name, fm="", body="Plain text.\n", full=True):
        head = ("title: t\nconfidence: high\nverified_at: '%s'\nsource: s\n" % ago(1) if full else "") + fm
        open(f"{self.d}/facts/{name}.md", "w").write(f"---\n{head}---\n{body}")

    def codes(self): return [i.split()[0] for i in self.lf.lint()]


class FmTest(unittest.TestCase):
    def test_frontmatter(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); p = f"{d}/a.md"
        open(p, "w").write("---\na: 1\n---\nbody\n"); self.assertEqual(_fm.frontmatter(p), ({"a": 1}, "body\n"))
        open(p, "w").write("plain"); self.assertEqual(_fm.frontmatter(p), ({}, "plain"))
        open(p, "w").write("---\na: [unclosed\n---\nb\n"); self.assertEqual(_fm.frontmatter(p), ({"_parse_error": True}, "b\n"))
        open(p, "w").write("---\na: 1\n---\n"); self.assertEqual(_fm.frontmatter(p), ({"a": 1}, ""))
        open(p, "w").write("---\na: 1\n---"); self.assertEqual(_fm.frontmatter(p), ({"a": 1}, ""))              # no trailing newline
        open(p, "w").write("---\n\n---\nbody"); self.assertEqual(_fm.frontmatter(p), ({}, "body"))             # empty frontmatter is {} not None


class Facts(Base):
    def test_clean_fact_has_no_issues(self): self.fact("ok"); self.assertEqual(self.lf.lint(), [])

    def test_missing_fields_and_parse(self):
        self.fact("a", full=False); self.assertEqual(self.codes().count("FIELD"), 3)                  # title, confidence, verified_at
        open(f"{self.d}/facts/b.md", "w").write("---\na: [x\n---\n"); self.assertIn("PARSE", self.codes())

    def test_age_thresholds(self):
        open(f"{self.d}/facts/old.md", "w").write(f"---\ntitle: t\nconfidence: high\nverified_at: '{ago(91)}'\nsource: s\n---\nx\n")
        self.assertEqual(self.codes(), ["OLD"])
        open(f"{self.d}/facts/old.md", "w").write(f"---\ntitle: t\nconfidence: high\nverified_at: '{ago(90)}'\nsource: s\n---\nx\n"); self.assertEqual(self.codes(), [])

    def test_unverified_needs_recorded_at_and_flags_after_30_days(self):
        def w(n, extra): open(f"{self.d}/facts/u.md", "w").write(f"---\ntitle: t\nconfidence: low\nverified: false\nsource: s\n{extra}---\nx\n")
        w(1, ""); self.assertEqual(self.codes(), ["FIELD"])
        w(1, f"recorded_at: '{ago(30)}'\n"); self.assertEqual(self.codes(), [])
        w(1, f"recorded_at: '{ago(31)}'\n"); self.assertEqual(self.codes(), ["UNVER"])

    def test_source_required(self):
        open(f"{self.d}/facts/s.md", "w").write(f"---\ntitle: t\nconfidence: high\nverified_at: '{ago(1)}'\n---\nx\n"); self.assertEqual(self.codes(), ["SOURCE"])
        for k in ("anchors: []\n", "verify_by: human\n"): open(f"{self.d}/facts/s.md", "w").write(f"---\ntitle: t\nconfidence: high\nverified_at: '{ago(1)}'\n{k}---\nx\n")
        open(f"{self.d}/facts/s.md", "w").write(f"---\ntitle: t\nconfidence: high\nverified_at: '{ago(1)}'\nverify_by: human\n---\nx\n"); self.assertEqual(self.codes(), [])

    def test_absolutes(self):
        self.fact("abs", body="line one\nThis will never fail.\nalways too\n"); r = self.lf.lint(); self.assertEqual(len(r), 1); self.assertIn("abs.md:2", r[0]); self.assertIn("'never'", r[0])
        self.fact("abs", fm="absolutes_ok: true\n", body="never\n"); self.assertEqual(self.lf.lint(), [])
        self.fact("abs", body="whenever and nevertheless\n"); self.assertEqual(self.lf.lint(), [])          # word boundaries

    def test_secrets_are_hard_issues(self):
        self.fact("sec", body="password: abcdefghijklmnopqrstuvwxyz0123\n"); self.assertEqual(self.codes(), ["SECRET"])
        self.fact("sec", body="key AKIAABCDEFGHIJKLMNOP\n"); self.assertEqual(self.codes(), ["SECRET"])
        self.fact("sec", body="password: short\n"); self.assertEqual(self.codes(), [])

    def test_anchor_staleness_uses_git(self):
        r = f"{self.d}/svc"; os.makedirs(r)
        git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", r, *a], capture_output=True, text=True)  # noqa: E731
        git("init", "-q", "-b", "main"); open(f"{r}/f.txt", "w").write("1"); git("add", "."); git("commit", "-qm", "c1")
        open(f"{self.d}/facts/anc.md", "w").write(f"---\ntitle: t\nconfidence: high\nverified_at: '{ago(5)}'\nanchors: ['svc@f.txt']\n---\nx\n"); self.assertEqual(self.codes(), ["STALE"])
        open(f"{self.d}/facts/anc.md", "w").write(f"---\ntitle: t\nconfidence: high\nverified_at: '{ago(5)}'\nanchors: ['svc@abc1234:f.txt']\n---\nx\n"); self.assertEqual(self.codes(), ["STALE"])   # repo@sha:path form
        open(f"{self.d}/facts/anc.md", "w").write(f"---\ntitle: t\nconfidence: high\nverified_at: '{ago(5)}'\nanchors: ['nope@f.txt']\n---\nx\n"); self.assertEqual(self.codes(), ["ANCHOR"])
        open(f"{self.d}/facts/anc.md", "w").write(f"---\ntitle: t\nconfidence: high\nverified_at: '{ago(5)}'\nanchors: ['svc@untouched.txt']\n---\nx\n"); self.assertEqual(self.codes(), [])
        open(f"{self.d}/facts/anc.md", "w").write(f"---\ntitle: t\nconfidence: high\nverified_at: '{ago(5)}'\nanchors: ['svc']\n---\nx\n"); self.assertEqual(self.codes(), ["STALE"])   # whole repo


class Others(Base):
    def test_workstream_staleness(self):
        def w(status, days): os.makedirs(f"{self.d}/workstreams/w", exist_ok=True); open(f"{self.d}/workstreams/w/STATE.md", "w").write(f"---\nslug: w\nstatus: {status}\nupdated: '{ago(days)}'\n---\n")
        w("active", 22); self.assertEqual(self.codes(), ["WS"]); w("blocked", 22); self.assertEqual(self.codes(), ["WS"])
        w("active", 21); self.assertEqual(self.codes(), []); w("done", 100); self.assertEqual(self.codes(), []); w("paused", 100); self.assertEqual(self.codes(), [])

    def test_requires_ids(self):
        open(f"{self.d}/capabilities.yaml", "w").write("- {id: c, requires: [vpn, gh, docker, 'aws:p', 'kube:ctx', 'mcp:srv']}\n"); self.assertEqual(self.lf.lint(), [])
        open(f"{self.d}/capabilities.yaml", "w").write("- {id: c, requires: [bogus]}\n"); self.assertEqual(self.codes(), ["REQ"])
        open(f"{self.d}/capabilities.yaml", "w").write("- {id: c, requires: ['aws:']}\n"); self.assertEqual(self.codes(), ["REQ"])
        open(f"{self.d}/capabilities.yaml", "w").write("- [unclosed\n"); self.assertEqual(self.codes(), ["PARSE"])

    def test_skills(self):
        def sk(name, text): os.makedirs(f"{self.d}/skills/{name}", exist_ok=True); open(f"{self.d}/skills/{name}/SKILL.md", "w").write(text)
        sk("a", "---\nname: a\ndescription: d\n---\nb\n"); self.assertEqual(self.lf.lint(), [])
        sk("a", "---\nname: other\ndescription: d\n---\nb\n"); self.assertEqual(self.codes(), ["FIELD"])
        sk("a", "---\nname: a\n---\nb\n"); self.assertEqual(self.codes(), ["FIELD"])
        sk("a", "---\nname: a\ndescription: " + "x" * 1025 + "\n---\n"); self.assertEqual(self.codes(), ["FIELD"])
        sk("a", "---\nname: a\ndescription: " + "x" * 1024 + "\n---\n"); self.assertEqual(self.lf.lint(), [])
        sk("a", "---\nname: [bad\n---\n"); self.assertEqual(self.codes(), ["PARSE"])

    def test_secret_scan_skips_digests_and_tests(self):
        for sub in ("digests", "drafts", ".cache", "tests"): os.makedirs(f"{self.d}/{sub}"); open(f"{self.d}/{sub}/x.md", "w").write("password: abcdefghijklmnopqrstuvwxyz0123\n")
        self.assertEqual(self.lf.lint(), [])
        open(f"{self.d}/top.yaml", "w").write("token: abcdefghijklmnopqrstuvwxyz0123\n"); self.assertEqual(self.codes(), ["SECRET"])

    def test_strict_exit_codes(self):
        run = lambda *a: subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "lint_facts.py"), *a], env={**os.environ, "BRAIN_DIR": self.d}, capture_output=True, text=True)  # noqa: E731
        self.assertEqual(run("--strict").returncode, 0)
        self.fact("abs", body="never\n"); self.assertEqual(run("--strict").returncode, 0)             # soft issue
        self.fact("sec", body="password: abcdefghijklmnopqrstuvwxyz0123\n"); r = run("--strict"); self.assertEqual(r.returncode, 1); self.assertIn("1 hard", r.stdout)
        self.assertEqual(run().returncode, 0)
        os.remove(f"{self.d}/facts/sec.md"); open(f"{self.d}/capabilities.yaml", "w").write("- {id: c, requires: [bogus]}\n"); self.assertEqual(run("--strict").returncode, 1)   # REQ is hard

    def test_anchor_without_any_date_looks_back_90_days(self):
        r = f"{self.d}/svc"; os.makedirs(r)
        git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", r, *a], capture_output=True, text=True)  # noqa: E731
        git("init", "-q", "-b", "main"); open(f"{r}/f.txt", "w").write("1"); git("add", "."); git("commit", "-qm", "c1")
        open(f"{self.d}/facts/nodate.md", "w").write("---\ntitle: t\nconfidence: low\nanchors: ['svc@f.txt']\n---\nx\n")
        self.assertEqual(sorted(self.codes()), ["FIELD", "STALE"])


class Primer(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d); set_env(self, PRIMER_BUDGET=None)
    def w(self, name, text): os.makedirs(os.path.dirname(f"{self.d}/{name}"), exist_ok=True); open(f"{self.d}/{name}", "w").write(text)

    def test_clip(self):
        self.assertEqual(build_primer.clip("a  b\n c", 10), "a b c"); self.assertEqual(build_primer.clip("x" * 11, 10), "x" * 9 + "…"); self.assertEqual(build_primer.clip("x" * 10, 10), "x" * 10); self.assertEqual(build_primer.clip(None, 5), "")

    def test_sections_and_ordering(self):
        self.w("brain.config.yaml", "org: Acme\nrole: data\nrepos_root: ~/p\nroutes:\n  - {need: n1, use: u1}\naccess: [a1]\n")
        self.w("style.md", "## Style\n- be brief"); self.w("skills/deploy/SKILL.md", "x")
        self.w("glossary.yaml", "- {term: Zed, kind: concept, one_liner: z, core: true}\n- {term: Beta, kind: system, one_liner: b, core: true, skill: deploy}\n- {term: Alpha, kind: system, one_liner: a, core: true}\n- {term: Hidden, kind: system, one_liner: h}\n")
        out, over = build_primer.build(self.d); self.assertFalse(over)
        self.assertIn("# Acme primer (router)", out); self.assertIn("You work at Acme (data). Repos: `~/p/<repo>`.", out); self.assertIn("be brief", out)
        self.assertIn("| n1 | u1 |", out); self.assertIn("skill `deploy`", out); self.assertIn("- a1", out); self.assertNotIn("Hidden", out)
        self.assertLess(out.index("**Alpha**"), out.index("**Beta**")); self.assertLess(out.index("**Beta**"), out.index("**Zed**"))        # system before concept, then alphabetical
        self.assertIn("**Beta** — b → `deploy`", out)

    def test_same_kind_sorts_alphabetically_and_budget_edge(self):
        self.w("glossary.yaml", "- {term: Bab, kind: system, one_liner: b, core: true}\n- {term: Abc, kind: system, one_liner: a, core: true}\n")
        out, _ = build_primer.build(self.d); self.assertLess(out.index("**Abc**"), out.index("**Bab**"))
        self.w("brain.config.yaml", f"primer_budget: {len(out)}\n"); out2, over = build_primer.build(self.d); self.assertFalse(over)        # exactly at budget is fine
        self.w("brain.config.yaml", f"primer_budget: {len(out) - 1}\n"); self.assertEqual(len(build_primer.build(self.d)[0]) <= len(out), True)

    def test_budget_equal_to_length_keeps_the_first_rendering(self):
        self.w("glossary.yaml", "- {term: Long, kind: system, one_liner: '" + "w" * 150 + "', core: true}\n")
        first, _ = build_primer.build(self.d); self.w("brain.config.yaml", f"primer_budget: {len(first)}\n")
        self.assertEqual(build_primer.build(self.d)[0], first)

    def test_minimal_brain_and_optional_sections(self):
        out, over = build_primer.build(self.d); self.assertIn("# your org primer", out); self.assertNotIn("Always-useful access", out); self.assertNotIn("Core systems", out); self.assertNotIn("deep knowledge", out)

    def test_budget_shrinks_oneliners_then_flags_over_budget(self):
        self.w("glossary.yaml", "".join(f"- {{term: T{i:02d}, kind: system, one_liner: '{'w' * 200}', core: true}}\n" for i in range(20)))
        self.w("brain.config.yaml", "primer_budget: 100000\n"); big, _ = build_primer.build(self.d)
        self.w("brain.config.yaml", "primer_budget: 3200\n"); out, over = build_primer.build(self.d)
        self.assertLess(len(out), len(big)); self.assertIn("w" * 69 + "…", out); self.assertFalse(over)
        self.w("brain.config.yaml", "primer_budget: 10\n"); self.assertTrue(build_primer.build(self.d)[1])
        set_env(self, PRIMER_BUDGET="100000"); self.assertEqual(build_primer.build(self.d)[0], big)    # env beats config

    def test_main_writes_primer(self):
        self.w("glossary.yaml", "[]\n"); r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_primer.py")], env={**os.environ, "BRAIN_DIR": self.d}, capture_output=True, text=True)
        self.assertTrue(os.path.exists(f"{self.d}/PRIMER.md")); self.assertIn("PRIMER.md", r.stdout)

if __name__ == "__main__": unittest.main()
