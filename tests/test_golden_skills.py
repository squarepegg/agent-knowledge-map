"""Spec for scripts/golden_skills.py: deterministic golden checks (frontmatter, pins, size budget, repo refs, --changed selection, config validation)."""
import json, os, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts")); os.environ.setdefault("BRAIN_DIR", ROOT); os.environ["GOLDEN_REPO_PREFIXES"] = "org-,svc-,sys-"
import golden_skills as g  # noqa: E402

GOOD = "---\nname: demo\ndescription: Use when demoing.\n---\n# Demo\nSee `org-real` and `svc-real`. Keep ME.\n"


def brain(text=GOOD, name="demo"):
    d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "skills", name)); open(os.path.join(d, "skills", name, "SKILL.md"), "w").write(text); return d


REPOS = {"org-real", "svc-real"}


def check(text=GOOD, repos=REPOS, **entry):
    return g.check_skill({"skill": "demo", **entry}, brain(text), repos)


class Frontmatter(unittest.TestCase):
    def test_clean_skill_passes(self): self.assertEqual(check(), [])
    def test_name_must_equal_directory(self): self.assertIn("frontmatter name is 'other'", check(GOOD.replace("name: demo", "name: other"))[0])
    def test_missing_frontmatter_fails_name_and_description(self):
        out = check("# no frontmatter\n"); self.assertEqual(len(out), 2); self.assertTrue(any("description missing" in o for o in out))
    def test_blank_description_fails(self): self.assertTrue(any("description missing" in o for o in check(GOOD.replace("Use when demoing.", "' '"))))
    def test_non_string_description_fails(self): self.assertTrue(any("description missing" in o for o in check(GOOD.replace("Use when demoing.", "[1]"))))
    def test_description_length_boundary(self):
        self.assertEqual(check(GOOD.replace("Use when demoing.", "x" * 1024)), [])
        self.assertTrue(any("1025 chars > 1024" in o for o in check(GOOD.replace("Use when demoing.", "x" * 1025))))
    def test_unterminated_or_invalid_yaml_frontmatter_is_not_a_crash(self):
        self.assertEqual(g.split_frontmatter("---\nname: x\nno end"), ({}, "---\nname: x\nno end"))
        self.assertEqual(g.split_frontmatter("---\nname: [unclosed\n---\nbody")[0], {})
        self.assertEqual(g.split_frontmatter("---\n- a list\n---\nbody")[0], {})
    def test_missing_skill_file(self): self.assertEqual(g.check_skill({"skill": "nope"}, brain(), REPOS), ["nope: SKILL.md not found"])


class Pins(unittest.TestCase):
    def test_present_pin_passes(self): self.assertEqual(check(pins=["Keep ME"]), [])
    def test_missing_pin_fails_each(self): self.assertEqual(len(check(pins=["gone", "also gone", "Keep ME"])), 2)
    def test_pin_is_case_sensitive(self): self.assertEqual(len(check(pins=["keep me"])), 1)


class Budget(unittest.TestCase):
    def test_boundary(self):
        n = len(GOOD); self.assertEqual(check(max_chars=n), []); self.assertEqual(len(check(max_chars=n - 1)), 1)
    def test_zero_budget_is_enforced_not_ignored(self): self.assertEqual(len(check(max_chars=0)), 1)
    def test_no_budget_means_no_limit(self): self.assertEqual(check(GOOD + "x" * 100000), [])


class RepoRefs(unittest.TestCase):
    def test_unknown_repo_fails(self): self.assertIn("unknown repo `org-ghost`", check(GOOD + "`org-ghost`\n")[0])
    def test_allow_repos_exempts_only_that_name(self):
        out = check(GOOD + "`org-ghost` `svc-ghost`\n", allow_repos=["org-ghost"]); self.assertEqual(len(out), 1); self.assertIn("svc-ghost", out[0])
    def test_each_prefix_is_checked(self):
        self.assertEqual(len(check(GOOD + "`org-x` `svc-x` `sys-x`\n")), 3)
    def test_unticked_or_other_prefix_is_ignored(self): self.assertEqual(check(GOOD + "org-ghost and `foo-bar`\n"), [])
    def test_prefix_is_literal_not_regex_and_unset_disables(self):
        os.environ["GOLDEN_REPO_PREFIXES"] = "a.b-"
        try: self.assertEqual(check(GOOD + "`axb-ghost`\n"), []); self.assertEqual(len(check(GOOD + "`a.b-ghost`\n")), 1)
        finally: os.environ["GOLDEN_REPO_PREFIXES"] = "org-,svc-,sys-"
        del os.environ["GOLDEN_REPO_PREFIXES"]
        try: self.assertEqual(check(GOOD + "`org-ghost`\n"), [])
        finally: os.environ["GOLDEN_REPO_PREFIXES"] = "org-,svc-,sys-"
    def test_repeats_reported_once(self): self.assertEqual(len(check(GOOD + "`org-ghost` `org-ghost`\n")), 1)


