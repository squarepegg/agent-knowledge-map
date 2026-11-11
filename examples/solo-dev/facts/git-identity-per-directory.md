---
title: Git identity switches by directory using includeIf
repos: [dotfiles]
tags: [git]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
source: 'example content (invented): replace with your own'
---
`~/.gitconfig` includes `~/work/.gitconfig-work` for repos under `~/work/` and the personal identity everywhere else. If a commit shows the wrong email, the repo is outside the expected
directory; fix with `git config user.email` in that repo and amend, or move the repo.
