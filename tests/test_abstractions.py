"""Contract tests: invoke real CLI/compactor/lint against isolated Markdown brains.

The YAML table defines expected behavior for _records and _context through the CLI. Generated sweeps check byte conservation,
idempotence, schema consistency and context budgets; no model or network is needed.
"""
import datetime
import hashlib
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
CASES = yaml.safe_load((ROOT / 'tests/fixtures/abstractions.yaml').read_text())
TODAY = str(datetime.date.today())


class Abstractions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.b = Path(self.tmp.name) / 'brain'
        self.b.mkdir()
        for d in ('facts', 'workstreams', 'templates', 'inbox'):
            (self.b / d).mkdir()
        shutil.copy(ROOT / 'templates/STATE.md', self.b / 'templates/STATE.md')
        self.env = {**os.environ, 'BRAIN_DIR': str(self.b), 'BRAIN_REPOS_ROOT': str(self.b.parent)}

    def cli(self, *args, script='brain.py'):
        return subprocess.run([sys.executable, str(ROOT / 'scripts' / script), *args],
                              env=self.env, cwd=ROOT, capture_output=True, text=True)

    def write(self, rel, fm, body='A claim.\n'):
        p = self.b / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('---\n' + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + '---\n' + body)
        return p

    def read(self, p):
        _, fm, body = p.read_text().split('---', 2)
        return yaml.safe_load(fm), body.lstrip('\n')

    def draft(self, **changes):
        return dict(dict(record_version=1, title='Zebra worker', confidence='low', verified=False,
                         recorded_at=TODAY, source='test', repos=[], tags=[], anchors=[]), **changes)

    def state(self, status='active'):
        return dict(record_version=1, slug='worker', title='Worker', status=status, updated=TODAY,
                    repos=['example'], branches=[], next=['finish'], links=[])

    def test_completion_table(self):
        for row in CASES['completion']:
            with self.subTest(row['id']):
                p = self.write('workstreams/worker/STATE.md', self.state(row['status']),
                               '## Goal\nKeep this text.\n## Progress\n- Existing work\n')
                before = p.read_bytes()
                r = self.cli('ws', 'complete', 'worker', '--check', row['check'],
                             '--command', row['command'], '--result', row['result'])
                self.assertEqual(r.returncode, row['exit'], r.stdout + r.stderr)
                if row['exit']:
                    self.assertEqual(p.read_bytes(), before)
                else:
                    fm, body = self.read(p)
                    self.assertEqual((fm['status'], str(fm['updated']), fm['next']), ('done', TODAY, []))
                    self.assertIn('Keep this text.', body)
                    self.assertEqual(fm['completion_evidence'], dict(check=row['check'], command=row['command'],
                                                                    result=row['result'], date=TODAY))
                    saved = p.read_bytes()
                    self.assertEqual(self.cli('ws', 'complete', 'worker', '--check', row['check'],
                                             '--command', row['command'], '--result', row['result']).returncode, 0)
                    self.assertEqual(p.read_bytes(), saved)
                    self.assertEqual(self.cli('--strict', script='lint_facts.py').returncode, 0)

    def test_verification_table(self):
        for row in CASES['verification']:
            with self.subTest(row['id']):
                p = self.write('facts/zebra.md', self.draft(extra={'preserve': ['yes']}), 'Exact claim: café.\n')
                before = p.read_bytes()
                r = self.cli('fact', 'verify', 'zebra', '--source', row['source'])
                self.assertEqual(r.returncode, row['exit'], r.stdout + r.stderr)
                if row['exit']:
                    self.assertEqual(p.read_bytes(), before)
                else:
                    fm, body = self.read(p)
                    self.assertIs(fm['verified'], True)
                    self.assertEqual((str(fm['verified_at']), fm['verify_by']), (TODAY, row['source']))
                    self.assertEqual(fm['extra'], {'preserve': ['yes']})
                    self.assertEqual(body, 'Exact claim: café.\n')
                    saved = p.read_bytes()
                    self.assertEqual(self.cli('fact', 'verify', 'zebra', '--source', row['source']).returncode, 0)
                    self.assertEqual(p.read_bytes(), saved)

    def test_manual_edit_rejected_by_lint(self):
        p = self.write('workstreams/worker/STATE.md', self.state('done'))
        r = self.cli('--strict', script='lint_facts.py')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('completion_evidence', r.stdout)
        for row in CASES['invalid_records']:
            with self.subTest(row['id']):
                p.unlink(missing_ok=True)
                self.write('facts/bad.md', self.draft(**row['changes']))
                r = self.cli('--strict', script='lint_facts.py')
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertNotIn('Traceback', r.stderr)

    def test_legacy_done_retains_compatibility_until_brain_opt_in(self):
        fm = self.state('done'); del fm['record_version']
        self.write('workstreams/worker/STATE.md', fm)
        r = self.cli('--strict', script='lint_facts.py')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        (self.b / 'brain.config.yaml').write_text('require_evidence: true\n')
        r = self.cli('--strict', script='lint_facts.py')
        self.assertEqual(r.returncode, 1)
        self.assertIn('completion_evidence', r.stdout)

    def test_bad_yaml_shapes_and_duplicate_keys_are_diagnostics(self):
        p = self.write('facts/bad.md', self.draft())
        for text in ('---\n- one\n---\nx', '---\na: [oops\n---\nx',
                     p.read_text().replace('record_version: 1', 'record_version: 1\nrecord_version: 1')):
            with self.subTest(text=text):
                p.write_text(text)
                before = p.read_bytes()
                r = self.cli('fact', 'verify', 'bad', '--source', 'test')
                self.assertEqual(r.returncode, 2)
                self.assertEqual(p.read_bytes(), before)
                self.assertNotIn('Traceback', r.stderr)
                self.assertEqual(self.cli('--strict', script='lint_facts.py').returncode, 1)

    def test_confined_writes_and_evidence_is_never_executed(self):
        p = self.write('facts/zebra.md', self.draft())
        before = p.read_bytes()
        for slug in ('../zebra', '/tmp/zebra', 'a/b', 'zebra.md'):
            r = self.cli('fact', 'verify', slug, '--source', 'test')
            self.assertEqual(r.returncode, 2)
            self.assertEqual(p.read_bytes(), before)
        link = self.b / 'facts/link.md'; link.symlink_to(p)
        self.assertEqual(self.cli('fact', 'verify', 'link', '--source', 'test').returncode, 2)
        link.unlink()
        marker = self.b / 'SHOULD_NOT_EXIST'
        source = 'observed $(touch ' + str(marker) + ') `touch ' + str(marker) + '`'
        self.assertEqual(self.cli('fact', 'verify', 'zebra', '--source', source).returncode, 0)
        self.assertFalse(marker.exists())
        self.assertEqual(self.read(p)[0]['verify_by'], source)

    def test_invalid_migration_is_not_laundered(self):
        p = self.write('facts/zebra.md', self.draft(record_version=99))
        before = p.read_bytes()
        self.assertEqual(self.cli('fact', 'verify', 'zebra', '--source', 'test').returncode, 2)
        self.assertEqual(p.read_bytes(), before)
        self.assertEqual(self.cli('ws', 'complete', 'missing', '--check', 'x', '--command', 'x', '--result', 'x').returncode, 2)

    def test_compaction_roundtrips_generated_titles(self):
        for i, title in enumerate(('a: b', '[brackets]', 'café 雪', 'quote "x"', 'plain')):
            (self.b / 'inbox' / f'{i}.md').write_text(f'## [fact] {title}\nUnique claim {i}.\n')
        r = self.cli('compact', '--write')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        facts = list((self.b / 'facts').glob('*.md'))
        self.assertEqual(len(facts), 5)
        for p in facts:
            fm, body = self.read(p)
            self.assertEqual(fm['record_version'], 1)
            self.assertIs(fm['verified'], False)
            self.assertIn('Unique claim', body)
        self.assertEqual(self.cli('--strict', script='lint_facts.py').returncode, 0)

    def test_context_budget_properties_readonly_and_deterministic(self):
        self.write('facts/zebra.md', self.draft(), 'Zebra worker café 雪\n' * 30)
        self.write('facts/known.md', self.draft(verified=True, verified_at=TODAY), 'Zebra known.\n')
        self.write('facts/stale.md', self.draft(verified=True, verified_at='2000-01-01'), 'Zebra stale.\n')
        self.write('facts/broken.md', self.draft(confidence='certain'), 'Zebra broken.\n')
        self.write('workstreams/worker/STATE.md', self.state(), '## Goal\nZebra worker.\n')
        def snapshot():
            return {str(p.relative_to(self.b)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in self.b.rglob('*') if p.is_file()}
        before = snapshot()
        rng = random.Random(7831)
        for budget in [128, 129, 256, 2048, 20000] + [rng.randrange(128, 5000) for _ in range(12)]:
            with self.subTest(budget=budget):
                args = ('context', 'zebra worker', '--budget', str(budget), '--cwd', str(self.b.parent / 'example'))
                a, b = self.cli(*args), self.cli(*args)
                self.assertEqual(a.returncode, 0, a.stdout + a.stderr)
                self.assertEqual(a.stdout, b.stdout)
                self.assertLessEqual(len(a.stdout.encode('utf-8')), budget)
                self.assertIn('omitted:', a.stdout)
        out = self.cli('context', 'zebra', '--budget', '20000', '--cwd', str(self.b.parent / 'example')).stdout
        self.assertIn('[unverified]', out)
        self.assertIn('[verified]', out)
        self.assertIn('[stale]', out)
        self.assertNotIn('Zebra broken.', out)
        self.assertLess(out.index('workstreams/worker/STATE.md'), out.index('facts/'))
        self.assertEqual(snapshot(), before)
        exact = self.cli('context', 'zebra', '--budget', str(len(out.encode('utf-8')) - 1),
                         '--cwd', str(self.b.parent / 'example'))
        self.assertLessEqual(len(exact.stdout.encode('utf-8')), len(out.encode('utf-8')) - 1)
        for budget in ('0', '-1', '1', 'oops'):
            self.assertEqual(self.cli('context', 'zebra', '--budget', budget).returncode, 2)

    def test_context_ignores_symlinked_external_content(self):
        p = Path(self.tmp.name) / 'outside.md'; p.write_text('Zebra PRIVATE_OUTSIDE')
        (self.b / 'facts/leak.md').symlink_to(p)
        r = self.cli('context', 'zebra', '--budget', '20000')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('PRIVATE_OUTSIDE', r.stdout)

    def test_extension_contract_change_and_required_fields(self):
        contract = dict(need='Add a record writer', use='_records.validate', guarantees='Invalid writes refused',
                        boundary='Validate before replacement', enforcement='python -m unittest tests.test_abstractions',
                        example='scripts/compact.py', choices_removed='No ad hoc schemas',
                        change_when='New record requirements differ')
        p = self.write('facts/contracts.md', self.draft(kind='extension-contract', **contract))
        self.assertEqual(self.cli('--strict', script='lint_facts.py').returncode, 0)
        for key in contract:
            fm = self.draft(kind='extension-contract', **{k: v for k, v in contract.items() if k != key})
            self.write('facts/contracts.md', fm)
            r = self.cli('--strict', script='lint_facts.py')
            self.assertEqual(r.returncode, 1, key + r.stdout)
            self.assertIn(key, r.stdout)
        contract['change_when'] = 'Support import provenance'
        self.write('facts/contracts.md', self.draft(kind='extension-contract', **contract))
        self.assertEqual(self.cli('--strict', script='lint_facts.py').returncode, 0)
        self.assertIn('Support import provenance', self.cli('context', 'record writer', '--budget', '20000').stdout)

    def test_atomic_failure_keeps_original_and_removes_temp(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import _records
        p = self.write('facts/zebra.md', self.draft())
        before = p.read_bytes()
        with patch.object(_records.os, 'replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                _records.verify_fact(self.b, 'zebra', 'test')
        self.assertEqual(p.read_bytes(), before)
        self.assertEqual([x.name for x in p.parent.iterdir()], ['zebra.md'])

    def test_versioned_schema_generated_bad_types_are_diagnostics(self):
        bad = {'verified': [None, 0, 'true', [], {}], 'confidence': [None, 2, [], {}],
               'anchors': [True, 'repo@path', {'a': 'b'}, [None]],
               'record_version': [True, '1', [], {}], 'recorded_at': ['2999-01-01', True, [], {}]}
        for field, values in bad.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.write('facts/bad.md', self.draft(**{field: value}))
                    r = self.cli('--strict', script='lint_facts.py')
                    self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                    self.assertNotIn('Traceback', r.stderr)

    def test_new_workstream_uses_shared_schema_and_safe_yaml(self):
        for i, title in enumerate(('a: b', 'line\nnext: injected', 'café 雪')):
            r = self.cli('ws', 'new', f'writer-{i}', title)
            self.assertEqual(r.returncode, 0, r.stderr)
            fm, _ = self.read(self.b / f'workstreams/writer-{i}/STATE.md')
            self.assertEqual(fm['title'], title)
            self.assertEqual(fm['record_version'], 1)
        self.assertEqual(self.cli('--strict', script='lint_facts.py').returncode, 0)

    def test_parse_errors_do_not_echo_sensitive_source_lines(self):
        secret = 'abcdefghijklmnopqrstuvwx012345'
        p = self.b / 'facts/bad.md'
        p.write_text('---\nrecord_version: 1\npassword: [' + secret + '\n---\nclaim\n')
        for r in (self.cli('fact', 'verify', 'bad', '--source', 'test'),
                  self.cli('--strict', script='lint_facts.py')):
            self.assertNotEqual(r.returncode, 0)
            self.assertNotIn(secret, r.stdout + r.stderr)

    def test_creation_writers_reject_symlink_directories(self):
        outside = Path(self.tmp.name) / 'outside'; outside.mkdir()
        for directory in ('facts', 'workstreams'):
            p = self.b / directory
            p.rmdir(); p.symlink_to(outside, target_is_directory=True)
        (self.b / 'inbox/note.md').write_text('## [fact] Zebra\nClaim.\n')
        for r in (self.cli('ws', 'new', 'escape'), self.cli('compact', '--write')):
            self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertEqual(list(outside.iterdir()), [])

    def test_context_respects_brain_completion_gate(self):
        (self.b / 'brain.config.yaml').write_text('require_evidence: true\n')
        fm = self.state('done'); del fm['record_version']
        self.write('workstreams/worker/STATE.md', fm, 'UNATTESTED CLAIM\n')
        r = self.cli('context', 'UNATTESTED', '--budget', '20000')
        self.assertEqual(r.returncode, 0)
        self.assertNotIn('UNATTESTED CLAIM', r.stdout)
        self.assertIn('omitted: 1', r.stdout)

    def test_completion_rejects_malformed_existing_versioned_fields(self):
        for changes in ({'updated': 'bad-date'}, {'updated': '2999-01-01'}, {'next': 'not-a-list'}):
            fm = self.state(); fm.update(changes)
            p = self.write('workstreams/worker/STATE.md', fm)
            before = p.read_bytes()
            r = self.cli('ws', 'complete', 'worker', '--check', 'suite', '--command', 'true', '--result', 'passed')
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertEqual(p.read_bytes(), before)

    def test_legacy_yaml_merge_keys_remain_readable(self):
        p = self.b / 'facts/legacy.md'
        p.write_text('---\ndefaults: &defaults\n  confidence: low\n<<: *defaults\nconfidence: high\n'
                     f'title: Legacy zebra\nverified_at: {TODAY}\nsource: observed\n---\nClaim.\n')
        r = self.cli('--strict', script='lint_facts.py')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.cli('fact', 'verify', 'legacy', '--source', 'observed')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.read(p)[0]['confidence'], 'high')

    def test_legacy_facts_never_receive_a_verified_context_label(self):
        fm = self.draft(verified=True, verified_at=TODAY); del fm['record_version']
        self.write('facts/legacy.md', fm, 'Legacy zebra\n')
        out = self.cli('context', 'zebra', '--budget', '20000').stdout
        self.assertIn('[unverified] facts/legacy.md', out)

    def test_legacy_bad_dates_are_rejected_without_rewriting(self):
        state = self.state(); del state['record_version']; state['updated'] = 'bad-date'
        fact = self.draft(verified=True, verified_at='bad-date'); del fact['record_version']
        for path, fm, args in [('workstreams/worker/STATE.md', state, ('ws', 'complete', 'worker', '--check', 'x', '--command', 'x', '--result', 'x')),
                               ('facts/legacy.md', fact, ('fact', 'verify', 'legacy', '--source', 'test'))]:
            p = self.write(path, fm); before = p.read_bytes()
            r = self.cli(*args)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertEqual(p.read_bytes(), before)

    def test_verification_does_not_fill_invalid_versioned_fields(self):
        for key in ('verified', 'verified_at'):
            fm = self.draft(verified=True, verified_at=TODAY)
            del fm[key]
            p = self.write('facts/bad.md', fm); before = p.read_bytes()
            r = self.cli('fact', 'verify', 'bad', '--source', 'observed')
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertEqual(p.read_bytes(), before)

    def test_context_no_match_malformed_yaml_and_legacy_routing(self):
        self.assertIn('omitted: 0', self.cli('context', 'zzzqxvnonsense', '--budget', '128').stdout)
        (self.b / 'facts/bad.md').write_text('---\nrecord_version: 1\ntitle: [bad\n---\nNEVER_EMIT_THIS\n')
        r = self.cli('context', 'NEVER_EMIT_THIS', '--budget', '128')
        self.assertEqual(r.returncode, 0)
        self.assertIn('omitted: 1', r.stdout)
        self.assertNotIn('NEVER_EMIT_THIS', r.stdout)
        fm = self.state(); del fm['record_version']; del fm['status']; del fm['slug']
        self.write('workstreams/worker/STATE.md', fm, 'LEGACY_CONTEXT_PRIORITY\n')
        out = self.cli('context', 'zzzqxvnonsense', '--budget', '20000', '--cwd', str(self.b.parent / 'example')).stdout
        self.assertIn('LEGACY_CONTEXT_PRIORITY', out)


if __name__ == '__main__':
    unittest.main()
