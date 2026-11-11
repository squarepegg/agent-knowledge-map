"""Spec for scripts/apply_verdicts.py: applies fact-verification verdicts to facts/*.md frontmatter. Never deletes. Throwaway BRAIN_DIR."""
import datetime, json, os, re, subprocess, sys, tempfile, unittest
import yaml
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts")); os.environ.setdefault("BRAIN_DIR", ROOT)
import apply_verdicts as av  # noqa: E402

TODAY = datetime.date.today().isoformat()


def fact(**fm):
    return "---\n" + yaml.safe_dump({"title": "T", **fm}, sort_keys=False) + "---\nBody line.\n"


def fm_of(text):
    return yaml.safe_load(re.match(r"^---\n(.*?)\n---", text, re.S).group(1))


class SetFm(unittest.TestCase):
    def test_updates_drops_and_orders_keys_and_keeps_body(self):
        t = fact(confidence="high", recorded_at="2026-01-01", extra="x", tags=["a"], verified=False)
        out = av.set_fm(t, {"verified": True, "verified_at": "D"}, drop=("recorded_at",))
        fm = fm_of(out); self.assertNotIn("recorded_at", fm); self.assertEqual((fm["verified"], fm["verified_at"], fm["extra"]), (True, "D", "x"))
        keys = list(fm); self.assertLess(keys.index("title"), keys.index("tags")); self.assertLess(keys.index("tags"), keys.index("verified")); self.assertLess(keys.index("verified"), keys.index("confidence")); self.assertEqual(keys[-1], "extra")
        self.assertTrue(out.endswith("---\nBody line.\n")); self.assertTrue(out.startswith("---\n"))

    def test_unicode_and_long_lines_survive_unescaped_and_unfolded(self):
        long = "Café — résumé " + "word " * 30
        out = av.set_fm(fact(title=long), {"verified": True}); self.assertEqual(fm_of(out)["title"], long)
        self.assertIn("Café — résumé", out); self.assertIn("word " * 30, out)  # readable in the file: not \\xe9-escaped, not folded across lines


class RepoExists(unittest.TestCase):
    def test_needs_a_git_dir_in_one_of_the_roots(self):
        root = tempfile.mkdtemp(); os.makedirs(os.path.join(root, "has", ".git")); os.makedirs(os.path.join(root, "nogit"))
        old = av.ROOTS; av.ROOTS = [os.path.join(root, "x"), root]
        try: self.assertTrue(av.repo_exists("has")); self.assertFalse(av.repo_exists("nogit")); self.assertFalse(av.repo_exists("missing"))
        finally: av.ROOTS = old


