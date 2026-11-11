---
title: Each Python project uses uv with a project-local virtualenv
repos: [dotfiles]
tags: [python]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
source: 'example content (invented): replace with your own'
---
`uv venv && uv pip install -r requirements.txt` per project; no global `pip install`. Pin the interpreter with `uv python pin 3.12`. If a tool needs a CLI globally use `uv tool install`.
Mixed Homebrew/uv Pythons caused the 'externally managed environment' error; do not fight it, use a venv.
