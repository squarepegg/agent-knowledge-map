"""rank (BM25), compact, init_brain, capture_hook, codex adapter, brain CLI dispatch."""
import datetime, io, json, os, shutil, site, subprocess, sys, tempfile, unittest, contextlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import fixture_brain
import brain, compact, capture_hook, init_brain, digest_sessions as dg
TODAY = str(datetime.date.today())

def mk(files):
    d = tempfile.mkdtemp()
    for rel, text in files.items():
        os.makedirs(os.path.dirname(f"{d}/{rel}"), exist_ok=True); open(f"{d}/{rel}", "w").write(text)
    return d


class Rank(unittest.TestCase):
    D = [("a.md", 1, "deploy things often"), ("b.md", 1, "gitops rules"), ("c.md", 1, "deploy"), ("d.md", 1, "deploy gitops deploy")]

    def test_rarer_and_more_terms_win_then_path_order(self):
        r = brain.rank(self.D, ["deploy", "gitops"], limit=10)
        self.assertEqual([x[0] for x in r], ["d.md", "b.md", "a.md", "c.md"])        # d has both; b has the rarer term; a, c tie -> path order
        self.assertEqual([x[0] for x in brain.rank([("z.md", 1, "x y"), ("a.md", 1, "x y")], ["x"])], ["a.md", "z.md"])   # ties: path order, not input order

    def test_prefix_matching_case_and_empty(self):
        self.assertEqual(len(brain.rank([("a", 1, "Deploys happen")], ["DEPLOY"])), 1)
        self.assertEqual(brain.rank([("a", 1, "redeploy")], ["deploy"]), [])                                 # prefix of a token, not a substring
        self.assertEqual(brain.rank(self.D, []), []); self.assertEqual(brain.rank(self.D, [""]), []); self.assertEqual(brain.rank([], ["x"]), [])

    def test_title_heading_name_and_description_lines_form_the_head(self):
        docs = [("a", 1, "alpha beta gamma delta"), ("b", 1, "title: alpha beta gamma delta"), ("c", 1, "# alpha beta gamma delta")]
        r = brain.rank(docs, ["alpha"]); self.assertEqual([x[0] for x in r], ["b", "c", "a"]); self.assertEqual(len(brain.rank(docs, ["alpha"], limit=2)), 2)
        for key in ("name:", "description:", "tags:", "aliases:"): self.assertEqual(brain.rank([("a", 1, "alpha x"), ("b", 1, key + " alpha x")], ["alpha"])[0][0], "b", key)
        self.assertEqual(brain.rank([("a", 1, "alpha x"), ("b", 1, "other: alpha x")], ["alpha"])[0][0], "a")             # only the head markers count
        self.assertEqual(brain.rank([("a", 1, "alpha x"), ("b", 1, "see title: alpha x")], ["alpha"])[0][0], "a")          # ... at the start of a line
        self.assertEqual(brain.rank([("a.md", 1, "alpha"), ("zeta/b.md", 1, "alpha")], ["alpha", "zeta"])[0][0], "a.md")     # directory names are not part of the file name
        late = [("b", i, "filler %d" % i) for i in range(1, 13)] + [("b", 13, "title: alpha x")]                          # a title-like line after HEAD_LINES lines is a body line
        self.assertEqual(brain.rank([("a", 1, "alpha x")] + late, ["alpha"])[0][0], "a")
        early = [("b", i, "filler %d" % i) for i in range(1, 12)] + [("b", 12, "title: alpha x")]; self.assertEqual(brain.rank([("a", 1, "alpha x")] + early, ["alpha"])[0][0], "b")

    def test_head_terms_count_even_when_spread_over_different_lines(self):
        docs = [("t", 1, "title: kafka"), ("t", 2, "description: retries"), ("u", 1, "kafka retries")]
        self.assertEqual(brain.rank(docs, ["kafka", "retries"])[0][0], "t")                                           # file t: head covers both words; u only has them on one line

    def test_file_name_words_count_even_without_a_matching_line(self):
        r = brain.rank([("a.md", 1, "x now"), ("b-zzz.md", 1, "x now")], ["now", "zzz"]); self.assertEqual(r[0][0], "b-zzz.md")
        r = brain.rank([("a-misc.md", 1, "deploy now"), ("z-deploy-guide.md", 1, "deploy now")], ["deploy"]); self.assertEqual(r[0][0], "z-deploy-guide.md")   # name beats path order

    def test_idf_is_computed_over_files_not_lines(self):
        docs = [("a", i, "common") for i in range(1, 30)] + [("b", 1, "common"), ("c", 1, "rare"), ("d", 1, "other")]
        self.assertEqual([x[0] for x in brain.rank(docs, ["common", "rare"])][:2], ["c", "a"])                       # 29 lines of 'common' in one file do not make it common; c's rare word wins
        docs = [("f%d" % i, 1, "x") for i in range(40)] + [("a", 1, "x y"), ("b", 1, "rare")]
        self.assertEqual([r[0] for r in brain.rank(docs, ["x", "y", "rare"])][:2], ["a", "b"])                        # two terms beat one rare term

    # Golden cases found by search: they flip if idf is computed over lines instead of files, or df counts lines instead of files.
    GOLDEN = {'df': ([('f0.md', 1, 'zz'), ('f1.md', 1, 'b c d'), ('f1.md', 2, 'c d'), ('f1.md', 3, 'a'), ('f1.md', 4, 'b'), ('f1.md', 5, 'zz'), ('f1.md', 6, 'a'), ('f2.md', 1, 'a b d'), ('f2.md', 2, 'a b d'), ('f2.md', 3, 'a c'), ('f2.md', 4, 'zz'), ('f2.md', 5, 'b'), ('f2.md', 6, 'b'), ('f3.md', 1, 'c d'), ('f4.md', 1, 'zz'), ('f4.md', 2, 'a'), ('f5.md', 1, 'b'), ('f6.md', 1, 'zz'), ('f6.md', 2, 'b'), ('f7.md', 1, 'a'), ('f7.md', 2, 'c d'), ('f8.md', 1, 'a'), ('f8.md', 2, 'zz'), ('f9.md', 1, 'c d'), ('f9.md', 2, 'a d'), ('f9.md', 3, 'd'), ('f9.md', 4, 'zz'), ('f9.md', 5, 'zz')], ['f1.md', 'f1.md', 'f1.md', 'f2.md', 'f2.md', 'f2.md', 'f5.md', 'f6.md', 'f3.md', 'f7.md', 'f7.md', 'f9.md', 'f9.md', 'f4.md', 'f8.md']), 'lines': ([('f0.md', 1, 'a b'), ('f0.md', 2, 'zz'), ('f0.md', 3, 'b'), ('f0.md', 4, 'zz'), ('f0.md', 5, 'zz'), ('f1.md', 1, 'a b'), ('f1.md', 2, 'c d'), ('f1.md', 3, 'zz'), ('f2.md', 1, 'zz'), ('f2.md', 2, 'b'), ('f3.md', 1, 'a'), ('f3.md', 2, 'b d'), ('f4.md', 1, 'd'), ('f4.md', 2, 'a b d'), ('f5.md', 1, 'zz'), ('f6.md', 1, 'zz'), ('f6.md', 2, 'a b d')], ['f1.md', 'f1.md', 'f0.md', 'f0.md', 'f4.md', 'f6.md', 'f3.md', 'f3.md', 'f2.md'])}

    def test_idf_golden_cases(self):
        for name, (docs, order) in self.GOLDEN.items(): self.assertEqual([r[0] for r in brain.rank(docs, ["a", "b", "c"], limit=50)], order, name)

    def test_a_file_contributes_only_matching_lines_best_first_at_most_three(self):
        docs = [("big.md", i, "deploy step %d" % i) for i in range(1, 7)] + [("big.md", 9, "unrelated line")] + [("other.md", 1, "deploy once")]
        r = brain.rank(docs, ["deploy"]); self.assertEqual(sum(1 for x in r if x[0] == "big.md"), 3); self.assertEqual(len(r), 4); self.assertNotIn("unrelated line", [x[2] for x in r])
        self.assertEqual(len(brain.rank(docs, ["deploy"], limit=2)), 2)
        docs = [("f", 1, "one"), ("f", 2, "one two"), ("f", 3, "one two three")]; self.assertEqual([x[1] for x in brain.rank(docs, ["one", "two", "three"])], [3, 2, 1])   # best line first
        docs = [("f", 4, "one two"), ("f", 2, "one two")]; self.assertEqual([x[1] for x in brain.rank(docs, ["one", "two"])], [2, 4])                               # equal scores: line order

    def test_terms_beyond_the_display_width_are_still_found_and_shown(self):
        d = mk({"facts/long.md": "filler " * 60 + "needle appears late " + "tail " * 20 + "\n", "facts/short.md": "needle short\n"}); self.addCleanup(shutil.rmtree, d)
        r = brain.search(["needle"], brain=d); self.assertEqual(len(r), 2); long = [x for x in r if "long.md" in x][0]
        self.assertIn("needle appears late", long); self.assertTrue(long.split(": ", 1)[1].startswith("…")); self.assertLessEqual(len(long.split(": ", 1)[1]), brain.SNIP + 2)
        self.assertEqual(brain.snippet("short line", ["short"]), "short line"); self.assertEqual(brain.snippet("x" * 250, ["zzz"]), "x" * 200 + "…")      # no hit: head of the line
        self.assertEqual(brain.snippet("a" * 100 + "needle" + "b" * 200, ["NEEDLE"])[:1], "…"); self.assertEqual(brain.snippet("needle" + "b" * 300, ["needle"]), "needle" + "b" * 194 + "…")
        w = brain.snippet("a" * 100 + "needle" + "b" * 200, ["needle"]); self.assertTrue(w.startswith("…" + "a" * 60 + "needle"))                       # window starts 60 chars before the hit
        w = brain.snippet("c" * 100 + "beta" + "c" * 46 + "alpha" + "d" * 200, ["alpha", "beta"]); self.assertTrue(w.startswith("…" + "c" * 60 + "beta"))   # earliest of several terms
        self.assertEqual(brain.snippet("A" * 100 + "NEEDLE" + "B" * 200, ["needle"])[:1], "…")                                                           # case-insensitive
        self.assertFalse(brain.snippet("x" * 150 + "needle", ["needle"]).endswith("…"))                                                                           # window reaches the end: no trailing ellipsis

    def test_query_words_drop_stop_words_and_short_tokens(self):
        self.assertEqual(brain.query_words("Why is my backfill slow?"), ["backfill", "slow"])
        self.assertEqual(brain.query_words("the Deploy and the deploy of order_date"), ["deploy", "order_date"])        # de-duplicated, order kept, underscores kept
        self.assertEqual(brain.query_words("how to do it"), ["how", "to", "do", "it"])                                     # nothing left: fall back to every token
        self.assertEqual(brain.query_words("ab abc"), ["abc"]); self.assertEqual(brain.query_words("an ab"), ["an", "ab"]); self.assertEqual(brain.query_words(""), [])
        for w in ("the", "what", "with", "when", "does", "from", "now", "still", "been", "being", "more", "some", "such", "very", "much"): self.assertEqual(brain.query_words(f"{w} kafka"), ["kafka"], w)

    def test_cli_search_accepts_a_natural_language_question(self):
        d = mk({"facts/d.md": "How production deploys work: canary first\n"}); self.addCleanup(shutil.rmtree, d)
        out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "brain.py"), "search", "how do I deploy to production?"], env={**os.environ, "BRAIN_DIR": d}, capture_output=True, text=True).stdout
        self.assertIn("facts/d.md:1", out)

    def test_stemming_matches_plurals_and_suffixes_in_both_directions(self):
        for w, st in (("emails", "email"), ("deploying", "deploy"), ("copied", "copi"), ("policies", "policy"), ("class", "class"), ("bus", "bus"), ("is", "is"), ("sing", "sing"), ("tested", "test"), ("tired", "tired"), ("doing", "doing"), ("string", "string"), ("testing", "test"), ("ads", "ads"), ("status", "statu")):
            self.assertEqual(brain.stem(w), st, w)
        self.assertEqual(brain.tokens("Emails sent"), ["email", "sent"])
        self.assertEqual(len(brain.rank([("a", 1, "customer email address")], ["emails"])), 1); self.assertEqual(len(brain.rank([("a", 1, "send emails daily")], ["email"])), 1)
        self.assertEqual(len(brain.rank([("a", 1, "we are deploying today")], ["deploy"])), 1)

    def test_deterministic(self):
        d = mk({"facts/a.md": "deploy one\n", "facts/b.md": "deploy two\n", "glossary.yaml": "- term: deploy\n"})
        self.addCleanup(shutil.rmtree, d); a = brain.search(["deploy"], brain=d)
        for _ in range(3): self.assertEqual(brain.search(["deploy"], brain=d), a)

    def test_corpus_skips_blank_processed_and_truncates(self):
        d = mk({"facts/a.md": "x\n\n   \n" + "y" * 300 + "\n", "inbox/processed/o.md": "old\n", "inbox/n.md": "new\n", "other/z.md": "no\n"}); self.addCleanup(shutil.rmtree, d)
        c = brain.corpus(d); self.assertEqual([x[:2] for x in c if x[0] == "facts/a.md"], [("facts/a.md", 1), ("facts/a.md", 4)])
        self.assertEqual(len(c[1][2]), 300); self.assertFalse(any("processed" in x[0] or x[0].startswith("other") for x in c)); self.assertTrue(any(x[0] == "inbox/n.md" for x in c))


