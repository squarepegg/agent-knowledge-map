"""session_start, check_freshness, maintain, digest_sessions."""
import datetime, json, os, shutil, sys, tempfile, unittest, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import session_start as ss, check_freshness as cf, maintain, digest_sessions as dg


def ws(slug, status="active", repos=(), branches=(), next_=()):
    return {"slug": slug, "title": "", "status": status, "repos": list(repos), "branches": list(branches), "updated": "", "next": list(next_), "file": f"/x/{slug}/STATE.md"}


class SessionStart(unittest.TestCase):
    def test_branch_evidence(self):
        w = ws("billing-v3", branches=["feat/pp-*"])
        self.assertTrue(ss.branch_evidence(w, "feat/pp-1")); self.assertFalse(ss.branch_evidence(w, "feat/other"))
        self.assertFalse(ss.branch_evidence(w, "main")); self.assertFalse(ss.branch_evidence(w, ""))
        self.assertTrue(ss.branch_evidence(w, "feat/BILLING-V3-x"))                      # slug in branch, case-insensitive
        self.assertFalse(ss.branch_evidence(ws("abc"), "feat/abc"))                        # short slugs are too ambiguous
        self.assertFalse(ss.branch_evidence(ws("zzzzzzz", branches=["*"]), "main")); self.assertFalse(ss.branch_evidence(ws("zzzzzzz", branches=["*"]), "master"))   # default branches never count
        self.assertFalse(ss.branch_evidence(ws("zzzzzzz", branches=["*"]), "")); self.assertTrue(ss.branch_evidence(ws("zzzzzzz", branches=["*"]), "topic"))
        self.assertFalse(ss.branch_evidence(ws("zzzzzzz", branches=["release"]), "RELEASE"))   # globs are case-sensitive

    def test_match_by_repo_branch_and_status(self):
        a = ws("alpha-work", repos=["Svc"]); b = ws("beta-work", status="done", repos=["svc"]); c = ws("gamma-work", status="blocked", repos=["svc"]); d = ws("delta", repos=["other"])
        got = [w["slug"] for w in ss.match([a, b, c, d], "svc", "main")]; self.assertEqual(got, ["alpha-work", "gamma-work"])
        self.assertEqual([w["slug"] for w in ss.match([d, ws("e", branches=["x/*"])], "nomatch", "x/1")], ["e"])
        self.assertEqual(ss.match([a], "", "main"), [])

    def test_likely_needs_exactly_one_with_branch_evidence(self):
        a = ws("alpha-work", repos=["s"], branches=["f/*"]); b = ws("beta-work", repos=["s"])
        self.assertIs(ss.likely([a, b], "f/1"), a); self.assertIsNone(ss.likely([a, b], "main"))
        self.assertIsNone(ss.likely([a, ws("beta-work", repos=["s"], branches=["f/*"])], "f/1"))

    def test_probe(self):
        self.assertTrue(ss.run_probe({"cmd": ["true"]})[0]); self.assertFalse(ss.run_probe({"cmd": ["false"]})[0])
        self.assertTrue(ss.run_probe({"cmd": ["echo", "x"], "okWhen": "stdoutNonEmpty"})[0]); self.assertFalse(ss.run_probe({"cmd": ["true"], "okWhen": "stdoutNonEmpty"})[0])
        self.assertFalse(ss.run_probe({"cmd": ["definitely-not-a-binary-xyz"]})[0])
        self.assertEqual(ss.run_probe({"cmd": ["echo", "hello"]})[1], "hello")

    def test_render(self):
        a = ws("alpha-work", repos=["s"], next_=["do x"]); b = ws("beta-work", repos=["s"])
        out = ss.render("s", "main", [a, b], None, [({"id": "gh", "fix": "login"}, False), ({"id": "d", "label": "Docker"}, True)], ["fact one"])
        self.assertIn("FAIL gh -> fix: login", out); self.assertIn("ok Docker", out); self.assertIn("| next: do x", out)
        self.assertIn("Several match", out); self.assertIn("fact one", out); self.assertNotIn("LIKELY", out)
        self.assertIn("* LIKELY alpha-work", ss.render("s", "b", [a], a, [], []))
        self.assertNotIn("Several match", ss.render("s", "b", [a], None, [], [])); self.assertNotIn("Several match", ss.render("s", "b", [a, b], a, [], []))

    def test_end_to_end_in_a_brain(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d)
        os.makedirs(f"{d}/workstreams/w1"); os.makedirs(f"{d}/facts")
        open(f"{d}/workstreams/w1/STATE.md", "w").write("---\nslug: w1\nstatus: active\nrepos: [myrepo]\nnext: [ship it]\n---\n")
        open(f"{d}/facts/f.md", "w").write("---\ntitle: a gotcha\nrepos: [myrepo]\nverified: false\n---\nx\n")
        self.assertEqual(ss.fact_titles("MyRepo", d), ["(unverified) a gotcha"]); self.assertEqual(ss.fact_titles("nope", d), [])
        self.assertEqual(ss.load_workstreams(d)[0]["next"], ["ship it"])
        self.assertEqual(ss.load_probes(d), [])
        open(f"{d}/probes.yaml", "w").write("- {id: t, cmd: [\"true\"]}\n"); self.assertEqual(ss.load_probes(d)[0]["id"], "t")
        g = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, g); r = os.path.join(g, "myrepo"); os.makedirs(r)
        subprocess.run(["git", "init", "-q", "-b", "feat1", r]); self.assertEqual(ss.git_info(r), ("myrepo", "feat1"))
        self.assertEqual(ss.git_info(g)[0], os.path.basename(g))                               # not a repo: falls back to the dir name, no branch
        self.assertEqual(ss.git_info(g)[1], "")


