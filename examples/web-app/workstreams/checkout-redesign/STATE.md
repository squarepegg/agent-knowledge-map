---
slug: checkout-redesign
title: Checkout redesign (single-page)
status: active
repos:
- shop-web
- shop-api
branches:
- feat/checkout-*
updated: '2025-01-15'
next:
- Ship the address step behind the flag to 10%
- Add the webkit retry to the new spec
links: []
---
## Goal
Replace the 4-step checkout with a single page; target +3% conversion without raising the payment error rate.

## Context
The API exposes `/v2/checkout/session`; the web client renders steps from it. Flag `checkout_single_page` controls exposure. Expand/contract applies to the `orders` table change.

## Progress
- Session endpoint live in staging
- Address step implemented behind the flag

## Verification evidence
| check | command | result | date |
|---|---|---|---|
| e2e passes on chromium+webkit | `pnpm test:e2e` | 38/38 (1 retry) | 2025-01-15 |

## Next steps
1. Ship address step to 10%
2. Payment step
3. Remove the flag within 30 days of 100%

## Open questions
- Do we keep guest checkout on the first release?

## References