class Compact(unittest.TestCase):
    def test_parse(self):
        t = "junk\n\n## [gotcha] one thing\nbody a\nmore\n\n## [decision] pick x\n\nlast body line\n"
        self.assertEqual(compact.parse(t), [{"kind": "gotcha", "title": "one thing", "body": "body a\nmore"}, {"kind": "decision", "title": "pick x", "body": "last body line"}])
        self.assertEqual(compact.parse("nothing"), [])

    def test_route_every_kind(self):
        it = lambda k: {"kind": k, "title": "My Thing!", "body": "b"}  # noqa: E731
        self.assertEqual(compact.route(it("gotcha"), ".", TODAY)[2], "facts/my-thing.md"); self.assertEqual(compact.route(it("fact"), ".", TODAY)[2], "facts/my-thing.md")
        t = compact.route(it("decision"), ".", TODAY); self.assertEqual(t[2], f"decisions/{TODAY}-my-thing.md"); self.assertIn("## Decision", t[3])
        c = compact.route(it("capability"), ".", TODAY); self.assertEqual((c[0], c[2]), ("capabilities.yaml", None)); self.assertIn("id: my-thing", c[1])
        self.assertEqual(compact.route(it("workstream"), ".", TODAY)[0], "workstreams/*/STATE.md")
        self.assertEqual(compact.route(it("correction"), ".", TODAY)[0], "facts/user-instincts.md")
        self.assertIn("classify by hand", compact.route(it("zzz"), ".", TODAY)[1])
        f = compact.route(it("gotcha"), ".", TODAY)[3]; self.assertIn("verified: false", f); self.assertIn(f"recorded_at: '{TODAY}'", f); self.assertIn("confidence: low", f); self.assertTrue(f.endswith("b\n"))
        self.assertTrue(compact.route({"kind": "fact", "title": "t", "body": ""}, ".", TODAY)[3].endswith("t\n"))     # empty body falls back to the title

    def test_plan_write_dedupe_and_archive(self):
        d = mk({"facts/known.md": "---\ntitle: Gitops deploys everything\n---\nx\n",
                "inbox/2025-01-01-1.md": "\n## [gotcha] Gitops deploys everything\nalready known\n\n## [gotcha] Brand new thing here\nnew body\n\n## [capability] Query tool\nrun q\n"})
        self.addCleanup(shutil.rmtree, d)
        out, created = compact.plan(d, TODAY)
        self.assertIn("3 item(s) from 1 inbox file(s)", out); self.assertIn("probable duplicate of facts/known.md", out); self.assertEqual(created, [])      # plan alone writes nothing
        self.assertFalse(os.path.exists(f"{d}/facts/brand-new-thing-here.md"))
        out, created = compact.plan(d, TODAY, write=True); self.assertEqual(created, ["facts/brand-new-thing-here.md"])                                       # duplicates and non-file kinds create nothing
        self.assertIn("created: facts/brand-new-thing-here.md", out); self.assertIn("verified: false", open(f"{d}/facts/brand-new-thing-here.md").read())
        open(f"{d}/facts/brand-new-thing-here.md", "w").write("HUMAN EDIT"); compact.plan(d, TODAY, write=True); self.assertEqual(open(f"{d}/facts/brand-new-thing-here.md").read(), "HUMAN EDIT")   # never overwrites
        self.assertEqual(compact.archive(d), ["2025-01-01-1.md"]); self.assertTrue(os.path.exists(f"{d}/inbox/processed/2025-01-01-1.md")); self.assertEqual(compact.archive(d), [])

    def test_duplicate_requires_all_title_tokens_and_ignores_inbox(self):
        d = mk({"facts/a.md": "kafka lag alert runbook\n", "inbox/x.md": "kafka lag alert wibble\n"}); self.addCleanup(shutil.rmtree, d)
        self.assertEqual(compact.duplicate_of({"title": "Kafka lag alert"}, d), "facts/a.md:1")
        self.assertIsNone(compact.duplicate_of({"title": "Kafka lag wibble"}, d))                          # inbox lines never count; 'wibble' only there
        open(f"{d}/facts/b.md", "w").write("a b c\n"); self.assertIsNone(compact.duplicate_of({"title": "a b"}, d))   # tokens <= 2 chars are ignored -> nothing to match
        self.assertIsNone(compact.duplicate_of({"title": "!!"}, d))

    def test_cli(self):
        d = mk({"inbox/n.md": "\n## [decision] Use sqlite\nwhy\n"}); self.addCleanup(shutil.rmtree, d); env = {**os.environ, "BRAIN_DIR": d}
        run = lambda *a: subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "brain.py"), "compact", *a], env=env, capture_output=True, text=True).stdout  # noqa: E731
        self.assertIn("1 item(s)", run()); self.assertIn("created: decisions/", run("--write")); self.assertIn("archived: n.md", run("--archive")); self.assertIn("archived: nothing", run("--archive"))