class Freshness(unittest.TestCase):
    NOW = datetime.datetime(2025, 1, 10, 12, tzinfo=datetime.timezone.utc)

    def test_parse_and_dig(self):
        self.assertEqual(cf.parse_ts("2025-01-10T12:00:00Z"), self.NOW); self.assertEqual(cf.parse_ts("2025-01-10T12:00:00"), self.NOW)
        self.assertIsNone(cf.parse_ts("garbage")); self.assertIsNone(cf.parse_ts(None))
        self.assertEqual(cf.dig({"a": {"b": 3}}, "a.b"), 3); self.assertIsNone(cf.dig({"a": 1}, "a.b")); self.assertIsNone(cf.dig({}, "x"))

    def test_evaluate(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d)
        json.dump({"synced": "2025-01-10T00:00:00Z", "meta": {"at": "2025-01-01T00:00:00Z"}}, open(f"{d}/c.json", "w"))
        r = cf.evaluate([{"name": "fresh", "file": "c.json", "budget_hours": 12}, {"name": "edge", "file": "c.json", "budget_hours": 11.9},
                         {"name": "nested", "file": "c.json", "key": "meta.at", "budget_hours": 24}, {"name": "gone", "file": "nope.json", "budget_hours": 99}], self.NOW, d)
        self.assertEqual([x[3] for x in r], [True, False, False, False]); self.assertAlmostEqual(r[0][1], 12.0); self.assertIsNone(r[3][1])

    def test_main_exit_codes(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); env = {**os.environ, "BRAIN_DIR": d}
        run = lambda: subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "check_freshness.py")], env=env, capture_output=True, text=True)  # noqa: E731
        self.assertEqual(run().returncode, 0)                                                   # nothing configured: nothing stale
        open(f"{d}/freshness.yaml", "w").write("- {name: x, file: x.json, budget_hours: 1}\n"); r = run(); self.assertEqual(r.returncode, 1); self.assertIn("STALE x", r.stdout)
        json.dump({"synced": datetime.datetime.now(datetime.timezone.utc).isoformat()}, open(f"{d}/x.json", "w")); self.assertEqual(run().returncode, 0)


