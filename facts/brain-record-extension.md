---
record_version: 1
kind: extension-contract
title: Add a brain record writer through _records.validate at the shared extension
  boundary
repos:
- agent-knowledge-map
tags:
- record
- writer
- extension
- boundary
- schema
- abstraction
anchors:
- agent-knowledge-map@scripts/_records.py
- agent-knowledge-map@tests/test_abstractions.py
verified: true
recorded_at: '2026-11-15'
confidence: low
scope: team
source: docs/brain-abstractions.md
need: Add a record writer without inventing another schema
use: _records.validate before writing; _records.render for YAML-safe Markdown; _records.atomic_write
  for existing records
guarantees: Shared field validation and atomic replacement of existing records; secret-like
  content refused
boundary: Versioned fact and workstream writers validate before writing; strict lint
  independently checks manual edits
enforcement: python3 -m unittest tests.test_abstractions; tests/test_abstractions.py
  exercises CLI, compaction and lint with invalid records
example: scripts/compact.py draft_fact constructs an unverified fact with _records.validate
  and _records.render
choices_removed: Field types, evidence shape, YAML quoting, and replacement behavior
  are defined once
change_when: New record requirements differ; extend the schema and contract tests
  first, then update writers and this fact
verified_at: '2026-11-15'
verify_by: 'Local contract suite: python3 -m unittest tests.test_abstractions; 19
  tests passed, including CLI/lint/compactor conformance'
---
Single-writer local files. Evidence is a recorded attestation, not proof of truth.
The named suite checks existing writer behavior; it cannot discover every future
writer automatically. Add a conformance case when introducing a new writer.
