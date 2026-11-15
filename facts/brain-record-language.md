---
record_version: 1
title: Verification attestation in the fact-record context
context: fact-record
repos:
- agent-knowledge-map
tags:
- verification
- attestation
- verified
- domain
- language
- meaning
anchors:
- agent-knowledge-map@scripts/_records.py
- agent-knowledge-map@tests/test_domain_language.py
verified: true
recorded_at: '2026-11-15'
confidence: low
scope: team
source: scripts/_records.py verify_fact; tests/test_domain_language.py
verified_at: '2026-11-15'
verify_by: Observed scripts/_records.py and scripts/_context.py; python3 -m unittest
  tests.test_domain_language passes the distinguishing counterexample
---
## Meaning
In a fact-record, verified: true records a verification attestation with a date
and provenance; it does not establish truth. The verify command stores an observation
without executing the source text or evaluating the claim's semantics.
## Relationships and invariants
verified_at dates the attestation; verify_by records its provenance. Confidence is
a separate field. Record validity and current presentation freshness are different
predicates: a well-formed, old verified fact remains a valid fact record.
## Symbols and checks
scripts/_records.py: verify_fact and validate.
Run python3 -m unittest tests.test_domain_language.DomainLanguage.test_record_verification_does_not_imply_context_verified.
## Counterexamples
A fact with verified: true and an old verified_at date can be valid while the context
bundle presents it as [stale]. A recorded attestation alone does not establish whether
the implementation follows the stated model; inspect the anchored check.
## Change when
If verification becomes automatically executed or the provenance schema changes,
revise this definition, the glossary entry and the distinguishing check together.
