---
title: Secrets are injected with the 1Password CLI, never stored in files
repos: [dotfiles]
tags: [secrets, api-keys, keys, env, credentials]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
absolutes_ok: true
source: 'example content (invented): replace with your own'
---
Use `op run --env-file=.env.tpl -- <command>` where `.env.tpl` holds `op://vault/item/field` references, not values. `.env` files with real values are in the global gitignore.
If a key is ever committed, rotate it first, then rewrite history.
