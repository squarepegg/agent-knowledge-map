"""agentic_ab: the with/without-brain comparison, exercised with a fake 'agent' (no model, no network)."""
import contextlib, glob, io, json, os, shutil, subprocess, sys, tempfile, unittest
import yaml
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts")); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agentic_ab as ab, agentic_eval as ae
from helpers import fixture_brain, set_env

FAKE = '''
import os, subprocess, sys
prompt, primer_file, tools = sys.argv[1], sys.argv[2], sys.argv[3]
if tools and os.path.getsize(primer_file) > 0 and os.path.exists("scripts/brain.py"):      # "has the brain": primer + tools + brain directory as cwd
    q = prompt.split("answer from what you can look up; do not modify anything.) ")[-1]
    print(subprocess.run([sys.executable, "scripts/brain.py", "search", q], capture_output=True, text=True).stdout)
else:
    print("I do not know. BRAIN_DIR=" + os.environ.get("BRAIN_DIR", "none") + " TOOLS=[" + tools + "] CWD_HAS_BRAIN=" + str(os.path.exists("scripts/brain.py")) + " PRIMER_BYTES=" + str(os.path.getsize(primer_file)))
'''
EXAMPLES = sorted(os.path.basename(p) for p in glob.glob(f"{ROOT}/examples/*") if os.path.isdir(p))


