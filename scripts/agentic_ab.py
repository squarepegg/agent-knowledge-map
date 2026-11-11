#!/usr/bin/env python3
"""Does the brain actually help? Ask the same questions to a fresh agent twice - WITH the example brain (primer + tools + brain directory) and
WITHOUT it (no primer, no tools, empty directory) - and compare how many answers are correct. The example facts are invented, so a correct answer
without the brain is a guess that happened to match; the difference is the brain's contribution. Costs model tokens: run it on demand.
  agentic_ab.py EXAMPLE [--cmd TEMPLATE] [--style FILE] [--no-baseline] [--only id ...] [--json out.json]
  --style FILE     use FILE as the brain's style.md (test a working-style rule: same questions, different rule)
  --no-baseline    skip the without-brain run (it does not depend on the style); the table then shows only the brain run
TEMPLATE placeholders: {prompt} (shell-quoted), {primer_file} (PRIMER.md of the example brain; an empty file for the baseline),
{tools} (comma list for the brain run, "" for the baseline). Default:
  CLAUDE_CODE_DISABLE_CLAUDE_MDS=1 claude -p {prompt} --model haiku --append-system-prompt "$(cat {primer_file})" --tools {tools}
    --strict-mcp-config --mcp-config '{"mcpServers":{}}' --permission-mode bypassPermissions
  (your own CLAUDE.md and MCP servers would otherwise leak into both runs; an answer that times out - AGENTIC_TIMEOUT seconds, default 300 - counts as empty, so run examples one at a time to avoid load-induced timeouts)
Questions: examples/EXAMPLE/evals/agentic.yaml (graded by agentic_eval.grade: expect groups, forbid, max_words). Exit 0 always; the table is the result."""
import json, os, shlex, shutil, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import agentic_eval, init_brain
import yaml
ROOT = os.path.dirname(HERE)
DEFAULT_CMD = ("CLAUDE_CODE_DISABLE_CLAUDE_MDS=1 claude -p {prompt} --model haiku --append-system-prompt \"$(cat {primer_file})\" --tools {tools} "
               "--strict-mcp-config --mcp-config '{\"mcpServers\":{}}' --permission-mode bypassPermissions")   # no user CLAUDE.md and no MCP tool definitions: only the brain differs
BRAIN_TOOLS = "Bash,Read,Grep,Glob"
SKIP = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "PRIMER.md", "status", ".cache", "metrics")

def build_brain(example, root=ROOT, style=None):
    """A throwaway brain: this repo's code + the example applied + PRIMER.md built. -> directory."""
    d = tempfile.mkdtemp(prefix="agentic-ab-"); b = os.path.join(d, "brain"); shutil.copytree(root, b, ignore=SKIP)
    acts = init_brain.apply_example(b, example)   # raises SystemExit for an unknown example
    if style: shutil.copyfile(style, os.path.join(b, "style.md"))
    r = subprocess.run([sys.executable, os.path.join(b, "scripts", "build_primer.py")], env={**os.environ, "BRAIN_DIR": b}, capture_output=True, text=True)
    if r.returncode: raise SystemExit("primer failed: " + r.stderr)
    return b

def condition(cmd_template, primer_file, tools):
    return cmd_template.replace("{primer_file}", shlex.quote(primer_file)).replace("{tools}", shlex.quote(tools))

def clean_env(brain=None):
    """Environment for the agent process: the inherited one without any brain variables, plus BRAIN_DIR=<this brain> for the with-brain run only
    (an inherited BRAIN_DIR would make the agent read a different brain than the one under test)."""
    env = {k: v for k, v in os.environ.items() if k not in ("BRAIN_DIR", "BRAIN_REPOS_ROOT")}
    if brain: env["BRAIN_DIR"] = brain
    return env

def run_condition(items, cmd, cwd, env=None):
    out = []
    for it in items:
        timeout = int(os.environ.get("AGENTIC_TIMEOUT", 300))
        text = agentic_eval.ask(it["q"], timeout=timeout, cmd=cmd, cwd=cwd, env=env)
        if not text: text = agentic_eval.ask(it["q"], timeout=timeout, cmd=cmd, cwd=cwd, env=env)   # an empty answer is a timeout or a crash, not "I don't know": retry once
        checks, score = agentic_eval.grade(it, text)
        out.append({"id": it["id"], "correct": checks["correct"], "concise": checks["concise"], "empty": not text, "answer": text[:300]})
    return out

def summarize(with_, without):
    n = len(with_); w = sum(r["correct"] for r in with_); wo = sum(r["correct"] for r in without)
    return {"n": n, "with_brain": w, "without_brain": wo, "gain": w - wo, "empty_with": sum(1 for r in with_ if r.get("empty")), "empty_without": sum(1 for r in without if r.get("empty"))}

def main(argv):
    if len(argv) < 2 or argv[1].startswith("--"): print(__doc__); return 2
    example = argv[1]; opt = lambda k: argv[argv.index(k) + 1] if k in argv else None  # noqa: E731
    only = argv[argv.index("--only") + 1:] if "--only" in argv else []; only = [o for o in only if not o.startswith("--")] if only else []
    cmd = opt("--cmd") or os.environ.get("AGENTIC_AB_CMD") or DEFAULT_CMD
    brain = build_brain(example, style=opt("--style")); empty = tempfile.mkdtemp(prefix="agentic-ab-empty-"); nopr = os.path.join(empty, "empty-primer.md"); open(nopr, "w").close()
    items = yaml.safe_load(open(os.path.join(brain, "examples", example, "evals", "agentic.yaml"))) or []
    items = [i for i in items if not only or i["id"] in only]
    with_ = run_condition(items, condition(cmd, os.path.join(brain, "PRIMER.md"), BRAIN_TOOLS), brain, clean_env(brain))
    skip = "--no-baseline" in argv
    without = [{"id": a["id"], "correct": False, "concise": False, "empty": False, "answer": ""} for a in with_] if skip else run_condition(items, condition(cmd, nopr, ""), empty, clean_env())
    for a, b in zip(with_, without): print(f"{a['id']:28} with brain: {'PASS' if a['correct'] else 'FAIL'}" + ("" if skip else f"   without: {'PASS' if b['correct'] else 'FAIL'}"))
    s = summarize(with_, without)
    print(f"{example}: with brain {s['with_brain']}/{s['n']}" + ("" if skip else f", without {s['without_brain']}/{s['n']}, gain {s['gain']:+d}"))
    if s["empty_with"] or s["empty_without"]: print(f"WARNING: {s['empty_with']} empty answer(s) with the brain, {s['empty_without']} without (timeouts or crashes, even after one retry): these numbers are NOT reliable; rerun this example alone")
    if opt("--json"): json.dump({"example": example, "summary": s, "with": with_, "without": without}, open(opt("--json"), "w"), indent=1)
    shutil.rmtree(os.path.dirname(brain), ignore_errors=True); shutil.rmtree(empty, ignore_errors=True)
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