class Main(unittest.TestCase):
    def apply(self, facts, results, repos=()):
        brain = tempfile.mkdtemp(); os.makedirs(os.path.join(brain, "facts"))
        for name, text in facts.items(): open(os.path.join(brain, "facts", name), "w").write(text)
        root = tempfile.mkdtemp()
        for r in repos: os.makedirs(os.path.join(root, r, ".git"))
        res = os.path.join(brain, "res.json"); json.dump(results, open(res, "w"))
        code = f"import sys; sys.path.insert(0, {os.path.join(ROOT, 'scripts')!r}); import apply_verdicts as av; av.ROOTS = [{root!r}]; sys.argv = ['x', {res!r}]; av.main()"
        r = subprocess.run([sys.executable, "-c", code], env={**os.environ, "BRAIN_DIR": brain}, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        read = lambda n: open(os.path.join(brain, "facts", n)).read()  # noqa: E731
        rv = os.path.join(brain, "review", "facts-review.md")
        return read, (open(rv).read() if os.path.exists(rv) else None), r.stdout

    def test_confirmed_marks_verified_merges_only_real_anchors_drops_recorded_and_verify_by(self):
        read, review, out = self.apply({"a.md": fact(verified=False, recorded_at="2026-01-01", verify_by="human", anchors=["old@1"])},
            [{"file": "facts/a.md", "verdict": "confirmed", "anchors": ["real@abc", "fake@abc", "noat", "real", "real@abc"]}], repos=["real", "noat"])
        fm = fm_of(read("a.md")); self.assertEqual((fm["verified"], fm["verified_at"]), (True, TODAY)); self.assertNotIn("recorded_at", fm); self.assertNotIn("verify_by", fm)
        self.assertEqual(fm["anchors"], ["old@1", "real@abc"])  # fake repo ignored; entries without '@' ignored even if the repo exists; deduped; existing kept
        self.assertIn("applied: {'confirmed': 1}", out); self.assertIn("review items: 0", out); self.assertEqual(review.count("###"), 0)

    def test_partly_and_contradicted_stay_unverified_low_confidence_and_are_queued_for_review(self):
        read, review, _ = self.apply({"p.md": fact(title="Partly one", confidence="high"), "c.md": fact(title="Wrong one")},
            [{"file": "p.md", "verdict": "partly", "evidence": "EVP", "fix": "FIXP"}, {"file": "c.md", "verdict": "contradicted", "evidence": "EVC", "fix": "FIXC"}])
        for n in ("p.md", "c.md"): fm = fm_of(read(n)); self.assertEqual((fm["confidence"], fm["verify_by"]), ("low", "human")); self.assertNotIn("verified_at", fm)
        self.assertIn("⚠️ partly wrong: Partly one", review); self.assertIn("❌ contradicted: Wrong one", review); self.assertIn("EVP", review); self.assertIn("FIXC", review); self.assertIn("`facts/p.md`", review)

    def test_unverifiable_gets_verify_by_and_a_yes_no_item(self):
        read, review, _ = self.apply({"u.md": fact(title="Unknown thing"), "v.md": fact(title="Live one")},
            [{"file": "u.md", "verdict": "unverifiable", "evidence": "EVU"}, {"file": "v.md", "verdict": "unverifiable", "verify_by": "live", "evidence": "x"}])
        self.assertEqual(fm_of(read("u.md"))["verify_by"], "human"); self.assertEqual(fm_of(read("v.md"))["verify_by"], "live")
        self.assertIn("❓ Unknown thing", review); self.assertIn("EVU", review); self.assertIn("still true", review)

    def test_missing_file_is_skipped_and_nothing_is_ever_deleted(self):
        read, review, out = self.apply({"keep.md": fact()}, [{"file": "ghost.md", "verdict": "confirmed"}, {"file": "keep.md", "verdict": "partly"}])
        self.assertIn("skip missing", out); self.assertTrue(read("keep.md")); self.assertIn("applied: {'partly': 1}", out)

    def test_counts_are_per_verdict_and_title_falls_back_to_the_file_name(self):
        _, review, out = self.apply({"a.md": fact(), "b.md": fact(), "n.md": "---\nrepos: []\n---\nBody\n"},
            [{"file": "a.md", "verdict": "confirmed"}, {"file": "b.md", "verdict": "confirmed"}, {"file": "n.md", "verdict": "partly"}])
        self.assertIn("applied: {'confirmed': 2, 'partly': 1}", out); self.assertIn("partly wrong: n.md", review)

    def test_accepts_dict_wrapper_and_uses_basename_only(self):
        read, review, out = self.apply({"w.md": fact()}, {"results": [{"file": "some/dir/w.md", "verdict": "confirmed"}]})
        self.assertTrue(fm_of(read("w.md"))["verified"]); self.assertIn("applied: {'confirmed': 1}", out)

    def test_review_file_header_and_counts(self):
        _, review, out = self.apply({"a.md": fact(), "b.md": fact()}, [{"file": "a.md", "verdict": "partly"}, {"file": "b.md", "verdict": "confirmed"}])
        self.assertTrue(review.startswith(f"# Facts needing your call ({TODAY})")); self.assertIn("review items: 1", out)


if __name__ == "__main__":
    unittest.main()
