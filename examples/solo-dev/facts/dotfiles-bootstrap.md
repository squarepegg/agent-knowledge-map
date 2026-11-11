---
title: A new Mac is set up with one script from the dotfiles repo
repos: [dotfiles]
tags: [setup, macos, laptop, new-machine, machine, brew]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
source: 'example content (invented): replace with your own'
---
`git clone <dotfiles> ~/dotfiles && ~/dotfiles/bootstrap.sh` installs Homebrew, the Brewfile, shell config and symlinks. On Apple Silicon Homebrew lives in `/opt/homebrew`; the script adds it to PATH,
and forgetting that is why `brew: command not found` appears in the first new shell. Re-running is safe (idempotent).
