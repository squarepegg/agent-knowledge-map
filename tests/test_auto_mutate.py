"""Spec for scripts/auto_mutate.py: automatic AST mutation scoring + ratchet for scripts that have no hand-written mutants yet."""
import ast, contextlib, io, json, os, subprocess, sys, tempfile, textwrap, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import auto_mutate as am  # noqa: E402
import mutation_check as mc  # noqa: E402

SRC = textwrap.dedent('''
    """module docstring"""
    LIMIT = 10
    def f(a, b):
        """doc"""
        if a == b and not (a < 3):
            return a + b
        x = True if a > 1 or b is None else False
        return "text" if x else None
    def g(items):
        for i in items:
            if i in items: pass
        return 5
''')


def kinds(src): return [k for k, _ in am.candidates(src)]
def idx(src, kind): return kinds(src).index(kind)


class Candidates(unittest.TestCase):
    def test_expected_operator_kinds_are_found(self):
        ks = set(kinds(SRC))
        for k in ("cmp:Eq->NotEq", "cmp:Lt->GtE", "cmp:Gt->LtE", "cmp:Is->IsNot", "cmp:In->NotIn", "bool:And->Or", "bool:Or->And", "bin:Add->Sub", "not:remove", "if:negate", "ret:None", "const:True->False", "const:False->True", "const:int+1"):
            self.assertIn(k, ks)

    def test_docstrings_and_plain_strings_are_not_mutated(self):
        for i, (k, _) in enumerate(am.candidates(SRC)):
            o = am.apply_mutation(SRC, i); self.assertIn("module docstring", o); self.assertIn('"""doc"""', o)
            if k != "ret:None": self.assertIn("text", o)   # (ret:None legitimately replaces the whole return expression)

    def test_every_mutant_compiles_and_differs_from_the_original(self):
        base = ast.unparse(ast.parse(SRC))
        for i in range(len(am.candidates(SRC))):
            m = am.apply_mutation(SRC, i); compile(m, "m", "exec"); self.assertNotEqual(ast.unparse(ast.parse(m)), base, f"mutant {i} is a no-op")

    def test_each_operator_changes_behaviour_as_named(self):
        src = "def f(a, b):\n    return a == b\n"
        ns = {}; exec(am.apply_mutation(src, idx(src, "cmp:Eq->NotEq")), ns); self.assertEqual((ns["f"](1, 1), ns["f"](1, 2)), (False, True))
        src2 = "def f(a, b):\n    return a and b\n"; ns = {}; exec(am.apply_mutation(src2, idx(src2, "bool:And->Or")), ns); self.assertEqual(ns["f"](0, 5), 5)  # and -> or
        src3 = "def f():\n    return 4 + 1\n"; ns = {}; exec(am.apply_mutation(src3, [k for k, _ in am.candidates(src3)].index("bin:Add->Sub")), ns); self.assertEqual(ns["f"](), 3)
        src4 = "def f(x):\n    if x: return 1\n    return 2\n"; ns = {}; exec(am.apply_mutation(src4, [k for k, _ in am.candidates(src4)].index("if:negate")), ns); self.assertEqual((ns["f"](1), ns["f"](0)), (2, 1))
        src5 = "def f():\n    return 7\n"; ns = {}; exec(am.apply_mutation(src5, [k for k, _ in am.candidates(src5)].index("ret:None")), ns); self.assertIsNone(ns["f"]())
        src6 = "def f():\n    return 7\n"; ns = {}; exec(am.apply_mutation(src6, [k for k, _ in am.candidates(src6)].index("const:int+1")), ns); self.assertEqual(ns["f"](), 8)
        src7 = "def f(x):\n    return not x\n"; ns = {}; exec(am.apply_mutation(src7, idx(src7, "not:remove")), ns); self.assertEqual((ns["f"](0), ns["f"](1)), (0, 1))

    def test_ints_are_only_mutated_where_they_carry_logic(self):
        ik = lambda src: kinds(src).count("const:int+1")  # noqa: E731
        self.assertEqual(ik("f(3)\nx = [1, 2][0]\ny = 5\nz = dict(a=7)\n"), 0)       # call args, subscripts, plain assignments, keyword values: noise (timeouts, indexes, sys.path.insert(0, ..))
        self.assertEqual(ik("def f(a):\n    return a > 3\n"), 1)                 # comparison operand
        self.assertEqual(ik("x = a + 4\n"), 1)                                    # arithmetic operand
        self.assertEqual(ik("x = 3 < a\n"), 1); self.assertEqual(ik("x = 4 + a\n"), 1)     # left-hand operands too
        self.assertEqual(ik("x = a == True\n"), 0)                                # bools are flipped, never also treated as ints
        self.assertEqual(ik("def f():\n    return 5\n"), 1)                      # returned value
        self.assertEqual(ik("x += 2\n"), 1)                                       # augmented assignment value

    def test_main_guard_block_is_not_mutated(self):
        self.assertEqual(kinds('if __name__ == "__main__":\n    main()\n'), [])

    def test_returns_none_and_bare_returns_are_not_candidates_for_ret_none(self):
        self.assertNotIn("ret:None", kinds("def f():\n    return None\n    return\n"))

    def test_out_of_range_index_raises_including_exactly_one_past_the_end(self):
        n = len(am.candidates("x = 1\n"))
        with self.assertRaises(IndexError): am.apply_mutation("x = 1\n", 99)
        with self.assertRaises(IndexError): am.apply_mutation("x = 1\n", n)

    def test_things_that_must_not_be_mutated(self):
        self.assertEqual(kinds("True\n"), [])                      # bare expression statements (docstring-like) are skipped
        self.assertEqual([k for k in kinds("ok = 1 < 2 < 3\n") if k.startswith("cmp:")], [])  # chained comparisons: no single swap is well-defined
        self.assertEqual([k for k in kinds("x = 2 * 3\ny = 8 / 2\nz = 7 - 1\n") if k.startswith("bin:")], ["bin:Sub->Add"])  # only + and - are swapped
        self.assertEqual(kinds("x = 'a' + 'b'\n").count("bin:Add->Sub"), 1)


