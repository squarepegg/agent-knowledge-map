---
record_version: 1
title: Verified and stale labels in the context-bundle context
context: context-bundle
repos:
- agent-knowledge-map
tags:
- context
- bundle
- verified
- stale
- freshness
- domain
- language
anchors:
- agent-knowledge-map@scripts/_context.py
- agent-knowledge-map@tests/test_domain_language.py
verified: true
recorded_at: '2026-11-15'
confidence: low
scope: team
source: scripts/_context.py bundle; tests/test_domain_language.py
verified_at: '2026-11-15'
verify_by: Observed scripts/_context.py; python3 -m unittest tests.test_domain_language
  passes old-versus-current verification label cases
---
## Meaning
In a context-bundle, [verified] is a presentation label for a valid versioned fact
with explicit verified: true, provenance and a verification date no older than
90 days. This label describes recorded verification and age, not semantic truth.
## Relationships and invariants
The label depends on the fact-record attestation plus the current date. Older
explicitly verified facts are [stale]; legacy and other prose are [unverified].
An anchor change is not part of this label calculation: anchor freshness is unchecked
by context retrieval and is assessed separately by lint.
## Symbols and checks
scripts/_context.py: bundle. Run python3 -m unittest tests.test_domain_language.DomainLanguage.test_record_verification_does_not_imply_context_verified.
## Counterexamples
verified: true in a fact-record does not imply [verified] in a context-bundle:
an old verification date yields [stale]. Conversely, [verified] does not establish
that anchored code is unchanged; inspect lint and the actual code/test evidence.
## Change when
Revise this definition and its check if the 90-day threshold, legacy treatment or
anchor-freshness policy changes. A consistent label must track implemented behavior.
