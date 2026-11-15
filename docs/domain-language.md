# Shared language anchored in behavior

Use the domain's names consistently within a bounded context. Capture concepts and
their relationships so an agent can reason about the model before reading every
implementation. Check code and tests before claiming actual behavior: vocabulary
can communicate a wrong or stale model just as consistently as a correct one.

## Scoped glossary entries

Legacy entries continue to work. To opt into validation, add:

```yaml
- record_version: 1
  term: Verified
  context: fact-record
  kind: concept
  one_liner: A recorded verification attestation with a date and provenance.
  aliases: [verification attestation]
  definition: facts/brain-record-language.md
  repos: [agent-knowledge-map]
  core: false
```

`kind` is system, concept, env, tool or team. `term`, `context`, `definition` and
`one_liner` are nonblank strings; the summary is at most 140 characters. Aliases
and repos, when present, are lists of nonblank strings; core is a boolean.
Canonical terms and aliases must be unique within a context, ignoring case and
surrounding whitespace. The same word in different contexts is supported.

`definition` references a versioned, valid fact directly under facts/ with matching
context. Absolute/traversal paths and symlink components are rejected. A definition
may remain unverified while being drafted: structural validity is separate from
verification. Use `brain.py fact verify` only after observing its supporting check.

`brain.py lint --strict` enforces the structure, namespace and definition boundary.
The primer qualifies core scoped terms as `Verified [fact-record]`; legacy labels
are unchanged. Mark only essential terms core so the primer remains a small router.
Detailed definitions stay in ordinary indexed facts, available to search and context.
Aliases are searchable text, not semantic query rewriting or automatic imports of
their linked definitions. No new catalog or inference engine is introduced.

## Useful definitions

Use templates/domain-language.md to record meaning, relationships, invariants,
state transitions where applicable, canonical code symbols, source anchors, a
distinguishing executable check, a counterexample and a revision trigger. References
connect the model to implementation evidence; a path by itself is not proof.

The existing code provides a concrete two-context example:

| Term and context | Meaning | Distinguishing case |
|---|---|---|
| Verified / fact-record | An attestation stored with provenance and date | An old attestation can still be a valid record. |
| Verified / context-bundle | A freshness-qualified presentation label | The same old record is presented as stale after 90 days. |

facts/brain-record-language.md and facts/brain-context-language.md link the meanings
to actual validators and context code. tests/test_domain_language.py exercises the
counterexample against those implementations. Findability evals measure whether
the definitions are retrievable; they do not measure an agent's semantic reasoning
or token efficiency. Naming lint across an arbitrary project's codebase requires
that project's own conventions and checks; this feature does not infer them.
