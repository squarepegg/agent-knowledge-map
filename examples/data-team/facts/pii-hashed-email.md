---
title: Email is only available hashed; raw email lives in the restricted schema
repos: [analytics-dbt]
tags: [pii, security, join, identity, customer, privacy]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
absolutes_ok: true
source: 'example content (invented): replace with your own'
---
Use `email_hash` (salted SHA-256, salt rotated yearly) for joins and counts. Raw email exists only in schema `restricted`; queries there are audited and need a ticket reference in the query comment.
Never paste raw values into the brain, tickets or chat. Exports containing `restricted` columns need approval from the data protection lead.
