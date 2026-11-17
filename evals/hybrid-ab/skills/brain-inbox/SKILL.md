---
name: brain
description: Use when starting or resuming a workstream, saving learnings, updating workstream STATE, compacting the brain inbox, checking stale facts (lint), recording decisions, creating topic skills, or promoting personal knowledge to a shared team brain.
---

# Brain inbox (hybrid: commands do the mechanics, you do the judgment)

`$B` = brain root. Never write secrets, tokens or personal data into any brain file.

1. `python3 scripts/brain.py compact` prints the plan: per item a target, `!!` probable duplicate, `~~` same recurring problem.
   If it refuses (`secret-like content`), delete that item from its `inbox/*.md` file (never copy the value anywhere) and re-run.
2. JUDGE the plan. Delete from the inbox file every item not worth keeping (typos, one-offs, trivia).
3. `python3 scripts/brain.py compact --write` creates draft facts/decisions (skips duplicates, never overwrites).
4. JUDGE what the commands cannot do:
   - `!!` duplicate: merge the new detail into the existing file (bump `verified_at`), no new file.
   - capability: add an entry to `capabilities.yaml` (`id, enables, requires, how`).
   - glossary-type term: `glossary.yaml` (`term, kind, one_liner <=140 chars`).
   - workstream: add the item to that `STATE.md` Progress AND a Verification-evidence row (`check | command | result | date`).
   - correction (the user pushed back): the user is the authority. Fix the rejected claim in the file that states it, then add a row to `facts/user-instincts.md` (frontmatter `tags: [instincts]`, template `templates/fact.md`): `- **When** trigger -> **do** action. _Evidence:_ date, what was said. high.`
5. `python3 scripts/brain.py compact --archive`, then `python3 scripts/brain.py lint`; fix until clean.
6. Report counts added / merged / discarded.
