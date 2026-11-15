---
record_version: 1
title: TERM in CONTEXT
context: CONTEXT
repos: []
tags: []
anchors: []
verified: false
recorded_at: 'DATE'
confidence: low
scope: personal
source: SOURCE
---
## Meaning
Canonical term and a precise definition in this bounded context. List accepted
aliases in glossary.yaml; qualify the context when the same word has other meanings.
## Relationships and invariants
How this concept relates to other named concepts; rules and valid state transitions.
## Symbols and checks
Canonical implementation symbols/paths and the executable check that supports the
definition. Record code anchors in frontmatter so existing lint can flag drift.
## Counterexamples
A plausible interpretation that is wrong in this context, with a test/input that
distinguishes it from the actual behavior. Avoid assertions supported only by names.
## Change when
What new requirement or observed behavior would require revising the model and its
language together. Keep this detail in the fact, not in the generated primer.
