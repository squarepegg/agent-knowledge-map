import os, random, subprocess, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import tour_lint as T

MD = "# Top\nintro\n## Alpha\nalpha body\n### Sub\nsub body\n## Beta\nbeta body\n```\n## Alpha\n```\n"
FILES = {("r", "m.md"): MD, ("r", "dup.md"): "## X\na\n## X\nb\n", ("r", "a.md"): "line1\nline2\nline3\nline4\n", ("r", "b.md"): "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu\n"}
def rd(repo, path):
    if repo == "gone": raise LookupError(repo)
    return FILES.get((repo, path))
def codes(text, status="reviewed", read=rd):
    wps, bad = T.parse(text); return [c for c, _, _ in T.check(wps, bad, status, read)]
def wp(id_="N1", links="", kind="Need", why="because we need it", anchor="r@a.md", hash_=None):
    h = f" `hash: {T.hash_text(FILES[('r','a.md')])}`" if hash_ is None and anchor == "r@a.md" else (f" `hash: {hash_}`" if hash_ else "")
    lk = f" -> {links}" if links else ""
    return f"- [{id_}{lk}] **{kind}: t** - {why} `anchor: {anchor}`{h}"
GOOD = "\n".join([wp("N1"), wp("D1", "N1, T1", "Decision"), wp("T1", "D1", "Test"), wp("Q1", "D1", "Question", "open. owner: nic")])

class Core(unittest.TestCase):
    def test_good_is_clean(self): self.assertEqual(codes(GOOD), [])
    def test_draft_flagged(self): self.assertIn("DRAFT", codes(GOOD, "draft"))
    def test_bad_line(self): self.assertIn("BADLINE", codes(GOOD + "\n- [X] malformed"))
    def test_unknown_kind(self): self.assertIn("KIND", codes(GOOD + "\n" + wp("X1", "N1", "Banana")))
    def test_dup_id(self): self.assertIn("DUPID", codes(GOOD + "\n" + wp("N1")))
    def test_dangling(self): self.assertIn("DANGLING", codes(GOOD + "\n" + wp("X1", "N9", "Risk")))
    def test_selflink(self): self.assertIn("SELFLINK", codes(GOOD + "\n" + wp("X1", "X1, N1", "Risk")))
    def test_nowhy(self): self.assertIn("NOWHY", codes(GOOD + "\n" + wp("X1", "N1", "Risk", why="")))
    def test_question_owner(self): self.assertIn("NOOWNER", codes(GOOD.replace("owner: nic", "later")))
    def test_decision_needs_need(self): self.assertIn("NONEED", codes("\n".join([wp("N1"), wp("T1", "N1", "Test"), wp("D1", "T1", "Decision")])))
    def test_decision_needs_proof(self): self.assertIn("NOPROOF", codes("\n".join([wp("N1"), wp("D1", "N1", "Decision")])))
    def test_orphan(self): self.assertIn("ORPHAN", codes(GOOD + "\n" + wp("X1", "", "Risk")))
    def test_orphan_cycle_without_need(self): self.assertIn("ORPHAN", codes(GOOD + "\n" + wp("X1", "X2", "Risk") + "\n" + wp("X2", "X1", "Risk")))
    def test_cycle_with_need_ok(self): self.assertEqual(codes(GOOD), [])  # D1 <-> T1 cycle reaches N1
    def test_missing_kinds(self): self.assertIn("MISSINGKIND", codes(wp("N1")))
    def test_broken_file(self): self.assertIn("BROKEN", codes(GOOD + "\n" + wp("X1", "N1", "Risk", anchor="r@zzz.md", hash_="0" * 12)))
    def test_range_past_eof(self): self.assertIn("BROKEN", codes(GOOD + "\n" + wp("X1", "N1", "Risk", anchor="r@a.md#L50-60", hash_="0" * 12)))
    def test_norepo(self): self.assertIn("NOREPO", codes(GOOD + "\n" + wp("X1", "N1", "Risk", anchor="gone@a.md", hash_="0" * 12)))
    def test_unpinned(self): self.assertIn("UNPINNED", codes(GOOD + "\n" + wp("X1", "N1", "Risk", anchor="r@b.md")))
    def test_stale(self): self.assertIn("STALE", codes(GOOD + "\n" + wp("X1", "N1", "Risk", anchor="r@b.md", hash_="0" * 12)))
    def test_not_stale_when_hash_matches(self):
        h = T.hash_text(FILES[("r", "b.md")]); self.assertNotIn("STALE", codes(GOOD + "\n" + wp("X1", "N1", "Risk", anchor="r@b.md", hash_=h)))
    def test_copied_why(self):
        t = "alpha beta gamma delta epsilon zeta eta theta"; h = T.hash_text(FILES[("r", "b.md")])
        self.assertIn("COPIED", codes(GOOD + "\n" + wp("X1", "N1", "Risk", why=t, anchor="r@b.md", hash_=h)))
    def test_short_why_not_copied(self):
        h = T.hash_text(FILES[("r", "b.md")]); self.assertNotIn("COPIED", codes(GOOD + "\n" + wp("X1", "N1", "Risk", why="alpha beta", anchor="r@b.md", hash_=h)))
    def test_range_hash_scoped(self):
        c = FILES[("r", "a.md")]; self.assertEqual(T.hash_text(c, 2, 3), T.hash_text("x\nline2\nline3\ny\n", 2, 3)); self.assertNotEqual(T.hash_text(c, 2, 3), T.hash_text(c, 2, 4))
    def test_range_ignores_edits_outside(self):
        self.assertEqual(T.hash_text("a\nB\nc\n", 2, 2), T.hash_text("zzz\nB\nqqq\n", 2, 2))

