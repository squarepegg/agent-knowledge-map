#!/usr/bin/env python3
"""Group inbox items that describe the same recurring problem (deterministic, no model).
Average-link agglomerative clustering. Item similarity is the token Jaccard of title + body, counted as 0 unless the items share at least
MIN_SHARED tokens (one shared word such as 'kafka' or 'ci' is a topic, not a problem). Two groups merge while their mean pairwise similarity is at least
THRESHOLD. History of this rule (evals/cluster.yaml): single-link with THRESHOLD=0.1 scored P=1.00 on dev and P=0.71 on heldout (it chained on a single
topic word), MIN_SHARED alone did not fix it (one 'lambda'+'export' false merge), average-link did. Because heldout was looked at while fixing it, the
`blind` split was written after the algorithm was frozen.
Grouping never drops text: compact.py prints and drafts every attempt's own title and body (rationale, outcome) under the shared problem."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import brain

THRESHOLD = 0.08
MIN_SHARED = 2

def words(item):
    return frozenset(t for t in brain.tokens(item["title"] + " " + item["body"]) if len(t) > 2 and t not in brain.STOP)

def similarity(a, b):
    return len(a & b) / len(a | b) if len(a & b) >= MIN_SHARED else 0.0

def cluster(items, threshold=THRESHOLD):
    """-> list of groups, each a sorted list of indexes into `items`; groups ordered by first member."""
    ws = [words(i) for i in items]; groups = [[i] for i in range(len(items))]
    sim = lambda g, h: sum(similarity(ws[a], ws[b]) for a in g for b in h) / (len(g) * len(h))
    while True:
        best, pair = threshold, None
        for x in range(len(groups)):
            for y in range(x + 1, len(groups)):
                s = sim(groups[x], groups[y])
                if s >= best and (pair is None or s > best): best, pair = s, (x, y)
        if pair is None: return sorted((sorted(g) for g in groups), key=lambda g: g[0])
        x, y = pair; groups[x] += groups.pop(y)
