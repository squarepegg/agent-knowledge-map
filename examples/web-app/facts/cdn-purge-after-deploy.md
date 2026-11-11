---
title: Purge the CDN for /static after a deploy that changes asset names
repos: [shop-web]
tags: [cdn, deploy, release, blank-page, '404', assets, javascript, missing-file]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
source: 'example content (invented): replace with your own'
---
Assets are fingerprinted, but the HTML shell is cached for 5 minutes, so users can briefly request old asset names that no longer exist (404 on JS). The deploy workflow purges `/index.html` automatically;
if you change the service worker, also purge `/sw.js` by hand: `curl -X POST $CDN_PURGE_URL -d '{"paths":["/sw.js"]}'` (token from the vault).
