# Contributing

The bar is the repo's own definition of done (`tests/test_definition_of_done.py` enforces most of it):
1. **Tests first**, from the spec and known gotchas. Pure logic separated from I/O; `main()` exercised end to end in a throwaway `BRAIN_DIR` **and an isolated `HOME`**. Tests must not read user-editable content from the working tree: use `tests/helpers.fixture_brain()`.
2. **Hand-written mutants** in `tests/mutants/<script>.yaml`; `python scripts/mutation_check.py tests/mutants/<script>.yaml` must report all killed, no survivors, no stale. Fix survivors with tests, never by deleting mutants. Equivalent mutants mean the code can be simplified.
3. **An eval question** in `evals/questions.yaml` proving the behaviour is findable; behaviour-changing edits to skills/primer need an eval delta (see the skill, section 7).
4. **Deterministic**: no clock, randomness or network in logic that tests assert on.
5. **Docs**: mention the script in the README table / `docs/integrations.md`; add a CHANGELOG entry; bump `VERSION` and `.claude-plugin/plugin.json` together.

Run everything: `CHECK_TEMPLATE=1 python -m unittest discover -s tests && for f in tests/mutants/*.yaml; do python scripts/mutation_check.py $f || break; done && python scripts/eval_run.py`.
