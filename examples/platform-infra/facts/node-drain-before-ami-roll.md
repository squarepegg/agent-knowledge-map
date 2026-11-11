---
title: Drain nodes (respecting PDBs) before rolling a node group AMI
repos: [infra-live]
tags: [eks, upgrade]
anchors: []
verified: true
verified_at: '2025-01-15'
confidence: high
scope: team
source: 'example content (invented): replace with your own'
---
Changing the AMI in the node group replaces instances. Cordon and drain first (`kubectl drain --ignore-daemonsets --delete-emptydir-data`) one group at a time. A PodDisruptionBudget with
`minAvailable` equal to the replica count blocks the drain forever; raise replicas or relax the PDB for the window. Roll staging a week ahead of prod.