class Hooks(unittest.TestCase):
    def tool_lines(self, n): return "\n".join(json.dumps({"message": {"content": [{"type": "tool_use", "name": "Bash"}]}}) for _ in range(n))

    def test_is_correction(self):
        for t in ("That's wrong, use X", "no, that's not right", "you're wrong", "Actually, the config is elsewhere", "I already told you", "don't use that", "this is incorrect", "not what I asked"):
            self.assertTrue(capture_hook.is_correction(t), t)
        for t in ("please add a test", "actually useful tool", "thanks, that is right", "", None): self.assertFalse(capture_hook.is_correction(t), t)

    def test_count_tools(self):
        self.assertEqual(capture_hook.count_tools(self.tool_lines(3) + "\nnot json\n" + json.dumps({"content": [{"type": "toolCall"}, {"type": "text"}]})), 4)
        self.assertEqual(capture_hook.count_tools(json.dumps({"message": {"content": "str"}})), 0)

    def test_should_block(self):
        t = self.tool_lines(8)
        self.assertTrue(capture_hook.should_block({}, t, False, 8)); self.assertFalse(capture_hook.should_block({}, self.tool_lines(7), False, 8))
        self.assertFalse(capture_hook.should_block({"stop_hook_active": True}, t, False, 8)); self.assertFalse(capture_hook.should_block({}, t, True, 8))
        self.assertFalse(capture_hook.should_block({}, t + "\nran brain.py note gotcha", False, 8))

    def test_stop_blocks_once_per_session(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); tp = f"{d}/t.jsonl"; open(tp, "w").write(self.tool_lines(9))
        pl = {"session_id": "s/../1", "transcript_path": tp}
        r = capture_hook.stop(pl, d, 8); self.assertEqual(r["decision"], "block"); self.assertIn("brain.py note", r["reason"])
        self.assertTrue(os.path.exists(f"{d}/.cache/captured-s1")); self.assertIsNone(capture_hook.stop(pl, d, 8))                                  # marker: only once; session id sanitised
        self.assertIsNone(capture_hook.stop({"session_id": "x", "transcript_path": "/no/such"}, d, 8)); self.assertIsNone(capture_hook.stop({}, d, 8))

    def test_default_threshold_is_eight(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); os.environ.pop("CAPTURE_THRESHOLD", None)
        tp = f"{d}/t.jsonl"; open(tp, "w").write(self.tool_lines(7)); self.assertIsNone(capture_hook.stop({"session_id": "a", "transcript_path": tp}, d))
        open(tp, "w").write(self.tool_lines(8)); self.assertEqual(capture_hook.stop({"session_id": "a", "transcript_path": tp}, d)["decision"], "block")
        os.environ["CAPTURE_THRESHOLD"] = "2"; self.addCleanup(os.environ.pop, "CAPTURE_THRESHOLD"); open(tp, "w").write(self.tool_lines(2))
        self.assertEqual(capture_hook.stop({"session_id": "b", "transcript_path": tp}, d)["decision"], "block")

    def test_prompt_captures_corrections_only_and_never_secrets(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d)
        self.assertIsNone(capture_hook.prompt({"prompt": "add a test please"}, d)); self.assertFalse(os.path.exists(f"{d}/inbox"))
        self.assertIsNone(capture_hook.prompt({"prompt": "that's wrong, password: abcdefghijklmnopqrstuvwxyz0123"}, d))
        p = capture_hook.prompt({"prompt": "That's wrong.\n\n" + "x" * 500}, d); txt = open(p).read()
        self.assertIn("[correction] That's wrong. xxx", txt); self.assertLessEqual(len(txt.splitlines()[1]), len("## [correction] ") + 300)

    def test_cli_modes(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); env = {**os.environ, "BRAIN_DIR": d}
        run = lambda mode, payload: subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "capture_hook.py"), mode], input=payload, env=env, capture_output=True, text=True)  # noqa: E731
        r = run("prompt", json.dumps({"prompt": "you're wrong"})); self.assertEqual((r.returncode, r.stdout), (0, "")); self.assertEqual(len(os.listdir(f"{d}/inbox")), 1)
        tp = f"{d}/t.jsonl"; open(tp, "w").write(self.tool_lines(8)); r = run("stop", json.dumps({"session_id": "a", "transcript_path": tp})); self.assertEqual(json.loads(r.stdout)["decision"], "block")
        self.assertEqual(run("stop", "garbage").stdout, ""); self.assertEqual(run("bogus", "{}").returncode, 2)


