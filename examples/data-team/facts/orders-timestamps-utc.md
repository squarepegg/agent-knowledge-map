---
title: orders.created_at is UTC but orders.order_date is store-local
repos: [analytics-dbt]
tags: [warehouse, timestamps]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
source: 'example content (invented): replace with your own'
---
`orders.created_at` is stored in UTC. `orders.order_date` is derived in the store's local timezone. Joining or grouping revenue on `order_date` across stores
double-counts or drops orders near midnight UTC. Use `created_at` converted with `convert_timezone('UTC', ...)` for global metrics and `order_date` only for per-store reports.
