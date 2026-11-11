---
title: Mobile events can arrive up to 72 hours late; rollups finalise at T+3
repos: [analytics-dbt]
tags: [events, warehouse]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: medium
scope: team
source: example content (invented); confirmed in the 2024 event-pipeline review
---
Clients batch events and flush on reconnect, so day D keeps growing until about D+3. Daily rollups are re-computed for D-1..D-3 every run. Do not alert on a D-1 volume drop
before 10:00 UTC, and quote D-4 or older when a number must be final. Dashboards show a "provisional" badge for the last 3 days.
