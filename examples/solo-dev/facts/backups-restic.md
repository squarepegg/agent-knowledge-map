---
title: Nightly restic backups; test a restore every quarter
repos: [dotfiles]
tags: [backup, restore, verify, drill]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: medium
scope: team
source: 'example content (invented): replace with your own'
---
`restic backup ~/projects ~/Documents` runs from launchd at 02:30 to an off-site bucket. A backup that has not been restored is a hope: each quarter restore one project to a temp dir and diff it.
The restic password is in the password manager, not on disk.