class Pieces(unittest.TestCase):
    def test_condition_substitutes_and_quotes(self):
        self.assertEqual(ab.condition("x {primer_file} --tools {tools}", "/a b/p.md", "Bash,Read"), "x '/a b/p.md' --tools Bash,Read"); self.assertEqual(ab.condition("--tools {tools}", "p", ""), "--tools ''")
        self.assertIn("{prompt}", ab.condition("claude -p {prompt}", "p", "t"))                                  # the prompt placeholder is left for agentic_eval.ask
        for must in ("CLAUDE_CODE_DISABLE_CLAUDE_MDS=1", "--strict-mcp-config", '{"mcpServers":{}}', "--model haiku"): self.assertIn(must, ab.DEFAULT_CMD)
        self.assertIn("--tools {tools}", ab.DEFAULT_CMD); self.assertIn("{primer_file}", ab.DEFAULT_CMD); self.assertIn("{prompt}", ab.DEFAULT_CMD)

    def test_summarize(self):
        w = [{"correct": True}, {"correct": True}, {"correct": False}]; wo = [{"correct": False}, {"correct": True}, {"correct": False}]
        self.assertEqual(ab.summarize(w, wo), {"n": 3, "with_brain": 2, "without_brain": 1, "gain": 1, "empty_with": 0, "empty_without": 0}); self.assertEqual(ab.summarize([], []), {"n": 0, "with_brain": 0, "without_brain": 0, "gain": 0, "empty_with": 0, "empty_without": 0})
        self.assertEqual(ab.summarize(wo, w)["gain"], -1)
        e = ab.summarize([{"correct": False, "empty": True}, {"correct": True, "empty": False}], [{"correct": False, "empty": True}, {"correct": False, "empty": True}]); self.assertEqual((e["empty_with"], e["empty_without"]), (1, 2))

    def test_run_condition_grades_each_item(self):
        os.environ.pop("AGENTIC_CMD", None)
        items = [{"id": "a", "q": "x", "expect": [["yes"]], "max_words": 5}, {"id": "b", "q": "y", "expect": [["zzz"]], "max_words": 1}]
        r = ab.run_condition(items, "echo yes yes", os.getcwd()); self.assertEqual([(x["id"], x["correct"], x["concise"]) for x in r], [("a", True, True), ("b", False, False)]); self.assertEqual(r[0]["answer"], "yes yes")
        self.assertEqual(len(ab.run_condition([{"id": "c", "q": "q", "expect": [["x"]]}], "python3 -c \"print('x' * 400)\"", os.getcwd())[0]["answer"]), 300)      # answers are truncated in the record

    def test_clean_env_drops_brain_variables_and_sets_the_brain_for_the_brain_run(self):
        set_env(self, BRAIN_DIR="/x", BRAIN_REPOS_ROOT="/y", KEEP_ME="1")
        e = ab.clean_env(); self.assertNotIn("BRAIN_DIR", e); self.assertNotIn("BRAIN_REPOS_ROOT", e); self.assertEqual(e["KEEP_ME"], "1")
        e = ab.clean_env("/brain"); self.assertEqual(e["BRAIN_DIR"], "/brain"); self.assertNotIn("BRAIN_REPOS_ROOT", e)

    def test_an_empty_answer_is_retried_once_in_the_same_directory_and_flagged(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); flag = os.path.join(d, "n"); d = os.path.realpath(d)
        flaky = (f"{sys.executable} -c \"import os; p=r'{flag}'; n=int(open(p).read()) if os.path.exists(p) else 0; open(p,'w').write(str(n+1)); "
                 f"print('yes' if n > 0 and os.path.realpath(os.getcwd()) == r'{d}' else '')\"")
        r = ab.run_condition([{"id": "a", "q": "q", "expect": [["yes"]]}], flaky, d); self.assertTrue(r[0]["correct"]); self.assertFalse(r[0]["empty"]); self.assertEqual(open(flag).read(), "2")   # first call empty, retry (same cwd) answered
        r = ab.run_condition([{"id": "a", "q": "q", "expect": [["yes"]]}], "true", d); self.assertFalse(r[0]["correct"]); self.assertTrue(r[0]["empty"])                      # still empty after the retry
        r = ab.run_condition([{"id": "a", "q": "q", "expect": [["yes"]]}], "echo yes", d); self.assertFalse(r[0]["empty"])

    def test_the_retry_gets_the_same_environment(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); flag = os.path.join(d, "n")
        cmd = (f"{sys.executable} -c \"import os; p=r'{flag}'; n=int(open(p).read()) if os.path.exists(p) else 0; open(p,'w').write(str(n+1)); "
               f"print('yes' if n > 0 and os.environ.get('ZZ_RETRY') == '1' else '')\"")
        r = ab.run_condition([{"id": "a", "q": "q", "expect": [["yes"]]}], cmd, d, env={**os.environ, "ZZ_RETRY": "1"}); self.assertTrue(r[0]["correct"])

    def test_a_timed_out_answer_is_empty_not_a_crash(self):
        self.assertEqual(ae.ask("q", cmd="sleep 5", timeout=0.3), ""); self.assertEqual(ae.ask("q", cmd="sleep 5 # {prompt}", timeout=0.3), "")

    def test_timeout_comes_from_the_environment_default_300(self):
        seen = []; real = ae.ask
        ae.ask = lambda q, timeout=0, **kw: (seen.append(timeout), "x")[1]
        try:
            os.environ.pop("AGENTIC_TIMEOUT", None); ab.run_condition([{"id": "a", "q": "q", "expect": [["x"]]}], "c", ".")
            set_env(self, AGENTIC_TIMEOUT="7"); ab.run_condition([{"id": "a", "q": "q", "expect": [["x"]]}], "c", ".")
        finally: ae.ask = real
        self.assertEqual(seen, [300, 7])

    def test_ask_passes_the_environment(self):
        self.assertEqual(ae.ask("q", cmd="echo $ZZ_TEST", env={**os.environ, "ZZ_TEST": "hello"}), "hello")

    def test_ask_uses_the_given_cwd_and_command(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); self.assertEqual(os.path.realpath(ae.ask("q", cmd="pwd", cwd=d)), os.path.realpath(d))
        os.environ["AGENTIC_CMD"] = "echo from-env"; self.addCleanup(os.environ.pop, "AGENTIC_CMD"); self.assertEqual(ae.ask("q"), "from-env"); self.assertEqual(ae.ask("q", cmd="echo explicit"), "explicit")

    def test_build_brain_applies_the_example_and_builds_the_primer(self):
        b = ab.build_brain("web-app"); self.addCleanup(shutil.rmtree, os.path.dirname(b))
        self.assertTrue(os.path.exists(f"{b}/facts/deploy-canary.md")); self.assertIn("Acme Shop", open(f"{b}/PRIMER.md").read()); self.assertTrue(os.path.exists(f"{b}/scripts/brain.py"))
        self.assertFalse(os.path.exists(f"{b}/.git")); self.assertFalse(os.path.exists(f"{b}/facts/example-fact.md"))
        with self.assertRaises(SystemExit): ab.build_brain("nope")


class Questions(unittest.TestCase):
    def test_every_example_has_agentic_questions_its_own_facts_can_answer(self):
        for ex in EXAMPLES:
            d = fixture_brain(); self.addCleanup(shutil.rmtree, d); shutil.copytree(f"{ROOT}/tests/fixtures", f"{d}/tests/fixtures", dirs_exist_ok=True)
            import init_brain; init_brain.apply_example(d, ex)
            items = yaml.safe_load(open(f"{ROOT}/examples/{ex}/evals/agentic.yaml")); self.assertGreaterEqual(len(items), 5, ex); self.assertEqual(len({i["id"] for i in items}), len(items), ex)
            text = "\n".join(open(p, errors="ignore").read() for p in glob.glob(f"{d}/**/*.md", recursive=True) + glob.glob(f"{d}/*.yaml", recursive=True) if "/skills/" not in p and "/docs/" not in p).lower()
            for it in items:
                for group in it["expect"]: self.assertTrue(any(str(alt).lower() in text for alt in group), f"{ex}/{it['id']}: nothing in the example answers {group}")   # answerable from the brain

    def test_questions_are_not_trivia_the_question_itself_does_not_give_away(self):
        for ex in EXAMPLES:
            for it in yaml.safe_load(open(f"{ROOT}/examples/{ex}/evals/agentic.yaml")):
                self.assertFalse(all(str(alt).lower() in it["q"].lower() for alt in it["expect"][0]), f"{ex}/{it['id']}: the question contains its own answer")


