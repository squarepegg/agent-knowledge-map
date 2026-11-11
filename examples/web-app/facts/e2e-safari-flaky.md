---
title: Playwright checkout tests are flaky on WebKit; retry once, never skip
repos: [shop-web]
tags: [testing]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: medium
scope: team
absolutes_ok: true
source: 'example content (invented): replace with your own'
---
The checkout spec fails about 1 run in 20 on WebKit because the payment iframe loads slowly. CI retries failed tests once (`retries: 1`). If a test fails twice it is real: fix it, do not add `test.skip`.
Run locally with `pnpm test:e2e --project=webkit --headed` to watch the iframe.
