"""Specs for cluster.py, the cluster_eval gate, and compact.py's use of clusters."""
import os, shutil, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts")); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import set_env
import cluster, cluster_eval, compact

def it(title, body="", kind="gotcha"): return {"kind": kind, "title": title, "body": body}


class Cluster(unittest.TestCase):
    def test_one_shared_topic_word_is_not_a_problem(self):
        self.assertEqual(cluster.cluster([it("kafka retention is seven days"), it("kafka consumer group id must be unique")]), [[0], [1]])

    def test_two_letter_tokens_are_noise(self):
        self.assertEqual(cluster.cluster([it("ci db fails often"), it("ci db slow lately")]), [[0], [1]])

    def test_same_problem_in_different_words_groups(self):
        a = it("pool exhausted errors under load", "hikari pool size was 10; raising to 30 stopped the timeouts")
        b = it("raise the connection pool size", "maximumPoolSize 30 in hikari; timeouts stopped")
        c = it("timezone bug in the weekly report", "dates converted twice")
        self.assertEqual(cluster.cluster([a, b, c]), [[0, 1], [2]])

    def test_average_link_does_not_chain(self):
        # b links to a and to c, but a and c share nothing: single-link would merge all three
        a, b, c = it("alpha beta gamma delta"), it("alpha beta epsilon zeta eta"), it("epsilon zeta theta iota")
        self.assertEqual(cluster.cluster([a, b, c], threshold=0.2), [[0, 1], [2]])

    def test_deterministic_and_order_independent_membership(self):
        items = [e for e in cluster_eval.yaml.safe_load(open(f"{ROOT}/evals/cluster.yaml")) if e["split"] == "dev"]
        self.assertEqual(cluster.cluster(items), cluster.cluster(items))
        rev = cluster.cluster(items[::-1]); n = len(items)
        self.assertEqual(sorted(sorted(n - 1 - i for i in g) for g in rev), sorted(cluster.cluster(items)))


class Eval(unittest.TestCase):
    def test_committed_fixture_passes_the_gate(self):
        self.assertEqual(cluster_eval.main([]), 0)

    def test_gate_catches_mutants(self):
        for name, attr, val in (("no shared-token floor", "MIN_SHARED", 0), ("merge everything", "THRESHOLD", 0.0)):
            old = getattr(cluster, attr)
            try:
                setattr(cluster, attr, val); self.assertEqual(cluster_eval.main([]), 1, name)
            finally: setattr(cluster, attr, old)
        old = cluster.THRESHOLD
        try:
            cluster.THRESHOLD = 0.9; self.assertEqual(cluster_eval.main([]), 1, "never merge")   # recall gate
        finally: cluster.THRESHOLD = old

    def test_each_gate_trips_alone(self):
        self.assertEqual(cluster_eval.main(["--min-recall", "1.01"]), 1)
        self.assertEqual(cluster_eval.main(["--min-gain", "2"]), 1)
        self.assertEqual(cluster_eval.main(["--min-precision", "1.01"]), 1)

    def test_prf_edge_cases(self):
        self.assertEqual(cluster_eval.prf({frozenset((0, 1))}, {frozenset((0, 1)), frozenset((2, 3))})["recall"], 0.5)


class CompactUse(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d)
        for n in ("facts", "inbox", "decisions"): os.makedirs(f"{self.d}/{n}")
        set_env(self, BRAIN_DIR=self.d)
        open(f"{self.d}/inbox/s1.md", "w").write(
            "## [gotcha] pool exhausted errors under load\nhikari pool size was 10; raising to 30 stopped the timeouts\n"
            "## [decision] raise the connection pool size\nmaximumPoolSize 30 in hikari; observed: timeouts stopped\n"
            "## [gotcha] timezone bug in the weekly report\ndates converted twice\n")

    def test_group_is_annotated_and_every_attempt_text_survives_in_every_draft(self):
        out, created = compact.plan(self.d, "2026-01-01", write=True)
        self.assertIn("1 recurring-problem group(s)", out)
        self.assertIn("~~ same recurring problem as: raise the connection pool size", out)
        self.assertEqual(len(created), 3)                                    # grouping never suppresses a draft
        fact = open(f"{self.d}/facts/pool-exhausted-errors-under-load.md").read()
        self.assertIn("observed: timeouts stopped", fact)                     # the sibling's outcome
        dec = open(next(f"{self.d}/{c}" for c in created if c.startswith("decisions/"))).read()
        self.assertIn("raising to 30 stopped the timeouts", dec)               # the sibling's rationale
        self.assertIn("## Predicted outcome", dec); self.assertIn("## Observed", dec)
        self.assertNotIn("Related attempts", open(f"{self.d}/facts/timezone-bug-in-the-weekly-report.md").read())

    def test_drafts_written_this_run_are_not_duplicates_of_each_other(self):
        out, created = compact.plan(self.d, "2026-01-01", write=True)
        self.assertNotIn("probable duplicate", out)                          # regression: sibling lists in draft 1 matched items 2 and 3


if __name__ == "__main__":
    unittest.main()