class More(unittest.TestCase):
    def test_decision_proof_by_question_ok(self):
        self.assertNotIn("NOPROOF", codes("\n".join([wp("N1"), wp("D1", "N1, Q1", "Decision"), wp("Q1", "D1", "Question", "open. owner: nic")])))
    def test_range_exact(self):
        c = "a\nb\nc\nd\n"
        self.assertEqual(T.anchored_text(c, 2, 3), "b\nc"); self.assertEqual(T.anchored_text(c, 1, 1), "a"); self.assertEqual(T.anchored_text(c, 3), "c")
    def test_crlf_hash_equal(self): self.assertEqual(T.hash_text("a\r\nb\r\n"), T.hash_text("a\nb\n"))
    def test_reader_requires_git_dir(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(f"{d}/plain")
            with self.assertRaises(LookupError): T.make_reader([d])("plain", "x")

class Anchors(unittest.TestCase):
    def h(self, heading, f="m.md"): return T.hash_text(FILES[("r", f)], heading=heading)
    def line(self, anchor, hash_=None, id_="X1"):
        return GOOD + "\n" + wp(id_, "N1", "Risk", anchor=anchor, hash_=hash_)
    def test_section_extent(self):
        self.assertEqual(T.sections(MD, "Alpha"), ["## Alpha\nalpha body\n### Sub\nsub body"])  # sub-heading included, fenced '## Alpha' ignored
        self.assertEqual(T.sections(MD, "Sub"), ["### Sub\nsub body"])
        self.assertEqual(T.sections(MD, "Beta"), ["## Beta\nbeta body\n```\n## Alpha\n```\n"])
        self.assertEqual(T.sections(MD, "Top")[0].count("\n"), MD.count("\n"))
    def test_heading_case_and_space_insensitive(self): self.assertEqual(T.sections(MD, "  aLPHA "), T.sections(MD, "Alpha"))
    def test_heading_hash_ignores_other_sections(self):
        self.assertEqual(T.hash_text(MD, heading="Alpha"), T.hash_text(MD.replace("beta body", "CHANGED"), heading="Alpha"))
        self.assertNotEqual(T.hash_text(MD, heading="Alpha"), T.hash_text(MD.replace("sub body", "CHANGED"), heading="Alpha"))
    def test_heading_survives_inserted_lines(self):
        self.assertEqual(T.hash_text(MD, heading="Beta"), T.hash_text("new\nlines\n" + MD, heading="Beta"))
    def test_heading_ok(self): self.assertEqual(codes(self.line("r@m.md#h:Alpha", self.h("Alpha"))), [])
    def test_heading_stale(self): self.assertIn("STALE", codes(self.line("r@m.md#h:Alpha", "0" * 12)))
    def test_heading_missing(self): self.assertIn("BROKEN", codes(self.line("r@m.md#h:Nope", "0" * 12)))
    def test_heading_ambiguous(self): self.assertIn("AMBIGUOUS", codes(self.line("r@dup.md#h:X", "0" * 12)))
    def test_heading_unpinned(self): self.assertIn("UNPINNED", codes(self.line("r@m.md#h:Alpha")))
    def test_exists_needs_no_hash(self): self.assertEqual(codes(self.line("r@a.md#exists")), [])
    def test_exists_still_checks_file(self):
        self.assertIn("BROKEN", codes(self.line("r@zzz.md#exists"))); self.assertIn("NOREPO", codes(self.line("gone@a.md#exists")))
    def test_exists_ignores_content_change(self): self.assertEqual(codes(self.line("r@a.md#exists", "0" * 12)), [])
    def test_pin_heading_and_exists(self):
        text = self.line("r@m.md#h:Alpha").replace("\n- [X1", "\n- [X1"); wps, _ = T.parse(text); out = T.pin(text, wps, rd)
        self.assertIn(f"`hash: {self.h('Alpha')}`", out)
        ex = self.line("r@a.md#exists"); w2, _ = T.parse(ex); self.assertEqual(T.pin(ex, w2, rd), ex)
    def test_heading_with_special_chars_roundtrip(self):
        w = T.Waypoint(1, "H1", "Risk", "t", "why here", "r", "m.md", heading="4.6 Vendor sync (Acme)", hash="0123456789ab")
        self.assertEqual(T.parse(T.render(w)), ([w], []))
    def test_exists_roundtrip(self):
        w = T.Waypoint(1, "H1", "Risk", "t", "why here", "r", "m.md", exists=True); self.assertEqual(T.parse(T.render(w)), ([w], []))
    def test_copied_why_from_heading(self):
        t = "alpha body sub body alpha body sub body alpha body sub body"; files = dict(FILES); files[("r", "m2.md")] = "## A\n" + t + "\n"
        h = T.hash_text(files[("r", "m2.md")], heading="A")
        self.assertIn("COPIED", codes(GOOD + "\n" + wp("X1", "N1", "Risk", why=t, anchor="r@m2.md#h:A", hash_=h), read=lambda r, p: files.get((r, p))))

class Anchors2(unittest.TestCase):
    def test_ambiguous_and_missing_give_none(self):
        self.assertIsNone(T.anchored_text(FILES[("r", "dup.md")], heading="X")); self.assertIsNone(T.hash_text(MD, heading="Nope"))
    def test_pin_leaves_missing_heading_alone(self):
        text = wp("X1", "", "Need", anchor="r@m.md#h:Nope", hash_="0" * 12); wps, _ = T.parse(text); self.assertEqual(T.pin(text, wps, rd), text)
    def test_copied_checks_section_not_file(self):
        t = "this exact sentence lives only in section b of the file"; files = {("r", "m3.md"): "## A\nshort\n## B\n" + t + "\n"}
        h = T.hash_text(files[("r", "m3.md")], heading="A"); rdr = lambda r, p: files.get((r, p))
        self.assertNotIn("COPIED", codes(GOOD + "\n" + wp("X1", "N1", "Risk", why=t, anchor="r@m3.md#h:A", hash_=h), read=rdr))

class Review(unittest.TestCase):
    OLD, NEW = "## A\nold line\n", "## A\nnew line\n"
    def w(self, content): return T.parse(wp("X1", "N1", "Risk", why="my reason", anchor="r@m.md#h:A", hash_=T.hash_text(content, heading="A")))[0][0]
    def test_find_pinned_newest_match(self):
        w = self.w(self.OLD); hist = [("c3", self.NEW), ("c2", self.OLD), ("c1", "## A\nolder\n"), ("c0", self.OLD)]
        self.assertEqual(T.find_pinned(hist, w), ("c2", "## A\nold line"))
    def test_find_pinned_none(self): self.assertIsNone(T.find_pinned([("c1", self.NEW)], self.w(self.OLD)))
    def test_find_pinned_skips_missing_file(self): self.assertEqual(T.find_pinned([("c2", None), ("c1", self.OLD)], self.w(self.OLD))[0], "c1")
    def test_prompt_contains_diff_and_choices(self):
        w = self.w(self.OLD); p = T.review_prompt(w, ("c1", "## A\nold line"), "## A\nnew line")
        for x in ("X1", "my reason", "pinned@c1", "-old line", "+new line", "--pin", "(a)", "(b)", "(c)"): self.assertIn(x, p)
    def test_prompt_unknown_pin(self): self.assertIn("not found in history", T.review_prompt(self.w(self.OLD), None, "x"))
    def test_prompt_formatting_only(self): self.assertIn("identical", T.review_prompt(self.w(self.OLD), ("c1", "same"), "same"))
    def test_review_only_stale(self):
        files = {("r", "m.md"): self.NEW}; rdr = lambda r, p: files.get((r, p))
        w = self.w(self.OLD); text = T.render(w)
        out = T.review(text, [w], rdr, lambda r, p: [("c2", self.NEW), ("c1", self.OLD)])
        self.assertIn("pinned@c1", out); self.assertIn("+new line", out)
        files[("r", "m.md")] = self.OLD; self.assertEqual(T.review(text, [w], rdr, lambda r, p: []), "No stale waypoints.")
    def test_review_skips_exists_unpinned_and_missing(self):
        rdr = lambda r, p: self.NEW if p == "m.md" else None
        ws = [T.Waypoint(1, "A", "Risk", "t", "w", "r", "m.md", exists=True, hash="0" * 12), T.Waypoint(2, "B", "Risk", "t", "w", "r", "m.md", heading="A"),
              T.Waypoint(3, "C", "Risk", "t", "w", "r", "gone.md", heading="A", hash="0" * 12)]
        self.assertEqual(T.review("", ws, rdr, lambda r, p: []), "No stale waypoints.")
    def test_review_does_not_edit(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d]); f = f"{d}/m.md"
            for i, c in enumerate([self.OLD, self.NEW]):
                open(f, "w").write(c); subprocess.run(["git", "-C", d, "add", "."]); subprocess.run(["git", "-C", d, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", str(i)])
            hist = T.git_history(d, "m.md"); self.assertEqual([c for _, c in hist], [self.NEW, self.OLD])
            self.assertEqual(T.find_pinned(hist, self.w(self.OLD))[1], "## A\nold line")

class Backtest(unittest.TestCase):
    def w(self, **k): return T.Waypoint(1, "X", "Risk", "t", "w", "r", "m.md", heading="A", **k)
    def test_counts_changes_oldest_first(self):
        h = [("c4", "## A\nz\n"), ("c3", "## A\nz\n"), ("c2", "## A\ny\n"), ("c1", "## A\nx\n")]
        self.assertEqual(T.backtest(h, self.w()), (4, 2))
    def test_unrelated_commits_do_not_fire(self):
        h = [("c2", "## A\nx\n## B\n2\n"), ("c1", "## A\nx\n## B\n1\n")]; self.assertEqual(T.backtest(h, self.w()), (2, 0))
    def test_missing_section_skipped_not_fired(self):
        h = [("c3", "## A\nx\n"), ("c2", "## B\n"), ("c1", "## A\nx\n")]; self.assertEqual(T.backtest(h, self.w()), (2, 0))
    def test_missing_file_skipped(self): self.assertEqual(T.backtest([("c2", None), ("c1", "## A\nx\n")], self.w()), (1, 0))
    def test_empty(self): self.assertEqual(T.backtest([], self.w()), (0, 0))

class Properties(unittest.TestCase):
    def rand_wp(self, r, i):
        kinds = list(T.KINDS); return T.Waypoint(i + 1, f"W{i}", r.choice(kinds), "t" + str(r.randint(0, 9)), "why " + "x" * r.randint(3, 9), "r", f"p{r.randint(0,3)}.md",
                                                  *( (lambda a: (a, a + r.randint(0, 5)))(r.randint(1, 20)) if r.random() < .5 else (0, 0)), r.choice(["", "0123456789ab"]),
                                                  tuple(f"W{j}" for j in r.sample(range(i + 1), min(i + 1, r.randint(0, 3)))))
    def test_render_parse_roundtrip(self):
        r = random.Random(1)
        for i in range(300):
            w = self.rand_wp(r, i % 7); w.line = 1; got, bad = T.parse(T.render(w))
            self.assertEqual((got, bad), ([w], []))
    def test_hash_whitespace_invariant(self):
        r = random.Random(2)
        for _ in range(200):
            lines = ["".join(r.choice("ab c") for _ in range(r.randint(0, 8))) for _ in range(r.randint(1, 8))]
            a = "\n".join(lines); b = "\r\n".join(l + "  " for l in lines)
            self.assertEqual(T.hash_text(a), T.hash_text(b))
    def test_hash_changes_on_edit(self):
        r = random.Random(3)
        for _ in range(200):
            s = "".join(r.choice("abcdef\n") for _ in range(30)); t = s + "Z"
            self.assertNotEqual(T.hash_text(s), T.hash_text(t))
    def test_check_deterministic_and_order_independent(self):
        r = random.Random(4); lines = GOOD.split("\n") + [wp("X1", "N1", "Risk"), wp("X2", "", "Risk")]
        base = None
        for _ in range(50):
            r.shuffle(lines); wps, bad = T.parse("\n".join(lines))
            res = sorted((c, m) for c, _, m in T.check(wps, bad, "reviewed", rd))
            base = base or res; self.assertEqual(res, base)
    def test_pin_idempotent_and_clears_unpinned(self):
        text = wp("N1", anchor="r@b.md") + "\n" + wp("D1", "N1, T1", "Decision") + "\n" + wp("T1", "D1", "Test")
        wps, _ = T.parse(text); once = T.pin(text, wps, rd); wps2, _ = T.parse(once); twice = T.pin(once, wps2, rd)
        self.assertEqual(once, twice); self.assertNotIn("UNPINNED", codes(once))
    def test_pin_never_touches_unresolvable(self):
        text = wp("N1", anchor="r@zzz.md", hash_="0" * 12); wps, _ = T.parse(text); self.assertEqual(T.pin(text, wps, rd), text)

class IO(unittest.TestCase):
    def test_reader_and_lint_file(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(f"{d}/repo/.git"); open(f"{d}/repo/f.md", "w").write("hello world\n")
            rdr = T.make_reader([d]); self.assertEqual(rdr("repo", "f.md"), "hello world\n"); self.assertIsNone(rdr("repo", "nope"))
            with self.assertRaises(LookupError): rdr("absent", "f.md")
            tour = f"{d}/TOUR.md"; open(tour, "w").write("---\nstatus: reviewed   # c\n---\n- [N1] **Need: t** - because reasons here `anchor: repo@f.md`\n")
            self.assertEqual([c for c, _, _ in T.lint_file(tour, rdr)], ["MISSINGKIND", "UNPINNED"])
if __name__ == "__main__": unittest.main()
