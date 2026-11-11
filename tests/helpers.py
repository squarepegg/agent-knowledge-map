"""Shared test helpers. Tests must never depend on user-editable content (config, glossary, facts, workstreams) of the working tree, because a user's
brain is a clone of this repo and edits those files. They use the pristine copies in tests/fixtures/brain instead."""
import os, shutil, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "brain")
IGNORE = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "PRIMER.md", "status", ".cache")

def fixture_brain(full=False):
    """A throwaway brain: shipped code (scripts, skills, templates) + pristine user-content fixtures. full=True also copies tests/evals/docs/CI (for a whole-repo copy)."""
    d = tempfile.mkdtemp()
    parts = ["scripts", "skills", "templates", "examples", "docs"] + (["tests", "evals", ".github", ".claude-plugin", "hooks"] if full else [])
    for n in parts:
        if os.path.exists(os.path.join(ROOT, n)): shutil.copytree(os.path.join(ROOT, n), os.path.join(d, n), ignore=IGNORE)
    if full:
        for n in os.listdir(ROOT):
            p = os.path.join(ROOT, n)
            if os.path.isfile(p) and n not in ("PRIMER.md",): shutil.copy(p, d)
    for n in os.listdir(FIX):
        src, dst = os.path.join(FIX, n), os.path.join(d, n)
        if os.path.isdir(src):
            if os.path.exists(dst): shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else: shutil.copy(src, dst)
    os.makedirs(os.path.join(d, "facts"), exist_ok=True)
    return d


def set_env(testcase, **kw):
    """Set env vars for one test and restore them afterwards (tests must not leak BRAIN_DIR / BRAIN_REPOS_ROOT into each other)."""
    for k, v in kw.items():
        old = os.environ.get(k)
        if v is None: os.environ.pop(k, None)
        else: os.environ[k] = v
        testcase.addCleanup((lambda k=k, old=old: os.environ.__setitem__(k, old) if old is not None else os.environ.pop(k, None)))