class EndToEnd(unittest.TestCase):
    def run_main(self, *extra):
        decoy = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, decoy); set_env(self, BRAIN_DIR=decoy, BRAIN_REPOS_ROOT=decoy)    # an inherited brain must not leak into either run
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); fake = os.path.join(d, "fake.py"); open(fake, "w").write(FAKE); out = os.path.join(d, "o.json")
        cmd = f"{sys.executable} {fake} {{prompt}} {{primer_file}} {{tools}}"
        with contextlib.redirect_stdout(io.StringIO()) as o: rc = ab.main(["x", "web-app", "--cmd", cmd, "--json", out, *extra])
        return rc, o.getvalue(), json.load(open(out))

    def test_with_brain_beats_without_and_baseline_gets_nothing(self):
        rc, text, data = self.run_main("--only", "canary", "migration-label")
        self.assertEqual(rc, 0); self.assertEqual(data["summary"], {"n": 2, "with_brain": 2, "without_brain": 0, "gain": 2, "empty_with": 0, "empty_without": 0}); self.assertEqual([r["id"] for r in data["with"]], ["canary", "migration-label"])
        self.assertIn("web-app: with brain 2/2, without 0/2, gain +2", text); self.assertIn("I do not know. BRAIN_DIR=none TOOLS=[] CWD_HAS_BRAIN=False PRIMER_BYTES=0", data["without"][0]["answer"]); self.assertIn("15 minutes", data["with"][0]["answer"])

    def test_style_file_replaces_the_brains_style_and_reaches_the_primer(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); st = os.path.join(d, "s.md"); open(st, "w").write("## Style\n- MARKER-RULE: always cite the fact file\n")
        b = ab.build_brain("web-app", style=st); self.addCleanup(shutil.rmtree, os.path.dirname(b))
        self.assertIn("MARKER-RULE", open(f"{b}/style.md").read()); self.assertIn("MARKER-RULE", open(f"{b}/PRIMER.md").read())
        b2 = ab.build_brain("web-app"); self.addCleanup(shutil.rmtree, os.path.dirname(b2)); self.assertNotIn("MARKER-RULE", open(f"{b2}/PRIMER.md").read())

    def test_no_baseline_skips_the_without_run_and_the_without_column(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); log = os.path.join(d, "calls"); fake = os.path.join(d, "f.py")
        open(fake, "w").write(FAKE + f"\nopen(r'{log}', 'a').write(('brain' if tools else 'baseline') + '\\n')\n")
        cmd = f"{sys.executable} {fake} {{prompt}} {{primer_file}} {{tools}}"; st = os.path.join(d, "s.md"); open(st, "w").write("## Style\n- x\n")
        with contextlib.redirect_stdout(io.StringIO()) as o: ab.main(["x", "web-app", "--cmd", cmd, "--no-baseline", "--style", st, "--only", "canary"])
        self.assertEqual(open(log).read().split(), ["brain"]); self.assertIn("web-app: with brain 1/1\n", o.getvalue()); self.assertNotIn("without", o.getvalue()); self.assertNotIn("WARNING", o.getvalue())
        os.remove(log)
        with contextlib.redirect_stdout(io.StringIO()) as o: ab.main(["x", "web-app", "--cmd", cmd, "--only", "canary"])
        self.assertEqual(sorted(open(log).read().split()), ["baseline", "brain"]); self.assertIn("without 0/1", o.getvalue())

    def test_build_brain_fails_loudly_when_the_primer_cannot_be_built(self):
        root = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, root); shutil.copytree(ROOT, f"{root}/r", ignore=shutil.ignore_patterns(".git", "__pycache__"))
        open(f"{root}/r/scripts/build_primer.py", "w").write("import sys; sys.stderr.write('boom'); sys.exit(3)\n")
        with self.assertRaises(SystemExit) as e: ab.build_brain("web-app", root=f"{root}/r")
        self.assertIn("primer failed", str(e.exception)); self.assertIn("boom", str(e.exception))

    def test_build_brain_leaves_vcs_and_generated_files_out(self):
        root = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, root); shutil.copytree(ROOT, f"{root}/r", ignore=shutil.ignore_patterns(".git", "__pycache__")); r = f"{root}/r"
        os.makedirs(f"{r}/.git"); open(f"{r}/.git/HEAD", "w").write("x"); os.makedirs(f"{r}/status", exist_ok=True); open(f"{r}/status/s.json", "w").write("{}"); os.makedirs(f"{r}/metrics", exist_ok=True); open(f"{r}/metrics/agentic.json", "w").write("{}"); open(f"{r}/PRIMER.md", "w").write("STALE")
        b = ab.build_brain("web-app", root=r); self.addCleanup(shutil.rmtree, os.path.dirname(b))
        for gone in (".git", "status", "metrics"): self.assertFalse(os.path.exists(f"{b}/{gone}"), gone)
        self.assertNotIn("STALE", open(f"{b}/PRIMER.md").read())

    def test_command_template_can_come_from_the_environment(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); fake = os.path.join(d, "fake.py"); open(fake, "w").write(FAKE)
        set_env(self, AGENTIC_AB_CMD=f"{sys.executable} {fake} {{prompt}} {{primer_file}} {{tools}}")
        with contextlib.redirect_stdout(io.StringIO()) as o: ab.main(["x", "web-app", "--only", "canary"])
        self.assertIn("web-app: with brain 1/1, without 0/1, gain +1", o.getvalue())
        other = f"{sys.executable} -c \"print('from-flag')\" {{prompt}}"
        with contextlib.redirect_stdout(io.StringIO()) as o: ab.main(["x", "web-app", "--cmd", other, "--only", "canary"])
        self.assertIn("with brain 0/1, without 0/1", o.getvalue())                       # --cmd wins over the environment

    def test_warning_when_answers_are_empty(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d)
        with contextlib.redirect_stdout(io.StringIO()) as o: ab.main(["x", "web-app", "--cmd", "true", "--only", "canary"])
        self.assertIn("WARNING: 1 empty answer(s) with the brain, 1 without", o.getvalue()); self.assertIn("NOT reliable", o.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as o: ab.main(["x", "web-app", "--cmd", "echo hi", "--only", "canary"])
        self.assertNotIn("WARNING", o.getvalue())
        only_brain_empty = f"{sys.executable} -c \"import sys; print('' if sys.argv[1] else 'hi')\" {{tools}}"       # empty only when tools are given, i.e. in the brain run
        with contextlib.redirect_stdout(io.StringIO()) as o: ab.main(["x", "web-app", "--cmd", only_brain_empty, "--only", "canary"])
        self.assertIn("WARNING: 1 empty answer(s) with the brain, 0 without", o.getvalue())

    def test_warning_names_the_side_that_was_empty(self):
        only_baseline_empty = f"{sys.executable} -c \"import sys; print('hi' if sys.argv[1] else '')\" {{tools}}"                 # empty only without tools, i.e. in the baseline run
        with contextlib.redirect_stdout(io.StringIO()) as o: ab.main(["x", "web-app", "--cmd", only_baseline_empty, "--only", "canary"])
        self.assertIn("WARNING: 0 empty answer(s) with the brain, 1 without", o.getvalue())

    def test_style_option_reaches_the_agent_through_main(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); st = os.path.join(d, "s.md"); open(st, "w").write("## Style\n- MARKER-RULE-XYZ keep it short\n"); out = os.path.join(d, "o.json")
        cmd = f"{sys.executable} -c \"import sys; print([l.strip() for l in open(sys.argv[1]) if 'MARKER-RULE-XYZ' in l])\" {{primer_file}}"
        with contextlib.redirect_stdout(io.StringIO()): ab.main(["x", "web-app", "--cmd", cmd, "--style", st, "--json", out, "--only", "canary"])
        data = json.load(open(out)); self.assertIn("MARKER-RULE-XYZ", data["with"][0]["answer"]); self.assertNotIn("MARKER-RULE-XYZ", data["without"][0]["answer"])

    def test_usage_and_cleanup(self):
        with contextlib.redirect_stdout(io.StringIO()) as o: self.assertEqual(ab.main(["x"]), 2)
        self.assertIn("agentic_ab.py EXAMPLE", o.getvalue())
        before = set(glob.glob(os.path.join(tempfile.gettempdir(), "agentic-ab-*"))); self.run_main("--only", "canary"); self.assertEqual(set(glob.glob(os.path.join(tempfile.gettempdir(), "agentic-ab-*"))) - before, set())

if __name__ == "__main__": unittest.main()