class Sampling(unittest.TestCase):
    def test_deterministic_sorted_and_bounded(self):
        a = am.pick(100, 10, seed=1); self.assertEqual(a, am.pick(100, 10, seed=1)); self.assertEqual(len(a), 10); self.assertEqual(a, sorted(a)); self.assertEqual(len(set(a)), 10)
        self.assertNotEqual(a, am.pick(100, 10, seed=2)); self.assertTrue(all(0 <= i < 100 for i in a))

    def test_population_one_above_the_limit_is_still_sampled(self):
        self.assertEqual(len(am.pick(11, 10, seed=1)), 10)

    def test_small_populations_return_everything(self):
        self.assertEqual(am.pick(5, 10, seed=1), [0, 1, 2, 3, 4]); self.assertEqual(am.pick(0, 10, seed=1), [])


class TestModules(unittest.TestCase):
    def test_finds_test_files_that_mention_the_script_by_word(self):
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "tests")); os.makedirs(os.path.join(d, "scripts"))
        open(os.path.join(d, "tests", "test_a.py"), "w").write("import widget\n"); open(os.path.join(d, "tests", "test_b.py"), "w").write("# widgets are unrelated\n")
        open(os.path.join(d, "tests", "helper.py"), "w").write("import widget\n"); open(os.path.join(d, "tests", "t.test.mjs"), "w").write("widget")
        open(os.path.join(d, "tests", "test_c.py"), "w").write("widget = 1\n"); open(os.path.join(d, "tests", "not_a_test.py"), "w").write("widget\n")
        open(os.path.join(d, "tests", "test_contracts_safety.py"), "w").write("widget\n")   # structure tests mention everything: never used to score behaviour
        self.assertEqual(am.test_modules(d, "widget"), ["tests.test_a", "tests.test_c"])  # whole-word match, test_*.py only, sorted


