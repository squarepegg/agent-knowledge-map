"""Scoped language properties and CLI integration for _records/build_primer/lint_facts.

The semantic examples exercise actual record validation and context rendering;
retrieval scores are reported separately from behavioral evidence.
"""
import datetime
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import _records
import build_primer
import _context


class DomainLanguage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.b = Path(self.tmp.name).resolve()
        (self.b / 'facts').mkdir()
        self.fact('meaning', 'records')

    def fact(self, slug, context):
        fm = dict(record_version=1, title='Verification attestation', context=context,
                  verified=False, recorded_at=str(datetime.date.today()), confidence='low',
                  source='contract fixture')
        p = self.b / f'facts/{slug}.md'
        p.write_text(_records.render(fm, 'Verification records an observation; it does not establish truth.\n'))
        return p

    def entry(self, **changes):
        return dict(dict(record_version=1, term='Verified', context='records', kind='concept',
                         one_liner='A recorded verification attestation.', aliases=['attested'],
                         definition='facts/meaning.md', repos=[]), **changes)

    def lint(self, entries):
        (self.b / 'glossary.yaml').write_text(yaml.safe_dump(entries, allow_unicode=True))
        return subprocess.run([sys.executable, str(ROOT / 'scripts/lint_facts.py'), '--strict'],
                              env={**os.environ, 'BRAIN_DIR': str(self.b), 'BRAIN_REPOS_ROOT': str(self.b)},
                              capture_output=True, text=True)

    def test_same_term_in_different_contexts_is_valid(self):
        self.fact('other', 'bundles')
        r = self.lint([self.entry(), self.entry(context='bundles', definition='facts/other.md')])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_ambiguous_canonical_names_and_aliases_fail_strict_lint(self):
        for second in [self.entry(term=' VERIFIED '), self.entry(term='Attested', aliases=[]),
                       self.entry(term='Other', aliases=['  ATTESTED  '])]:
            with self.subTest(second=second):
                r = self.lint([self.entry(), second])
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn('GLOSSARY', r.stdout)

    def test_versioned_fields_and_local_aliases_are_validated(self):
        cases = [dict(record_version=True), dict(record_version=2), dict(term=' '), dict(context=' '),
                 dict(kind='invented'), dict(kind=[]), dict(one_liner='x' * 141), dict(one_liner=[]), dict(aliases='attested'),
                 dict(aliases=['']), dict(aliases=['VERIFIED']), dict(aliases=['a', ' A ']),
                 dict(definition=None), dict(repos='repo')]
        for changes in cases:
            with self.subTest(changes=changes):
                r = self.lint([self.entry(**changes)])
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertNotIn('Traceback', r.stderr)

    def test_legacy_entries_are_unchanged(self):
        r = self.lint([dict(term='Legacy', kind='system', one_liner='Old entry', core=True)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out, _ = build_primer.build(str(self.b))
        self.assertIn('**Legacy** — Old entry', out)

    def test_definition_references_are_confined_and_scoped(self):
        outside = self.b.parent / (self.b.name + '-outside.md')
        outside.write_text('outside')
        self.addCleanup(outside.unlink)
        (self.b / 'facts/link.md').symlink_to(outside)
        for path in ['../outside.md', str(outside), 'docs/meaning.md', 'facts/missing.md',
                     'facts/link.md', 'facts/../facts/meaning.md']:
            with self.subTest(path=path):
                r = self.lint([self.entry(definition=path)])
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn('GLOSSARY', r.stdout)
        # Remove the deliberately unsafe unrelated fact: otherwise its PARSE error
        # could mask a broken glossary-context check (caught by mutation testing).
        (self.b / 'facts/link.md').unlink()
        r = self.lint([self.entry(context='wrong')])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('GLOSSARY', r.stdout)
        self.fact('invalid', 'records').write_text('---\nrecord_version: 1\ncontext: records\n---\nunsupported\n')
        self.assertEqual(self.lint([self.entry(definition='facts/invalid.md')]).returncode, 1)
        (self.b / 'facts/legacy.md').write_text('---\ncontext: records\n---\nBare legacy mapping\n')
        r = self.lint([self.entry(definition='facts/legacy.md')])
        self.assertEqual(r.returncode, 1)
        self.assertIn('GLOSSARY', r.stdout)

    def test_core_labels_expose_context_without_expanding_definitions(self):
        self.fact('other', 'bundles')
        r = self.lint([self.entry(core=True), self.entry(context='bundles', definition='facts/other.md', core=True)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out, over = build_primer.build(str(self.b))
        self.assertFalse(over)
        self.assertIn('**Verified [records]**', out)
        self.assertIn('**Verified [bundles]**', out)
        self.assertNotIn('Verification records an observation', out)

    def test_generated_namespace_collisions_and_order_independence(self):
        rng = random.Random(6154)
        for i in range(20):
            term = f'Word{i}'; context = f'Context{rng.randrange(4)}'
            self.fact('meaning', context)
            a = self.entry(term=term, context=context, aliases=[f'Alias{i}'])
            b = self.entry(term=term.upper(), context=' ' + context.lower() + ' ', aliases=[])
            for entries in ([a, b], [b, a]):
                self.assertTrue(_records.glossary_errors(entries, self.b))
            self.fact('other', 'independent')
            b.update(context='independent', definition='facts/other.md')
            self.assertEqual(_records.glossary_errors([a, b], self.b), [])
            self.assertEqual(_records.glossary_errors([b, a], self.b), [])

    def test_record_verification_does_not_imply_context_verified(self):
        # Same domain word, different predicates: dated attestation versus presentation.
        p = self.fact('old', 'records')
        fm, body = _records.parse(p.read_text())
        fm.update(verified=True, verified_at='2000-01-01')
        p.write_text(_records.render(fm, body))
        self.assertEqual(_records.validate(fm, 'fact'), [])
        out = _context.bundle(self.b, 'attestation', 8000, cwd=str(self.b))
        self.assertIn('[stale] facts/old.md', out)
        self.assertNotIn('[verified] facts/old.md', out)
        fm.update(verified_at=str(datetime.date.today()))
        p.write_text(_records.render(fm, body))
        self.assertIn('[verified] facts/old.md', _context.bundle(self.b, 'attestation', 8000, cwd=str(self.b)))

    def test_invalid_scoped_kind_does_not_overwrite_primer(self):
        self.lint([self.entry(kind=[], core=True)])
        primer = self.b / 'PRIMER.md'; primer.write_text('Existing router\n')
        r = subprocess.run([sys.executable, str(ROOT / 'scripts/build_primer.py')],
                           env={**os.environ, 'BRAIN_DIR': str(self.b)}, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn('Traceback', r.stderr)
        self.assertEqual(primer.read_text(), 'Existing router\n')


if __name__ == '__main__':
    unittest.main()
