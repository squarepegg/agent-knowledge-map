"""Bounded read-only context using brain.rank and session_start.match.

Whole entries only; the UTF-8 budget includes headers, omission count and newline.
No probes or stored commands execute. Verified means recorded verification, with
date freshness only; anchor drift remains the responsibility of brain lint.
"""
import datetime
from pathlib import Path

import brain
import _records
import session_start


def bundle(brain_dir, query, budget=8000, cwd=None, today=None):
    if type(budget) is not int or budget < 128:
        raise _records.RecordError('budget must be at least 128 UTF-8 bytes')
    today = today or datetime.date.today()
    root = Path(brain_dir).resolve()
    require_evidence = _records.evidence_required(root)
    repo, branch = session_start.git_info(cwd or str(root))
    docs, texts, meta, states = [], {}, {}, []
    invalid = 0
    # Rank only contained files; brain.corpus also serves older unrestricted search.
    files = sorted({p for d in brain.SCAN for p in (root / d).glob('**/*.md')})
    for p in files:
        rel = p.relative_to(root).as_posix()
        if 'processed' in p.relative_to(root).parts:
            continue
        try:
            _records.contained_file(root, p)
            text = p.read_text(encoding='utf-8')
            kind = 'fact' if rel.startswith('facts/') else 'workstream' if p.name == 'STATE.md' else 'prose'
            fm = {}
            if kind != 'prose':
                fm, _ = _records.parse(text)
                if _records.validate(fm, kind, today, require_evidence):
                    raise _records.RecordError('invalid record')
            if _records.SECRET.search(text):
                raise _records.RecordError('secret-like content')
        except (OSError, UnicodeError, _records.RecordError):
            invalid += 1
            continue
        texts[rel] = text
        meta[rel] = (kind, fm)
        docs.extend((rel, i, line.strip()) for i, line in enumerate(text.splitlines(), 1) if line.strip())
        if kind == 'workstream':
            states.append(dict(slug=str(fm.get('slug') or p.parent.name), status=str(fm.get('status') or 'active').lower(),
                               repos=session_start.as_list(fm.get('repos')), branches=session_start.as_list(fm.get('branches')),
                               file=rel))
    matches = session_start.match(states, repo, branch)
    pick = session_start.likely(matches, branch)
    selected = [w['file'] for w in sorted(matches, key=lambda w: (w is not pick, w['file']))]
    terms = brain.query_words(query)
    ranked = brain.rank(docs, terms, limit=len(docs))
    paths = list(dict.fromkeys(selected + [p for p, _, _ in ranked]))
    out = 'Context: complete entries; verification attested; anchor freshness unchecked\n'
    omitted = len(paths) + invalid
    # Reserve worst-case footer length before adding whole records.
    footer_size = len(f'omitted: {omitted}\n'.encode('utf-8'))
    for rel in paths:
        kind, fm = meta[rel]
        trust = 'unverified'
        if kind == 'fact' and fm.get('record_version') == 1 and fm.get('verified') is True and not _records.validate(fm, 'fact', today):
            d = _records.date(fm.get('verified_at'))
            provenance = (_records.nonblank(fm.get('source')) or _records.nonblank(fm.get('verify_by')) or fm.get('anchors'))
            if d is not None and d <= today and provenance:
                trust = 'stale' if (today - d).days > 90 else 'verified'
        entry = f'[{trust}] {rel}\n' + texts[rel].rstrip('\n') + '\n'
        if len((out + entry).encode('utf-8')) + footer_size <= budget:
            out += entry
            omitted -= 1
    return out + f'omitted: {omitted}\n'
