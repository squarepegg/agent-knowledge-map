"""Shared Markdown record boundary. Evidence is an attestation, never executed.

Version 1 is opt-in for existing records; require_evidence in brain.config.yaml
enforces completion evidence even when a manual edit removes the record version.
Writers assume one local writer; replacement is atomic, not a transaction lock.
"""
import datetime
import os
from pathlib import Path
import re
import tempfile

import yaml

STATES = ('active', 'blocked', 'paused', 'done')
CONTRACT = ('need', 'use', 'guarantees', 'boundary', 'enforcement', 'example', 'choices_removed', 'change_when')
SECRET = re.compile(r'AKIA[0-9A-Z]{16}|eyJ[\w-]{20,}\.[\w-]{10,}\.[\w-]+|(?i:(password|secret|api[_-]?key|token)\s*[:=]\s*[\'"]?[A-Za-z0-9/+_-]{16,})')


class RecordError(ValueError):
    pass


class UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node):
    keys = [loader.construct_object(k) for k, _ in node.value]
    if any(not isinstance(k, str) for k in keys) or len(keys) != len(set(keys)):
        raise RecordError('frontmatter keys must be unique strings')
    return loader.construct_mapping(node)


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def parse(text):
    m = re.match(r'^---\n(.*?)^---(?:\n|$)(.*)', text, re.S | re.M)
    if not m:
        raise RecordError('missing Markdown frontmatter')
    try:
        fm = yaml.safe_load(m.group(1))
        if isinstance(fm, dict) and ('record_version' in fm or fm.get('kind') == 'extension-contract'):
            fm = yaml.load(m.group(1), Loader=UniqueLoader)
    except (yaml.YAMLError, TypeError, ValueError) as e:
        # YAML exceptions contain source lines; do not echo potentially secret input.
        raise RecordError('invalid frontmatter (malformed YAML or duplicate keys)') from e
    if fm is None:
        fm = {}
    if not isinstance(fm, dict):
        raise RecordError('frontmatter must be a mapping')
    return fm, m.group(2)


def render(fm, body):
    return '---\n' + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + '---\n' + body


def nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def date(value):
    if isinstance(value, datetime.datetime):
        return None
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(value)):
        return None
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def validate(fm, kind, today=None, require_evidence=False):
    """Return actionable field errors. Unknown extension metadata is preserved."""
    today = today or datetime.date.today()
    errors = []
    version = fm.get('record_version')
    versioned = 'record_version' in fm
    if versioned and (type(version) is not int or version != 1):
        errors.append('record_version must be 1')
    contract = fm.get('kind') == 'extension-contract'
    if versioned or contract:
        for k in ('title',):
            if not nonblank(fm.get(k)):
                errors.append(k + ' must be a nonblank string')
        for k in ('repos', 'tags', 'anchors', 'branches', 'next', 'links'):
            if k in fm and (not isinstance(fm[k], list) or any(not nonblank(v) for v in fm[k])):
                errors.append(k + ' must be a list of nonblank strings')
        keys = ('updated',) if kind == 'workstream' else (('recorded_at',) if fm.get('verified') is False else ('verified_at',))
        for k in set(keys) | ({'verified_at', 'recorded_at'} & set(fm)):
            d = date(fm.get(k))
            if d is None or d > today:
                errors.append(k + ' must be an ISO date no later than today')
        if kind == 'fact':
            if type(fm.get('verified')) is not bool:
                errors.append('verified must be a boolean')
            if fm.get('confidence') not in ('low', 'medium', 'high'):
                errors.append('confidence must be low, medium or high')
            if not (nonblank(fm.get('source')) or nonblank(fm.get('verify_by')) or fm.get('anchors')):
                errors.append('source/verify_by/anchors must record provenance')
        if kind == 'workstream':
            if fm.get('status') not in STATES:
                errors.append('status must be active, blocked, paused or done')
            if not nonblank(fm.get('slug')):
                errors.append('slug must be a nonblank string')
    if kind == 'workstream' and fm.get('status') == 'done' and (versioned or require_evidence):
        ev = fm.get('completion_evidence')
        if not isinstance(ev, dict):
            errors.append('completion_evidence must contain check, command, result and date')
        else:
            for k in ('check', 'command', 'result'):
                if not nonblank(ev.get(k)):
                    errors.append('completion_evidence.' + k + ' must be a nonblank string')
            d = date(ev.get('date'))
            if d is None or d > today:
                errors.append('completion_evidence.date must be an ISO date no later than today')
            if fm.get('next'):
                errors.append('done workstream must have empty next')
    if contract:
        if version != 1:
            errors.append('extension-contract requires record_version: 1')
        for k in CONTRACT:
            if not nonblank(fm.get(k)):
                errors.append(k + ' must be a nonblank string')
    return errors


def contained_file(brain, path):
    """Return a regular file under brain, rejecting symlink components."""
    p = contained_path(brain, path)
    if not p.is_file():
        raise RecordError('record does not exist')
    return p


def contained_path(brain, path):
    """Containment check for existing or not-yet-created record paths."""
    base = Path(brain).absolute()
    root = base.resolve()
    p = Path(path).absolute()
    try:
        parts = p.relative_to(base if p.is_relative_to(base) else root).parts
    except ValueError as e:
        raise RecordError('path must stay inside the brain') from e
    if '..' in parts:
        raise RecordError('path must stay inside the brain')
    p = root.joinpath(*parts)
    cursor = root
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise RecordError('symlink record paths are not supported')
    return p


