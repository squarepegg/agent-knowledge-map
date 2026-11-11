"""Spec for scripts/harness_check.py: repo agent-readiness score. Hand-computed fixtures (each check flipped alone), arg parsing, determinism."""
import json, os, sys, tempfile, unittest
from pathlib import Path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts")); os.environ.setdefault("BRAIN_DIR", ROOT)
import harness_check as hc  # noqa: E402

FULL_AGENTS = "Run `pytest` to test. See STATE.md. Definition of done: tests green. Provide evidence before finishing."


def mk(base, name, files):
    r = Path(base) / name
    r.mkdir(parents=True, exist_ok=True)
    for rel, txt in files.items():
        p = r / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt)
    return r


FULL = {"AGENTS.md": FULL_AGENTS, "docs/x.md": "", "pyproject.toml": "", "init.sh": "set -e", ".github/CODEOWNERS": "* @x",
        ".github/workflows/ci.yml": "run: pytest"}


class Score(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def score(self, files, name="r"):
        return hc.check(mk(self.d, name, files))

    def test_empty_repo_scores_zero_with_ten_missing(self):
        r = self.score({})
        self.assertEqual((r["score"], len(r["missing"])), (0, 10))

    def test_full_repo_scores_100_nothing_missing(self):
        r = self.score(FULL)
        self.assertEqual((r["score"], r["missing"]), (100, []))
        self.assertEqual(r["sub"], {k: 2 for k in ("instructions", "state", "verification", "scope", "lifecycle")})

    def test_each_check_is_worth_exactly_ten_and_removable_alone(self):
        for drop, label in [("docs/x.md", "docs/ or openspec/ present"), ("init.sh", "init.sh (green-baseline"),
                            (".github/CODEOWNERS", "CODEOWNERS or README ownership"), (".github/workflows/ci.yml", "tests run in CI")]:
            files = {k: v for k, v in FULL.items() if k != drop}
            r = self.score(files, name="r" + drop.replace("/", "_"))
            self.assertEqual(r["score"], 90, drop)
            self.assertEqual(len(r["missing"]), 1, drop)
            self.assertIn(label, r["missing"][0])

    def test_claude_md_counts_as_instruction_file(self):
        r = self.score({"CLAUDE.md": FULL_AGENTS})
        self.assertNotIn("instructions: AGENTS.md/CLAUDE.md exists", r["missing"])

    def test_agents_md_wins_over_claude_md(self):
        r = self.score({"AGENTS.md": "", "CLAUDE.md": FULL_AGENTS})
        self.assertIn("instructions: states build/test commands", r["missing"])

    def test_verify_entrypoint_alternatives(self):
        for f in ("init.sh", "Makefile", "justfile", "package.json", "gradlew", "pyproject.toml", "tox.ini"):
            r = self.score({f: ""}, name="e" + f)
            self.assertNotIn("verification: single verify entrypoint", " ".join(r["missing"]), f)
        self.assertIn("single verify entrypoint", " ".join(self.score({"README.md": ""}, name="none")["missing"]))

    def test_state_routing_words_and_openspec(self):
        for w in ("STATE.md", "progress", "handoff"):
            self.assertNotIn("state: progress/handoff routed", " ".join(self.score({"AGENTS.md": w}, name="s" + w)["missing"]), w)
        self.assertNotIn("docs/ or openspec/", " ".join(self.score({"openspec/a": ""}, name="os")["missing"]))

    def test_ci_detection_needs_a_test_word_and_yaml_ext(self):
        self.assertIn("tests run in CI", " ".join(self.score({".github/workflows/a.yml": "run: echo hi"}, name="a")["missing"]))
        self.assertNotIn("tests run in CI", " ".join(self.score({".github/workflows/a.yaml": "run: ./gradlew build"}, name="b")["missing"]))
        self.assertIn("tests run in CI", " ".join(self.score({".github/workflows/a.txt": "run: pytest"}, name="c")["missing"]))

    def test_codeowners_alternatives(self):
        for f in (".github/CODEOWNERS", "CODEOWNERS"):
            self.assertNotIn("CODEOWNERS", " ".join(self.score({f: "x"}, name="c" + f.replace("/", "_"))["missing"]))
        self.assertNotIn("CODEOWNERS", " ".join(self.score({"README.md": "Owner: data team"}, name="ro")["missing"]))

    def test_keywords_are_case_insensitive_and_word_bounded(self):
        self.assertNotIn("states build/test", " ".join(self.score({"AGENTS.md": "Run PYTEST"}, name="u")["missing"]))
        self.assertIn("states build/test", " ".join(self.score({"AGENTS.md": "contestant"}, name="w")["missing"]))  # 'test' inside a word doesn't count

    def test_each_command_word_and_keyword_is_accepted(self):
        for i, w in enumerate(("gradlew", "npm", "make", "cargo", "dotnet", "pytest")):
            self.assertNotIn("states build/test", " ".join(self.score({"AGENTS.md": f"run {w}"}, name=f"k{i}")["missing"]), w)
        for i, w in enumerate(("never", "do not", "scope", "Definition of done")):
            self.assertNotIn("scope: definition", " ".join(self.score({"AGENTS.md": w}, name=f"sc{i}")["missing"]), w)
        for i, w in enumerate(("evidence", "end of session", "before ending", "before finishing", "clean state")):
            self.assertNotIn("end-of-session", " ".join(self.score({"AGENTS.md": w}, name=f"ev{i}")["missing"]), w)

    def test_unreadable_file_is_treated_as_empty(self):
        r = mk(self.d, "bad", {})
        (r / "AGENTS.md").mkdir()   # a directory where a file is expected
        self.assertEqual(hc.check(r)["score"], 0)

    def test_score_is_multiple_of_ten_and_in_range(self):
        import itertools
        keys = list(FULL)
        for n in range(len(keys) + 1):
            for i, combo in enumerate(itertools.combinations(keys, n)):
                sc = hc.check(mk(self.d, f"c{n}_{i}", {k: FULL[k] for k in combo}))["score"]
                self.assertTrue(0 <= sc <= 100 and sc % 10 == 0)


class Cli(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.base = self.home / "projects"
        for name, files in [("b-good", FULL), ("a-good", FULL), ("c-bad", {})]:
            r = mk(self.base, name, files)
            (r / ".git").mkdir()
        mk(self.base, "not-a-repo", FULL)   # no .git -> skipped by --all

    def test_parse(self):
        self.assertEqual(hc.parse(["x", "--min", "80", "--json", "--all", "y"]), (["x", "y"], 80, True, True))
        self.assertEqual(hc.parse([]), ([], 60, False, False))

    def test_parse_bad_min_exits(self):
        for bad in (["--min"], ["--min", "abc"]):
            with self.assertRaises(SystemExit): hc.parse(bad)

    def test_all_scans_only_git_repos_sorted_by_score_then_name(self):
        code, out = hc.run(["--all", "--json"], home=self.home)
        self.assertEqual([r["repo"] for r in json.loads(out)], ["c-bad", "a-good", "b-good"])
        self.assertEqual(code, 1)   # c-bad < 60

    def test_exit_code_threshold_is_inclusive(self):
        d = str(self.base / "a-good")
        self.assertEqual(hc.run([d, "--min", "100"])[0], 0)
        self.assertEqual(hc.run([d, "--min", "101"])[0], 1)
        c = str(self.base / "c-bad")
        self.assertEqual(hc.run([c, "--min", "0"])[0], 0)

    def test_missing_dir_is_error_not_zero_score(self):
        code, out = hc.run([str(self.base / "nope")])
        self.assertEqual(code, 2)
        self.assertIn("not a directory", out)

    def test_text_output_lists_score_name_and_first_three_missing(self):
        _, out = hc.run([str(self.base / "c-bad")])
        self.assertTrue(out.startswith("  0  c-bad"))
        self.assertEqual(out.count(";"), 2)

    def test_deterministic_across_runs_and_arg_order(self):
        a, b = str(self.base / "a-good"), str(self.base / "b-good")
        self.assertEqual(hc.run([a, b, "--json"]), hc.run([b, a, "--json"]))
        self.assertEqual(hc.run(["--all"], home=self.home), hc.run(["--all"], home=self.home))

    def test_default_dir_is_cwd(self):
        old = os.getcwd(); os.chdir(self.base / "a-good")
        try: self.assertEqual(hc.run(["--json"])[0], 0)
        finally: os.chdir(old)


class RealRepoSmoke(unittest.TestCase):
    def test_the_brain_repo_itself_is_scored_without_error(self):
        r = hc.check(Path(ROOT))
        self.assertTrue(0 <= r["score"] <= 100)


if __name__ == "__main__":
    unittest.main()
