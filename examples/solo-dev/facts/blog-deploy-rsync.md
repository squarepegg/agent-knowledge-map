---
title: The blog deploys with a build then rsync to the web host
repos: [blog]
tags: [blog, deploy, publish, post, server, deleted-files]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
absolutes_ok: true
source: 'example content (invented): replace with your own'
---
`make deploy` builds the static site and `rsync -az --delete public/ host:/var/www/blog/`. `--delete` removes files not in the build, so never keep hand-uploaded files in that directory.
The feed lives at `/feed.xml`; after a deploy check it validates before announcing a post.