def evidence_required(brain):
    p = Path(brain) / 'brain.config.yaml'
    if not p.exists():
        return False
    try:
        cfg = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
        value = cfg.get('require_evidence', False)
    except (OSError, AttributeError, yaml.YAMLError) as e:
        raise RecordError('invalid brain.config.yaml') from e
    if type(value) is not bool:
        raise RecordError('require_evidence must be boolean')
    return value


def record_path(brain, kind, slug):
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
        raise RecordError('use a record slug, not a path or filename')
    root = Path(brain).resolve()
    rel = f'facts/{slug}.md' if kind == 'fact' else f'workstreams/{slug}/STATE.md'
    return contained_file(root, root / rel)


def atomic_write(path, text):
    """Validate before calling. A replacement failure retains the original bytes."""
    if SECRET.search(text):
        raise RecordError('refusing secret-like content')
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as f:
            tmp = f.name
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, path.stat().st_mode & 0o777)
        os.replace(tmp, path)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


def _load_for_write(brain, kind, slug):
    p = record_path(brain, kind, slug)
    fm, body = parse(p.read_text(encoding='utf-8'))
    if 'record_version' in fm and (type(fm['record_version']) is not int or fm['record_version'] != 1):
        raise RecordError('unsupported record_version')
    return p, fm, body


def complete_workstream(brain, slug, check, command, result, today=None):
    today = today or datetime.date.today()
    if not all(nonblank(v) for v in (check, command, result)):
        raise RecordError('check, command and result must be nonblank')
    p, fm, body = _load_for_write(brain, 'workstream', slug)
    if fm.get('status') not in STATES:
        raise RecordError('invalid workstream status')
    # Completion may supply missing completion evidence, but not launder bad
    # dates or field types by overwriting them before checking the record.
    errors = [e for e in validate(dict(fm, record_version=1), 'workstream', today)
              if not e.startswith('completion_evidence') and e != 'done workstream must have empty next']
    if errors:
        raise RecordError('; '.join(errors))
    fm.update(record_version=1, status='done', updated=str(today), next=[],
              completion_evidence=dict(check=check, command=command, result=result, date=str(today)))
    errors = validate(fm, 'workstream', today)
    if errors:
        raise RecordError('; '.join(errors))
    atomic_write(p, render(fm, body))
    return p


def verify_fact(brain, slug, source, today=None):
    today = today or datetime.date.today()
    if not nonblank(source):
        raise RecordError('source must be nonblank')
    p, fm, body = _load_for_write(brain, 'fact', slug)
    original = dict(fm, record_version=1)
    # Legacy implicit verification is permitted for explicit migration, while
    # any stored dates must already be valid before the new date replaces them.
    if 'record_version' not in fm:
        original.setdefault('verified', True)
        original.setdefault('verified_at', str(today))
    errors = validate(original, 'fact', today)
    if errors:
        raise RecordError('; '.join(errors))
    fm.update(record_version=1, verified=True, verified_at=str(today), verify_by=source)
    errors = validate(fm, 'fact', today)
    if errors:
        raise RecordError('; '.join(errors))
    atomic_write(p, render(fm, body))
    return p


def glossary_errors(entries, brain):
    """Scoped language structure. Unversioned entries retain legacy behavior.

    The definition is an anchored fact; this validator cannot establish its
    semantic truth or automatically enforce names across a caller's codebase.
    """
    if not isinstance(entries, list):
        return ['glossary must be a list']
    errors, names = [], {}
    for index, entry in enumerate(entries, 1):
        prefix = f'entry {index}: '
        if not isinstance(entry, dict):
            errors.append(prefix + 'must be a mapping')
            continue
        if 'record_version' not in entry:
            continue
        local = []
        if type(entry['record_version']) is not int or entry['record_version'] != 1:
            local.append('record_version must be 1')
        for field in ('term', 'context', 'one_liner', 'definition'):
            if not nonblank(entry.get(field)):
                local.append(field + ' must be a nonblank string')
        if isinstance(entry.get('one_liner'), str) and len(entry['one_liner']) > 140:
            local.append('one_liner must be <=140 characters')
        if entry.get('kind') not in ('system', 'concept', 'env', 'tool', 'team'):
            local.append('kind must be system, concept, env, tool or team')
        for field in ('aliases', 'repos'):
            values = entry.get(field, [])
            if not isinstance(values, list) or any(not nonblank(v) for v in values):
                local.append(field + ' must be a list of nonblank strings')
        if 'core' in entry and type(entry['core']) is not bool:
            local.append('core must be boolean')
        if local:
            errors.extend(prefix + error for error in local)
            continue
        context = entry['context'].strip().casefold()
        for name in [entry['term']] + entry.get('aliases', []):
            key = (context, name.strip().casefold())
            if key in names:
                errors.append(prefix + f'name already used in this context by entry {names[key]}')
            else:
                names[key] = index
        try:
            rel = Path(entry['definition'])
            if len(rel.parts) != 2 or rel.parts[0] != 'facts' or rel.suffix != '.md':
                raise RecordError('definition must reference facts/*.md')
            p = contained_file(brain, Path(brain).absolute() / rel)
            fm, _ = parse(p.read_text(encoding='utf-8'))
            if fm.get('record_version') != 1 or validate(fm, 'fact'):
                raise RecordError('definition must be a valid versioned fact')
            if not nonblank(fm.get('context')) or fm['context'].strip().casefold() != context:
                raise RecordError('definition context must match glossary context')
        except (OSError, UnicodeError, RecordError) as e:
            # Only controlled RecordError messages may contain input diagnostics.
            reason = str(e) if isinstance(e, RecordError) else 'definition cannot be read'
            errors.append(prefix + reason)
    return errors
