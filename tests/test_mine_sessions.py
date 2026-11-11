"""mine_sessions: recurring errors and user corrections from digests -> candidate inbox entries (deterministic)."""
import os, shutil, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import mine_sessions as ms

def digest(*lines): return "# source: x\n# cwd: /w\n" + "\n".join(lines) + "\n"
ERR = "ERR [bash] kubectl get pods => Error from server (Forbidden): pods is forbidden: cannot list resource in the namespace"

def mk(files):
    d = tempfile.mkdtemp()
    for rel, text in files.items():
        os.makedirs(os.path.dirname(f"{d}/{rel}"), exist_ok=True); open(f"{d}/{rel}", "w").write(text)
    return d


class Normalize(unittest.TestCase):
    def test_variable_parts_are_masked_so_the_same_failure_gets_one_key(self):
        a = ms.normalize_error('ERR [bash] curl https://a.example/x => HTTP 503 from https://svc.internal/api/v2 request 8f3a9c2d1e failed after 3 tries')
        b = ms.normalize_error('ERR [bash] curl https://b.example/y => HTTP 502 from https://other.internal/api/v9 request 1a2b3c4d5e failed after 7 tries')
        self.assertEqual(a, b); self.assertIn("<url>", a); self.assertIn("<n>", a); self.assertIn("<hex>", a); self.assertNotIn("8f3a9c2d1e", a)
        self.assertEqual(ms.normalize_error('ERR cannot open "my file.txt" at /home/u/p/f.py'), "cannot open <q> at <path>")
        self.assertIn("<id>", ms.normalize_error("ERR job 123e4567-e89b-12d3-a456-426614174000 not found anywhere"))

    def test_prefixes_case_whitespace_punctuation_length(self):
        self.assertEqual(ms.normalize_error("ERR [bash] ls /nope => No   Such  FILE or directory.  "), "no such file or directory")      # text after '=>' only, lowercased, collapsed, trimmed
        self.assertEqual(ms.normalize_error("ERR connection refused by the host"), "connection refused by the host")                      # no '=>' : the whole body
        self.assertEqual(ms.normalize_error("plain line without a prefix that is long enough"), "plain line without a prefix that is long enough")
        self.assertEqual(ms.normalize_error("ERR too short"), ""); self.assertEqual(len(ms.normalize_error("ERR " + "word " * 40)), 90)  # capped at 90 characters
        self.assertEqual(ms.normalize_error("ERR " + "x" * 11), ""); self.assertEqual(ms.normalize_error("ERR " + "x" * 12), "x" * 12)   # boundary

class Aggregate(unittest.TestCase):
    def test_parse_digest(self):
        errs, users = ms.parse_digest(digest("USER: hello", "CMD ls", ERR, "USER: that's wrong", "ERR second one here ok", "ERRATIC behaviour noted by the user")); self.assertEqual(len(errs), 2); self.assertEqual(users, ["hello", "that's wrong"])

    def test_recurring_errors_need_enough_distinct_sessions(self):
        s = {"a.txt": digest(ERR, ERR), "b.txt": digest(ERR.replace("Forbidden", "Forbidden")), "c.txt": digest("ERR something else entirely happened")}
        c = ms.aggregate(s); self.assertEqual([x["kind"] for x in c], ["gotcha"]); self.assertEqual(c[0]["count"], 2)                      # two sessions; repeats inside one session count once
        self.assertTrue(c[0]["title"].startswith("Recurring error: error from server")); self.assertIn("seen in 2 sessions; example: ERR [bash] kubectl", c[0]["body"])
        self.assertEqual(ms.aggregate(s, min_sessions=3), []); self.assertEqual(len(ms.aggregate(s, min_sessions=1)), 2)
        self.assertEqual(ms.aggregate({"a.txt": digest(ERR, ERR)}), [])                                                                    # one session only

    def test_the_same_error_twice_in_one_session_is_still_one_session(self):
        e1, e2 = "ERR first failure mode appears here", "ERR second failure mode appears here"
        self.assertEqual(ms.aggregate({"a": digest(e1, e2, e1)}), [])

    def test_example_is_the_first_occurrence_cut_to_200_chars(self):
        v1 = "ERR [bash] run 1 => connection to host 10.0.0.1 refused by peer"; v2 = "ERR [bash] run 2 => connection to host 10.0.0.2 refused by peer"
        self.assertIn("example: " + v1, ms.aggregate({"a": digest(v1), "b": digest(v2)})[0]["body"])
        long = "ERR [bash] x => " + "connection refused " * 30; body = ms.aggregate({"a": digest(long), "b": digest(long)})[0]["body"]; self.assertEqual(body.split("example: ", 1)[1], long[:200])

    def test_corrections_that_differ_only_in_spacing_merge(self):
        c = ms.aggregate({"a": digest("USER: that's wrong,   use the other table"), "b": digest("USER: that's wrong, use the other table")}); self.assertEqual((len(c), c[0]["count"]), (1, 2))

    def test_user_corrections_are_candidates_even_from_one_session(self):
        s = {"a.txt": digest("USER: please add a test", "USER: That's wrong, use the other table"), "b.txt": digest("USER: That's wrong, use the other table")}
        c = ms.aggregate(s); self.assertEqual(len(c), 1); self.assertEqual((c[0]["kind"], c[0]["count"]), ("correction", 2)); self.assertEqual(c[0]["title"], "That's wrong, use the other table")
        self.assertIn("pushed back in 2 session(s)", c[0]["body"]); long = "That's wrong " + "x" * 400
        self.assertEqual(len(ms.aggregate({"a": digest("USER: " + long)})[0]["title"]), 300)

    def test_ordering_is_by_count_then_title(self):
        s = {"s1": digest("USER: no, that's not right, c", "USER: no, that's not right, b"), "s2": digest("USER: no, that's not right, b", "USER: no, that's not right, a")}
        self.assertEqual([x["title"] for x in ms.aggregate(s)], ["no, that's not right, b", "no, that's not right, a", "no, that's not right, c"])      # count first; ties by title, not by input order