class Init(unittest.TestCase):
    def brain_copy(self):
        d = fixture_brain(); self.addCleanup(shutil.rmtree, d); return d

    def test_config_and_examples(self):
        d = self.brain_copy()
        self.assertEqual(init_brain.set_config(d, "Foo Inc", "ops"), ["config org = Foo Inc", "config role = ops"]); self.assertEqual(init_brain.set_config(d, "Foo Inc", "ops"), [])   # idempotent
        self.assertEqual(init_brain.set_config(d), []); c = open(f"{d}/brain.config.yaml").read(); self.assertIn('org: "Foo Inc"', c); self.assertIn("routes:", c)
        a = init_brain.remove_examples(d); self.assertEqual(len(a), 4); self.assertEqual(init_brain.remove_examples(d), [])
        self.assertFalse(os.path.exists(f"{d}/facts/example-fact.md")); self.assertFalse(os.path.exists(f"{d}/workstreams/example-workstream"))
        import yaml; self.assertEqual(yaml.safe_load(open(f"{d}/glossary.yaml")), []); self.assertEqual(yaml.safe_load(open(f"{d}/capabilities.yaml")), [])

    def test_wire_claude_is_idempotent_and_preserves_existing(self):
        d = self.brain_copy(); h = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, h)
        os.makedirs(f"{h}/.claude"); open(f"{h}/.claude/CLAUDE.md", "w").write("# mine"); json.dump({"model": "x", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "other"}]}]}}, open(f"{h}/.claude/settings.json", "w"))
        a = init_brain.wire_claude(d, h); self.assertEqual(len(a), 5)                                                                       # CLAUDE.md, 1 skill, 3 hooks
        self.assertEqual(open(f"{h}/.claude/CLAUDE.md").read(), f"# mine\n@{d}/PRIMER.md\n"); self.assertTrue(os.path.islink(f"{h}/.claude/skills/brain"))
        s = json.load(open(f"{h}/.claude/settings.json")); self.assertEqual(s["model"], "x"); self.assertEqual(len(s["hooks"]["Stop"]), 2); self.assertEqual(set(s["hooks"]), {"Stop", "SessionStart", "UserPromptSubmit"})
        self.assertIn("capture_hook.py stop", json.dumps(s)); self.assertEqual(init_brain.wire_claude(d, h), [])                              # second run: no change
        h2 = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, h2); self.assertEqual(len(init_brain.wire_claude(d, h2)), 5)                    # fresh home works too

    def test_cli_end_to_end(self):
        d = self.brain_copy(); h = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, h); env = {**os.environ, "BRAIN_DIR": d, "HOME": h, "PYTHONUSERBASE": site.getuserbase()}   # HOME isolated: init must never touch the real one
        r = subprocess.run([sys.executable, f"{d}/scripts/brain.py", "init", "--org", "Zed", "--no-examples", "--claude", "--home", h], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("config org = Zed", r.stdout); self.assertIn("PRIMER.md", r.stdout); self.assertIn("# Zed primer", open(f"{d}/PRIMER.md").read())
        self.assertEqual(r.returncode, 0); self.assertFalse(os.path.exists(f"{d}/facts/example-fact.md"))
        d2 = self.brain_copy(); h2 = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, h2)
        r2 = subprocess.run([sys.executable, f"{d2}/scripts/brain.py", "init"], env={**os.environ, "BRAIN_DIR": d2, "HOME": h2, "PYTHONUSERBASE": site.getuserbase()}, capture_output=True, text=True)
        self.assertEqual(r2.returncode, 0); self.assertIn("Next: import PRIMER.md", r2.stdout)
        self.assertTrue(os.path.exists(f"{d2}/facts/example-fact.md")); self.assertNotIn(".claude", os.listdir(h2))      # no flags: examples kept, home untouched
        os.remove(f"{d2}/scripts/build_primer.py"); fail = subprocess.run([sys.executable, f"{d2}/scripts/init_brain.py"], env={**os.environ, "BRAIN_DIR": d2, "HOME": h2, "PYTHONUSERBASE": site.getuserbase()}, capture_output=True, text=True)
        self.assertEqual(fail.returncode, 1); self.assertIn("primer failed", fail.stdout)