class Maintain(unittest.TestCase):
    def test_due(self):
        self.assertTrue(maintain.due({}, 3)); self.assertTrue(maintain.due({"weekday": 3}, 3)); self.assertFalse(maintain.due({"weekday": 1}, 3)); self.assertTrue(maintain.due({"weekday": "3"}, 3))

    def test_run_steps(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d)
        steps = [{"name": "a", "cmd": ["true"]}, {"name": "b", "cmd": ["false"]}, {"name": "c", "cmd": ["true"], "weekday": 1}, {"name": "e", "cmd": ["no-such-bin-xyz"]},
                 {"name": "slow", "cmd": ["sleep", "5"], "timeout": 0.2}, {"name": "after", "cmd": ["pwd"]}]
        r = maintain.run_steps(steps, 2, cwd=d)
        self.assertEqual(r, {"a": "ok", "b": "failed", "c": "skipped", "e": "failed", "slow": "failed", "after": "ok"})   # a failure never stops later steps
        self.assertEqual(maintain.run_steps(steps, 2, only=["a", "c"], cwd=d), {"a": "ok", "c": "skipped"})
        doc = maintain.write_status(r, d); self.assertEqual(doc["failed"], ["b", "e", "slow"])
        self.assertEqual(json.load(open(f"{d}/status/maintenance.json"))["steps"]["a"], "ok")

    def test_commit_only_when_changed(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d)
        g = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=d, capture_output=True, text=True)  # noqa: E731
        g("init", "-q", "-b", "main"); os.makedirs(f"{d}/facts"); open(f"{d}/facts/a.md", "w").write("1")
        subprocess.run(["git", "config", "user.name", "t"], cwd=d); subprocess.run(["git", "config", "user.email", "t@t"], cwd=d)
        self.assertTrue(maintain.commit(["facts", "missing-dir"], d)); self.assertFalse(maintain.commit(["facts"], d))
        self.assertIn("brain upkeep", g("log", "--oneline").stdout)

    def test_main_exit_code_and_status(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); env = {**os.environ, "BRAIN_DIR": d}
        run = lambda: subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "maintain.py"), "--weekday", "2"], env=env, capture_output=True, text=True)  # noqa: E731
        open(f"{d}/maintenance.yaml", "w").write("steps:\n  - {name: ok, cmd: [\"true\"]}\n"); self.assertEqual(run().returncode, 0)
        open(f"{d}/maintenance.yaml", "w").write("steps:\n  - {name: bad, cmd: [\"false\"]}\n"); self.assertEqual(run().returncode, 1)
        self.assertEqual(json.load(open(f"{d}/status/maintenance.json"))["failed"], ["bad"])


class MaintainCommit(unittest.TestCase):
    def test_no_commit_when_a_step_failed(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d)
        env = {**os.environ, "BRAIN_DIR": d, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d); os.makedirs(f"{d}/facts"); open(f"{d}/facts/a.md", "w").write("1")
        def go(step):
            open(f"{d}/maintenance.yaml", "w").write("steps:\n  - {name: s, cmd: [\"" + step + "\"]}\ncommit: true\ncommit_paths: [facts]\n")
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "maintain.py")], env=env, capture_output=True, text=True)
            return subprocess.run(["git", "log", "--oneline"], cwd=d, capture_output=True, text=True).stdout
        self.assertEqual(go("false"), "")                       # failed step: nothing committed
        self.assertIn("brain upkeep", go("true"))               # clean run: committed


