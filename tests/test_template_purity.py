"""Template repo only (CI sets CHECK_TEMPLATE=1): the published template must carry nothing organisation-specific. Not run in users' own brains."""
import os, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANNED = [b.strip() for b in os.environ.get("TEMPLATE_BANNED", "").split(",") if b.strip()]

@unittest.skipUnless(os.environ.get("CHECK_TEMPLATE") == "1", "template repo only")
class Purity(unittest.TestCase):
    def test_no_org_specific_strings(self):
        bad = []
        for dp, dn, fn in os.walk(ROOT):
            dn[:] = [x for x in dn if x not in (".git", "__pycache__", ".cache")]
            for f in fn:
                if f in ("test_template_purity.py", "test_examples.py", "PRIMER.md") or f.endswith(".pyc"): continue
                low = open(os.path.join(dp, f), errors="ignore").read().lower()
                bad += [f"{os.path.relpath(os.path.join(dp, f), ROOT)}: {b}" for b in BANNED if b in low]
        self.assertEqual(bad, [])

if __name__ == "__main__": unittest.main()