class Codex(unittest.TestCase):
    def test_digest_codex(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); p = f"{d}/rollout.jsonl"
        rows = [{"type": "session_meta", "payload": {"cwd": "/work"}},
                {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "<environment_context>x</environment_context>"}]}},
                {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "fix the build"}]}},
                {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "ok"}]}},
                {"type": "response_item", "payload": {"type": "function_call", "name": "shell", "arguments": json.dumps({"cmd": "make test"}), "call_id": "c1"}},
                {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "c1", "output": "permission denied"}},
                {"type": "response_item", "payload": {"type": "function_call", "name": "shell", "arguments": "not json", "call_id": "c2"}},
                {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "c2", "output": "all good"}},
                {"type": "event_msg", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "duplicate from an event"}]}},
                {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "input_text", "text": "assistant echo"}]}},
                {"type": "event_msg", "payload": {"type": "token_count"}}]
        open(p, "w").write("\n".join(json.dumps(r) for r in rows) + "\nbroken line\n")
        cwd, lines = dg.digest_codex(p); self.assertEqual(cwd, "/work")
        self.assertEqual(lines, ["USER: fix the build", "ERR [shell] make test => permission denied", "CMD not json"])

    def test_default_globs_include_codex_and_adapters_registered(self):
        self.assertIn("codex", [k for k, _ in dg.session_globs("")]); self.assertEqual(set(dg.ADAPTERS), {"pi", "claude", "codex"})

if __name__ == "__main__": unittest.main()