class Digest(unittest.TestCase):
    def test_clean_redacts_and_truncates(self):
        self.assertNotIn("hunter2hunter2", dg.clean("password: hunter2hunter2 ok", 100)); self.assertIn("[REDACTED]", dg.clean("api_key=abcdef", 100))
        self.assertEqual(dg.clean("a   b\n c", 100), "a b c"); self.assertEqual(len(dg.clean("x" * 50, 10)), 10); self.assertEqual(dg.clean(None, 5), "")
        self.assertIn("[REDACTED]", dg.clean("AKIAABCDEFGHIJKLMNOP", 50))

    def test_squash_dedupes_and_prioritises(self):
        lines = ["CMD a", "CMD a", "USER hi", "USER hi"]
        self.assertEqual(dg.squash(lines).split("\n"), ["CMD a", "USER hi", "USER hi"])        # repeats dropped except USER lines
        big = ["CMD " + str(i) * 30 + str(i) for i in range(2000)] + ["USER keep", "ERR bad", "MCP x"]
        out = dg.squash(big); self.assertIn("USER keep", out); self.assertIn("ERR bad", out); self.assertNotIn("CMD 1", out); self.assertLessEqual(len(out), dg.CAP + 30)

    def test_globs(self):
        self.assertEqual(dg.session_globs("pi=/a/*.jsonl" + os.pathsep + "claude=/b/*.jsonl"), [("pi", "/a/*.jsonl"), ("claude", "/b/*.jsonl")])
        self.assertEqual(dg.session_globs("junk"), []); self.assertEqual([k for k, _ in dg.session_globs("")], ["pi", "claude", "codex"])

    def test_digest_claude_and_main(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d)
        p = f"{d}/s.jsonl"
        rows = [{"type": "user", "cwd": "/w", "message": {"content": "please fix the flaky deploy " + "x" * 450}},
                {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}},
                {"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True, "content": "boom denied"}]}}]
        open(p, "w").write("\n".join(json.dumps(r) for r in rows))
        cwd, lines = dg.digest_claude(p); self.assertEqual(cwd, "/w"); self.assertTrue(lines[0].startswith("USER: please fix")); self.assertTrue(any(l.startswith("CALL Bash") for l in lines)); self.assertTrue(any(l.startswith("ERR boom") for l in lines))
        out = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, out)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "digest_sessions.py")], env={**os.environ, "BRAIN_DIR": out, "BRAIN_SESSION_GLOBS": f"claude={d}/*.jsonl"}, capture_output=True, text=True)
        self.assertIn("1 digests", r.stdout); self.assertEqual(len(json.load(open(f"{out}/digests/_index.json"))), 1)
        # sessions without a user turn, or with too little content, are not digested; successful tool results are not errors
        d2 = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d2)
        open(f"{d2}/nouser.jsonl", "w").write(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": f"{i}" * 180}} for i in range(6)]}}) + "\n")
        open(f"{d2}/tiny.jsonl", "w").write(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n")
        out2 = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, out2)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "digest_sessions.py")], env={**os.environ, "BRAIN_DIR": out2, "BRAIN_SESSION_GLOBS": f"claude={d2}/*.jsonl"}, capture_output=True, text=True)
        self.assertIn("0 digests", r.stdout)
        ok = {"type": "user", "message": {"content": [{"type": "tool_result", "is_error": False, "content": "fine"}]}}
        open(f"{d2}/ok.jsonl", "w").write(json.dumps({"type": "user", "message": {"content": "q"}}) + "\n" + json.dumps(ok) + "\n")
        self.assertFalse(any(l.startswith("ERR") for l in dg.digest_claude(f"{d2}/ok.jsonl")[1]))
        big = [f"CMD c{i} " + "z" * 40 for i in range(600)] + ["USER u", "SUMMARY s", "ERR e", "MCP m", "CMD last"]
        body = dg.squash(big); self.assertIn("SUMMARY s", body); self.assertNotIn("CMD last", body)

if __name__ == "__main__": unittest.main()


class SkillEdits(unittest.TestCase):
    def test_apply_edits(self):
        import apply_skill_edits as a
        t, n, sk = a.apply_edits("one two two three", [{"find": "one", "replace": "1"}, {"find": "two", "replace": "2"}, {"find": "nope", "replace": "x"}, {"find": "three", "replace": "three"}])
        self.assertEqual((t, n, sk), ("1 two two three", 1, ["2 matches", "not found", "no-op"]))

    def test_stamp_and_main(self):
        import apply_skill_edits as a
        self.assertEqual(a.stamp("---\nname: x\n---\nbody\n", "2025-01-02", 3), "---\nname: x\nmetadata:\n  verified_at: '2025-01-02'\n  source: verified 2025-01-02\n  unresolved: 3\n---\nbody\n")
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d); os.makedirs(f"{d}/skills/x")
        open(f"{d}/skills/x/SKILL.md", "w").write("---\nname: x\ndescription: d\n---\nold line\n")
        res = f"{d}/r.json"; json.dump({"result": {"skills": [{"skill": "x", "summary": "s" * 200, "edits": [{"find": "old", "replace": "new"}], "unresolved": ["q"]}, {"skill": "gone"}], "missing": []}}, open(res, "w"))
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "apply_skill_edits.py"), res], env={**os.environ, "BRAIN_DIR": d}, capture_output=True, text=True)
        self.assertIn("x: 1 edits applied, 0 skipped, 1 unresolved", r.stdout); self.assertIn("gone: missing file", r.stdout); self.assertIn("s" * 140, r.stdout); self.assertNotIn("s" * 141, r.stdout)
        body = open(f"{d}/skills/x/SKILL.md").read(); self.assertIn("new line", body); self.assertIn("unresolved: 1", body)