class Scoring(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.old = mc.ROOT; mc.ROOT = self.d
        os.makedirs(os.path.join(self.d, "scripts")); os.makedirs(os.path.join(self.d, "tests"))
        open(os.path.join(self.d, "scripts", "calc.py"), "w").write("def add(a, b):\n    return a + b\n\ndef sign(x):\n    if x > 0:\n        return 1\n    return 0\n")
        open(os.path.join(self.d, "tests", "test_calc.py"), "w").write(
            "import os, sys, unittest\nsys.path.insert(0, os.path.join(os.environ['BRAIN_DIR'], 'scripts'))\nimport calc\n"
            "class T(unittest.TestCase):\n    def test_add(self): self.assertEqual(calc.add(1, 2), 3)\n")   # sign() is untested

    def tearDown(self): mc.ROOT = self.old

    def test_score_counts_killed_and_lists_surviving_mutants_with_lines(self):
        r = am.score("scripts/calc.py", max_mutants=50, seed=1, jobs=2)
        self.assertEqual(r["tests"], ["tests.test_calc"]); self.assertGreater(r["total"], 3)
        self.assertEqual(r["killed"] + len(r["survivors"]), r["total"]); self.assertAlmostEqual(r["score"], r["killed"] / r["total"], 3)
        self.assertTrue(all(s["line"] >= 4 for s in r["survivors"]), r["survivors"])  # only sign() (lines 4-7) survives
        self.assertTrue(any(s["line"] == 2 for s in []) or True); self.assertGreater(len(r["survivors"]), 0); self.assertLess(r["score"], 1)
        self.assertFalse([s for s in r["survivors"] if s["line"] == 2], "the add() mutants must be killed")

    def test_total_is_the_sample_size_not_the_population(self):
        self.assertEqual(am.score("scripts/calc.py", max_mutants=3, seed=1, jobs=1)["total"], 3)

    def test_a_mutant_that_cannot_be_built_counts_as_killed(self):
        real = am.apply_mutation
        am.apply_mutation = lambda src, i: (_ for _ in ()).throw(RuntimeError("cannot unparse"))
        try: r = am.score("scripts/calc.py", max_mutants=4, seed=1, jobs=1)
        finally: am.apply_mutation = real
        self.assertEqual((r["killed"], r["survivors"]), (r["total"], []))

    def test_no_tests_scores_zero_with_a_clear_reason(self):
        os.remove(os.path.join(self.d, "tests", "test_calc.py"))
        r = am.score("scripts/calc.py", max_mutants=5, seed=1, jobs=1); self.assertEqual((r["killed"], r["score"]), (0, 0.0)); self.assertIn("no test", r["note"])

    def test_failing_baseline_is_an_error_not_a_score(self):
        open(os.path.join(self.d, "tests", "test_calc.py"), "a").write("    def test_red(self): self.fail('x')\n")
        r = am.score("scripts/calc.py", max_mutants=5, seed=1, jobs=1); self.assertIsNone(r["score"]); self.assertIn("baseline", r["note"])


class Ratchet(unittest.TestCase):
    REC = {"scripts/a.py": {"score": 0.70, "total": 30}, "scripts/b.py": {"score": 0.50, "total": 30}}

    def test_regression_beyond_tolerance_fails_improvement_and_equal_pass(self):
        now = {"scripts/a.py": {"score": 0.60, "total": 30}, "scripts/b.py": {"score": 0.55, "total": 30}}
        bad = am.regressions(self.REC, now, tolerance=0.05); self.assertEqual([b[0] for b in bad], ["scripts/a.py"])
        self.assertEqual(am.regressions(self.REC, {"scripts/a.py": {"score": 0.65, "total": 30}}, tolerance=0.05), [])  # exactly at tolerance: ok

    def test_unrecorded_and_errored_scripts(self):
        self.assertEqual(am.regressions(self.REC, {"scripts/new.py": {"score": 0.1, "total": 5}}, tolerance=0.05), [])  # new scripts are recorded, not failed
        e = am.regressions(self.REC, {"scripts/a.py": {"score": None, "total": 0, "note": "baseline fails"}}, tolerance=0.05); self.assertEqual([x[0] for x in e], ["scripts/a.py"])


class Cli(unittest.TestCase):
    def run_cli(self, d, *args):
        return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "auto_mutate.py"), *args], env={**os.environ, "MUTATION_ROOT": d}, capture_output=True, text=True)

    def project(self):
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "scripts")); os.makedirs(os.path.join(d, "tests", "mutants"))
        open(os.path.join(d, "scripts", "calc.py"), "w").write("def add(a, b):\n    return a + b\n")
        open(os.path.join(d, "tests", "test_calc.py"), "w").write("import os, sys, unittest\nsys.path.insert(0, os.path.join(os.environ['BRAIN_DIR'], 'scripts'))\nimport calc\nclass T(unittest.TestCase):\n    def test_add(self): self.assertEqual(calc.add(1, 2), 3)\n")
        open(os.path.join(d, "tests", "mutants", "GRANDFATHERED.txt"), "w").write("# c\nscripts/calc.py\n")
        return d

    def test_update_then_check_roundtrip_and_regression_exit_code(self):
        d = self.project(); rec = os.path.join(d, "tests", "mutants", "legacy_scores.json")
        r = self.run_cli(d, "--update", "--max", "10", "--jobs", "1"); self.assertEqual(r.returncode, 0, r.stderr); saved = json.load(open(rec))
        self.assertEqual(list(saved["scripts"]), ["scripts/calc.py"]); self.assertEqual(saved["scripts"]["scripts/calc.py"]["score"], 1.0)
        self.assertEqual(self.run_cli(d, "--check", "--max", "10", "--jobs", "1").returncode, 0)
        open(os.path.join(d, "tests", "test_calc.py"), "w").write("import unittest\nclass T(unittest.TestCase):\n    def test_nothing(self): pass\nimport calc\n")   # tests stop catching mutants
        bad = self.run_cli(d, "--check", "--max", "10", "--jobs", "1"); self.assertEqual(bad.returncode, 1); self.assertIn("REGRESSION", bad.stdout)

    def test_defaults_and_survivor_cap_in_the_record(self):
        d = self.project(); body = "def f(a):\n" + "".join(f"    if a == {i}: return {i}\n" for i in range(40)) + "    return -1\n"
        open(os.path.join(d, "scripts", "calc.py"), "w").write(body)
        open(os.path.join(d, "tests", "test_calc.py"), "w").write("import os, sys, unittest\nsys.path.insert(0, os.path.join(os.environ['BRAIN_DIR'], 'scripts'))\nimport calc\nclass T(unittest.TestCase):\n    def test_f(self): self.assertTrue(callable(calc.f))\n")
        self.assertEqual(self.run_cli(d, "--update", "--jobs", "2").returncode, 0)
        saved = json.load(open(os.path.join(d, "tests", "mutants", "legacy_scores.json")))
        self.assertEqual((saved["seed"], saved["max"]), (1, 30)); r = saved["scripts"]["scripts/calc.py"]; self.assertEqual(r["total"], 30); self.assertEqual(len(r["survivors"]), 15)

    def test_update_with_script_arguments_rescored_only_those_and_keeps_the_rest(self):
        d = self.project(); rec = os.path.join(d, "tests", "mutants", "legacy_scores.json")
        open(os.path.join(d, "scripts", "other.py"), "w").write("def f(a):\n    return a + 1\n"); open(os.path.join(d, "tests", "test_other.py"), "w").write("import os, sys, unittest\nsys.path.insert(0, os.path.join(os.environ['BRAIN_DIR'], 'scripts'))\nimport other\nclass T(unittest.TestCase):\n    def test_f(self): self.assertEqual(other.f(1), 2)\n")
        open(os.path.join(d, "tests", "mutants", "GRANDFATHERED.txt"), "w").write("scripts/calc.py\nscripts/other.py\n")
        self.assertEqual(self.run_cli(d, "--update", "--max", "10", "--jobs", "1").returncode, 0); first = json.load(open(rec))
        first["scripts"]["scripts/calc.py"]["score"] = 0.123; first["scripts"]["scripts/other.py"]["score"] = 0.5; json.dump(first, open(rec, "w"))   # markers: calc must survive a partial update, other must be overwritten
        self.assertEqual(self.run_cli(d, "--update", "scripts/other.py", "--max", "10", "--jobs", "1").returncode, 0)
        now = json.load(open(rec))["scripts"]; self.assertEqual(now["scripts/calc.py"]["score"], 0.123); self.assertEqual(now["scripts/other.py"]["score"], 1.0)
        r = self.run_cli(d, "--check", "scripts/other.py", "--max", "10", "--jobs", "1"); self.assertEqual(r.returncode, 0); self.assertNotIn("calc.py", r.stdout)   # --check also honours explicit scripts
        stale = json.load(open(rec)); stale["scripts"]["scripts/removed.py"] = {"score": 0.9}; json.dump(stale, open(rec, "w"))
        self.assertEqual(self.run_cli(d, "--update", "--max", "10", "--jobs", "1").returncode, 0); self.assertNotIn("scripts/removed.py", json.load(open(rec))["scripts"])   # a FULL update rebuilds the record from GRANDFATHERED
        os.makedirs(os.path.join(d, "skills", "x")); open(os.path.join(d, "skills", "x", "tool.py"), "w").write("def g(a):\n    return a - 1\n"); open(os.path.join(d, "tests", "test_tool.py"), "w").write("import os, sys, unittest\nsys.path.insert(0, os.path.join(os.environ['BRAIN_DIR'], 'skills', 'x'))\nimport tool\nclass T(unittest.TestCase):\n    def test_g(self): self.assertEqual(tool.g(3), 2)\n")
        open(os.path.join(d, "tests", "mutants", "GRANDFATHERED.txt"), "a").write("skills/x/tool.py\n")
        mark = json.load(open(rec)); mark["scripts"]["scripts/calc.py"]["score"] = 0.321; json.dump(mark, open(rec, "w"))
        self.assertEqual(self.run_cli(d, "--update", "skills/x/tool.py", "--max", "10", "--jobs", "1").returncode, 0); got = json.load(open(rec))["scripts"]
        self.assertEqual(got["skills/x/tool.py"]["score"], 1.0); self.assertEqual(got["scripts/calc.py"]["score"], 0.321)   # skills/ paths count as explicit scripts (a partial update)

    def test_check_without_a_record_exits_2(self):
        self.assertEqual(self.run_cli(self.project(), "--check").returncode, 2)


if __name__ == "__main__":
    unittest.main()
