"""Meta-tests: the brain's own tooling obeys its definition of done (tests exist, mutants exist, lists only shrink)."""
import glob, os, re, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = "\n".join(open(f).read() for f in glob.glob(f"{ROOT}/tests/test_*.py") if not f.endswith("test_definition_of_done.py"))
GRAND = [l.strip() for l in open(f"{ROOT}/tests/mutants/GRANDFATHERED.txt") if l.strip() and not l.startswith("#")]
MAX_GRANDFATHERED = 0   # ratchet: lower this when a script gains a mutants file; never raise it

class DoD(unittest.TestCase):
    def test_every_script_is_referenced_by_a_test(self):
        for p in glob.glob(f"{ROOT}/scripts/*.py"):
            stem = os.path.basename(p)[:-3]
            self.assertRegex(TESTS, rf"\b{re.escape(stem)}\b", f"{stem}.py has no test")

    def test_every_script_has_mutants_or_is_grandfathered(self):
        for p in glob.glob(f"{ROOT}/scripts/*.py"):
            rel = "scripts/" + os.path.basename(p); stem = os.path.basename(p)[:-3]
            self.assertTrue(os.path.exists(f"{ROOT}/tests/mutants/{stem}.yaml") or rel in GRAND, f"{rel}: add tests/mutants/{stem}.yaml")

    def test_grandfather_list_only_shrinks(self):
        self.assertLessEqual(len(GRAND), MAX_GRANDFATHERED)
        for g in GRAND: self.assertTrue(os.path.exists(f"{ROOT}/{g}"), f"{g} listed but missing")
        for g in GRAND: self.assertFalse(os.path.exists(f"{ROOT}/tests/mutants/{os.path.basename(g)[:-3]}.yaml"), f"{g} has mutants now: remove it from GRANDFATHERED.txt")

    def test_mutant_files_are_well_formed(self):
        import yaml
        for p in glob.glob(f"{ROOT}/tests/mutants/*.yaml"):
            s = yaml.safe_load(open(p)); self.assertTrue(os.path.exists(f"{ROOT}/{s['target']}"), p)
            self.assertTrue(s["mutants"]); ids = [m["id"] for m in s["mutants"]]; self.assertEqual(len(ids), len(set(ids)), f"{p}: duplicate ids")

if __name__ == "__main__": unittest.main()
