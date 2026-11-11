---
slug: portfolio-site
title: Rebuild the portfolio site
status: active
repos:
- blog
branches:
- site-rebuild
updated: '2025-01-15'
next:
- Pick the static site generator
- Port the three best posts
links: []
---
## Goal
A fast, accessible portfolio and blog I can update in minutes.

## Context
Current site is a hand-edited theme; builds break on every OS update.

## Progress
- Chose a content structure (posts as Markdown + frontmatter)

## Verification evidence
| check | command | result | date |
|---|---|---|---|
| site builds from clean checkout | `make build` | ok, 1.2s | 2025-01-15 |

## Next steps
1. Pick generator (evaluate two)
2. Port posts
3. Switch DNS

## Open questions
- Keep comments or drop them?

## References