class KnownRepos(unittest.TestCase):
    def test_reads_inventory_and_local_clones(self):
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "repos"))
        json.dump({"repos": [{"name": "from-inventory"}]}, open(os.path.join(d, "repos", "repos.json"), "w"))
        json.dump({"clones": {"from-clone": []}}, open(os.path.join(d, "repos", "local-clones.json"), "w"))
        r = g.known_repos(d); self.assertTrue({"from-inventory", "from-clone"} <= r)
    def test_missing_or_corrupt_inventory_is_not_a_crash(self):
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "repos")); open(os.path.join(d, "repos", "repos.json"), "w").write("{bad")
        self.assertIsInstance(g.known_repos(d), set)


class Config(unittest.TestCase):
    def write(self, text): f = tempfile.mktemp(suffix=".yaml"); open(f, "w").write(text); return f
    def test_valid(self): self.assertEqual(g.load_config(self.write("- {skill: a}\n- {skill: b}\n")), [{"skill": "a"}, {"skill": "b"}])
    def test_rejects_non_list_missing_skill_duplicates_bad_yaml_and_missing_file(self):
        for bad in ("a: 1", "- {pins: []}", "- {skill: a}\n- {skill: a}", "- [unclosed", "- skill"):
            with self.assertRaises(SystemExit, msg=bad): g.load_config(self.write(bad))
        with self.assertRaises(SystemExit): g.load_config("/no/such/file.yaml")
    def test_shipped_config_is_valid_and_passes(self):
        self.assertEqual({k: v for k, v in g.run(os.path.join(ROOT, "evals", "golden", "skills.yaml")).items() if v}, {})


class Run(unittest.TestCase):
    def cfg(self): f = tempfile.mktemp(suffix=".yaml"); open(f, "w").write("- {skill: demo, pins: [Keep ME]}\n- {skill: other}\n"); return f
    def test_changed_filters_to_named_skills(self):
        d = brain(); res = g.run(self.cfg(), d, changed={"demo"}, repos=REPOS); self.assertEqual(list(res), ["demo"]); self.assertEqual(res["demo"], [])
    def test_empty_changed_set_checks_nothing(self): self.assertEqual(g.run(self.cfg(), brain(), changed=set(), repos=REPOS), {})
    def test_none_means_all(self): self.assertEqual(set(g.run(self.cfg(), brain(), repos=REPOS)), {"demo", "other"})


class Changed(unittest.TestCase):
    def test_git_diff_maps_paths_to_skills(self):
        d = tempfile.mkdtemp(); sh = lambda *a: subprocess.run(["git", "-C", d, "-c", "user.email=a@b", "-c", "user.name=t", *a], check=True, capture_output=True)
        os.makedirs(os.path.join(d, "skills", "a")); os.makedirs(os.path.join(d, "skills", "b"))
        open(os.path.join(d, "skills", "a", "SKILL.md"), "w").write("1"); open(os.path.join(d, "skills", "b", "SKILL.md"), "w").write("1"); open(os.path.join(d, "top.md"), "w").write("1")
        sh("init", "-q"); sh("add", "-A"); sh("commit", "-qm", "x")
        open(os.path.join(d, "skills", "a", "SKILL.md"), "w").write("2"); open(os.path.join(d, "top.md"), "w").write("2")
        self.assertEqual(g.changed_skills("HEAD", d), {"a"})
    def test_bad_ref_exits(self):
        with self.assertRaises(SystemExit): g.changed_skills("no-such-ref", ROOT)


class Cli(unittest.TestCase):
    def test_exit_codes(self):
        d = brain(); cfg = tempfile.mktemp(suffix=".yaml")
        env = {**os.environ, "BRAIN_DIR": d}
        def run(c):
            open(cfg, "w").write(c); return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "golden_skills.py"), "--config", cfg], env=env, capture_output=True, text=True)
        ok = run("- {skill: demo, allow_repos: [org-real, svc-real]}"); self.assertEqual(ok.returncode, 0); self.assertIn("1/1 skills pass", ok.stdout)
        bad = run("- {skill: demo, pins: [absent]}"); self.assertEqual(bad.returncode, 1); self.assertIn("FAIL demo", bad.stdout)
        self.assertNotEqual(run("nonsense: [").returncode, 0)


if __name__ == "__main__":
    unittest.main()
