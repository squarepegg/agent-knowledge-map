---
name: brain
description: Use when starting or resuming a workstream, saving learnings, updating workstream STATE, compacting the brain inbox, checking stale facts (lint), recording decisions, creating topic skills, or promoting personal knowledge to a shared team brain.
---

# Brain inbox (short prose, no compaction tooling: same judgment rules as the hybrid skill)

`$B` = brain root. Never write secrets, tokens or personal data into any brain file.

1. List the inbox with `python3 scripts/brain.py inbox` and read each file. Check each item for probable duplicates with `python3 scripts/brain.py search <keywords>`.
   If an item contains a secret-like value, delete that item from its `inbox/*.md` file (never copy the value anywhere).
2. JUDGE every item. Delete from the inbox file every item not worth keeping (typos, one-offs, trivia).
3. Write new facts to `facts/<slug>.md` (template `templates/fact.md`) and decisions via `python3 scripts/brain.py decision <slug>`.
4. JUDGE the rest:
   - duplicate: merge the new detail into the existing file (bump `verified_at`), no new file.
   - capability: add an entry to `capabilities.yaml` (`id, enables, requires, how`).
   - glossary-type term: `glossary.yaml` (`term, kind, one_liner <=140 chars`).
   - workstream: add the item to that `STATE.md` Progress AND a Verification-evidence row (`check | command | result | date`).
   - correction (the user pushed back): the user is the authority. Fix the rejected claim in the file that states it, then add a row to `facts/user-instincts.md` (frontmatter `tags: [instincts]`, template `templates/fact.md`): `- **When** trigger -> **do** action. _Evidence:_ date, what was said. high.`
5. Move handled inbox files to `inbox/processed/`, then run `python3 scripts/brain.py lint`; fix until clean.
6. Report counts added / merged / discarded.