class Known(unittest.TestCase):
    def test_known_by_brain_or_inbox(self):
        d = mk({"facts/f.md": "kubectl pods forbidden namespace error\n", "inbox/x.md": "\n## [gotcha] Recurring error: already queued thing happened\nbody\n"}); self.addCleanup(shutil.rmtree, d)
        self.assertTrue(ms.known({"title": "Recurring error: kubectl pods forbidden namespace"}, d))                                         # prefix stripped, all words on one fact line
        self.assertTrue(ms.known({"title": "Recurring error: already queued thing happened"}, d))                                           # same title in the inbox
        self.assertFalse(ms.known({"title": "Recurring error: brand new failure mode"}, d)); self.assertFalse(ms.known({"title": "Recurring error: kubectl pods wibble"}, d))

    def test_run_filters_known_limits_and_counts(self):
        d = mk({"facts/f.md": "error from server forbidden pods cannot list resource in the namespace\n", "digests/a.txt": digest(ERR, "ERR brand new failure mode appears here"), "digests/b.txt": digest(ERR, "ERR brand new failure mode appears here"), "digests/c.txt": digest("ERR third unique failure appears now")})
        self.addCleanup(shutil.rmtree, d); c, n = ms.run(f"{d}/digests", d); self.assertEqual(n, 3); self.assertEqual([x["title"] for x in c], ["Recurring error: brand new failure mode appears here"])
        c, _ = ms.run(f"{d}/digests", d, min_sessions=1, top=1); self.assertEqual(len(c), 1)


class Cli(unittest.TestCase):
    def run_cli(self, d, *a):
        return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "mine_sessions.py"), *a], env={**os.environ, "BRAIN_DIR": d}, capture_output=True, text=True)

    def test_plan_then_write_then_nothing_new(self):
        d = mk({"digests/a.txt": digest("ERR brand new failure mode appears here", "USER: no, that's not right"), "digests/b.txt": digest("ERR brand new failure mode appears here")}); self.addCleanup(shutil.rmtree, d)
        r = self.run_cli(d); self.assertEqual(r.returncode, 0); self.assertIn("2 digest(s), 2 new candidate(s)", r.stdout); self.assertIn("- [gotcha] x2 Recurring error: brand new failure mode appears here", r.stdout); self.assertFalse(os.path.exists(f"{d}/inbox"))
        r = self.run_cli(d, "--write"); self.assertIn("wrote 2 inbox entries", r.stdout); text = "".join(open(f"{d}/inbox/{f}").read() for f in os.listdir(f"{d}/inbox"))
        self.assertIn("## [gotcha] Recurring error: brand new failure mode appears here", text); self.assertIn("## [correction] no, that's not right", text)
        r = self.run_cli(d, "--write"); self.assertIn("0 new candidate(s)", r.stdout); self.assertIn("nothing to write", r.stdout)               # dedupes against its own earlier output

    def test_flags_and_positional_digest_dir(self):
        d = mk({"elsewhere/a.txt": digest("ERR brand new failure mode appears here"), "elsewhere/b.txt": digest("ERR brand new failure mode appears here")}); self.addCleanup(shutil.rmtree, d)
        self.assertIn("0 digest(s)", self.run_cli(d).stdout); r = self.run_cli(d, f"{d}/elsewhere"); self.assertIn("2 digest(s), 1 new candidate(s)", r.stdout)
        self.assertIn("0 new candidate(s)", self.run_cli(d, f"{d}/elsewhere", "--min", "3").stdout); self.assertIn("1 new candidate(s)", self.run_cli(d, "--min", "2", f"{d}/elsewhere").stdout)
        d2 = mk({"digests/a.txt": digest(*[f"ERR distinct failure number {chr(97 + i) * 6} appears" for i in range(4)]), "digests/b.txt": digest(*[f"ERR distinct failure number {chr(97 + i) * 6} appears" for i in range(4)])}); self.addCleanup(shutil.rmtree, d2)
        self.assertIn("2 new candidate(s)", self.run_cli(d2, "--top", "2").stdout); self.assertIn("1 new candidate(s)", self.run_cli(d2, "--top", "1").stdout)
        r = self.run_cli(d2, "--write", "--top", "1"); self.assertIn("wrote 1 inbox entry", r.stdout)

if __name__ == "__main__": unittest.main()
