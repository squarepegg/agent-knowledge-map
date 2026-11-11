#!/usr/bin/env python3
"""Automatic AST mutation scoring + ratchet, for scripts that have no hand-written mutants yet (tests/mutants/GRANDFATHERED.txt).
Hand-written mutants (scripts/mutation_check.py) stay the bar for new products; this measures how well the existing tests really
constrain each legacy script and refuses regressions:
  auto_mutate.py scripts/foo.py [--max 30] [--seed 1] [--jobs 4]     score one script, list surviving mutants
  auto_mutate.py --update [scripts/x.py ...]                         score every GRANDFATHERED script (or just the named ones, keeping the rest), write tests/mutants/legacy_scores.json
  auto_mutate.py --check [scripts/x.py ...]                          re-score, exit 1 if any script scores below its recorded score - tolerance
Mutation operators: comparison swaps, and/or, + / -, True/False, int+1, `not` removal, if-negation, return value -> None.
Docstrings, plain strings and `if __name__ == "__main__"` blocks are never mutated."""
import ast, concurrent.futures, json, os, random, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutation_check as mc

CMP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.LtE: ast.Gt, ast.Gt: ast.LtE, ast.GtE: ast.Lt, ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is}
TOLERANCE = 0.05


def _is_main_guard(n):
    return isinstance(n, ast.If) and isinstance(n.test, ast.Compare) and isinstance(n.test.left, ast.Name) and n.test.left.id == "__name__"


class _Walk(ast.NodeVisitor):
    """Enumerates mutation candidates in a deterministic order; when `target` is set, applies that one mutation in place."""
    def __init__(self, target=None):
        self.n = 0; self.target = target; self.found = []; self.skip = set()

    def hit(self, kind, node, apply):
        if self.target == self.n: apply()
        self.found.append((kind, getattr(node, "lineno", 0))); self.n += 1

    def generic_visit(self, node):
        if _is_main_guard(node): return
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant): return   # docstrings / bare strings
        super().generic_visit(node)

    def visit_Compare(self, node):
        if len(node.ops) == 1 and type(node.ops[0]) in CMP:
            old = type(node.ops[0]); self.hit(f"cmp:{old.__name__}->{CMP[old].__name__}", node, lambda: node.ops.__setitem__(0, CMP[old]()))
        for x in [node.left, *node.comparators]: self.int_hit(x)
        self.generic_visit(node)

    def visit_BoolOp(self, node):
        a, b = (ast.And, ast.Or) if isinstance(node.op, ast.And) else (ast.Or, ast.And)
        self.hit(f"bool:{a.__name__}->{b.__name__}", node, lambda: setattr(node, "op", b()))
        self.generic_visit(node)

    def visit_BinOp(self, node):
        if isinstance(node.op, (ast.Add, ast.Sub)):
            a, b = (ast.Add, ast.Sub) if isinstance(node.op, ast.Add) else (ast.Sub, ast.Add)
            self.hit(f"bin:{a.__name__}->{b.__name__}", node, lambda: setattr(node, "op", b()))
        for x in (node.left, node.right): self.int_hit(x)
        self.generic_visit(node)

    def visit_UnaryOp(self, node):
        if isinstance(node.op, ast.Not): self.hit("not:remove", node, lambda: self._replace(node, node.operand))
        self.generic_visit(node)

    def _replace(self, node, new):
        node.__class__ = new.__class__; node.__dict__.clear(); node.__dict__.update(new.__dict__)

    def visit_If(self, node):
        if not _is_main_guard(node):
            self.hit("if:negate", node, lambda: setattr(node, "test", ast.copy_location(ast.UnaryOp(op=ast.Not(), operand=node.test), node.test)))
        self.generic_visit(node)

    def visit_IfExp(self, node):
        self.generic_visit(node)

    def visit_Return(self, node):
        if node.value is not None and not (isinstance(node.value, ast.Constant) and node.value.value is None):
            self.hit("ret:None", node, lambda: setattr(node, "value", ast.copy_location(ast.Constant(value=None), node.value)))
            self.int_hit(node.value)
        self.generic_visit(node)

    def int_hit(self, node):
        """Ints only where they carry logic (comparison/arithmetic operands, returned values, += values); elsewhere they are timeouts, indexes, sys.path slots."""
        if isinstance(node, ast.Constant) and type(node.value) is int:
            v = node.value; self.hit("const:int+1", node, lambda: setattr(node, "value", v + 1))

    def visit_AugAssign(self, node):
        self.int_hit(node.value); self.generic_visit(node)

    def visit_Constant(self, node):
        v = node.value
        if v is True: self.hit("const:True->False", node, lambda: setattr(node, "value", False))
        elif v is False: self.hit("const:False->True", node, lambda: setattr(node, "value", True))


def candidates(src):
    w = _Walk(); w.visit(ast.parse(src)); return w.found


def apply_mutation(src, idx):
    tree = ast.parse(src); w = _Walk(target=idx); w.visit(tree)
    if idx >= w.n: raise IndexError(f"mutation {idx} out of range ({w.n})")
    return ast.unparse(tree)


def pick(total, n, seed):
    return sorted(random.Random(seed).sample(range(total), n)) if total > n else list(range(total))


CONTRACT_TESTS = {"test_contracts_safety.py"}   # mention every script by name but test repo structure, not behaviour


def test_modules(root, stem):
    out = []
    d = os.path.join(root, "tests")
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not (f.startswith("test_") and f.endswith(".py")) or f in CONTRACT_TESTS: continue
        with open(os.path.join(d, f)) as fh: text = fh.read()
        if re.search(rf"\b{re.escape(stem)}\b", text): out.append("tests." + f[:-3])
    return out


def score(target, max_mutants=30, seed=1, jobs=4):
    root = mc.ROOT; stem = os.path.splitext(os.path.basename(target))[0]
    mods = test_modules(root, stem); base = {"script": target, "tests": mods, "seed": seed, "total": 0, "killed": 0, "score": 0.0, "survivors": [], "note": ""}
    if not mods: return {**base, "note": "no test module references this script"}
    src = open(os.path.join(root, target)).read(); cmd = [sys.executable, "-W", "ignore", "-m", "unittest", *mods]
    ok, out = mc.run_copy(src, target, cmd)
    if not ok: return {**base, "score": None, "note": f"baseline fails in a clean copy: {out[-300:]}"}
    cand = candidates(src); chosen = pick(len(cand), max_mutants, seed)
    def run(i):
        try: return not mc.run_copy(apply_mutation(src, i), target, cmd)[0]
        except Exception: return True   # a mutant that cannot even run counts as killed
    with concurrent.futures.ThreadPoolExecutor(max(1, jobs)) as ex: res = list(ex.map(run, chosen))
    surv = [{"line": cand[i][1], "op": cand[i][0]} for i, k in zip(chosen, res) if not k]
    killed = sum(res)
    return {**base, "total": len(chosen), "killed": killed, "score": round(killed / len(chosen), 3) if chosen else 0.0, "survivors": surv}


def regressions(recorded, now, tolerance=TOLERANCE):
    bad = []
    for k, v in now.items():
        r = recorded.get(k)
        if r is None: continue
        if v.get("score") is None: bad.append((k, r["score"], None, v.get("note", "no score")))
        elif v["score"] < r["score"] - tolerance - 1e-9: bad.append((k, r["score"], v["score"], "score dropped"))
    return bad


def grandfathered(root):
    p = os.path.join(root, "tests", "mutants", "GRANDFATHERED.txt")
    return [l.strip() for l in open(p) if l.strip() and not l.startswith("#")] if os.path.exists(p) else []


def main(argv):
    a = argv[1:]; opt = lambda name, d: int(a[a.index(name) + 1]) if name in a else d  # noqa: E731
    mx, seed, jobs = opt("--max", 30), opt("--seed", 1), opt("--jobs", 4)
    root = mc.ROOT; rec_path = os.path.join(root, "tests", "mutants", "legacy_scores.json")
    if "--update" in a or "--check" in a:
        if "--check" in a and not os.path.exists(rec_path): print("no tests/mutants/legacy_scores.json: run --update first"); return 2
        explicit = [x for x in a if x.startswith(("scripts/", "skills/")) and x.endswith(".py")]
        scripts = explicit or grandfathered(root); now = {}
        for s in scripts:
            r = score(s, mx, seed, jobs); now[s] = {k: r[k] for k in ("score", "total", "killed", "tests", "note") if k in r}; now[s]["survivors"] = r["survivors"][:15]
            shown = "ERR" if r["score"] is None else f"{r['score']:.0%}"; print(f"{s}: {shown} ({r['killed']}/{r['total']}) {r['note'][:80]}", flush=True)
        if "--update" in a:
            merged = json.load(open(rec_path))["scripts"] if explicit and os.path.exists(rec_path) else {}   # partial update keeps the other scripts' scores
            json.dump({"seed": seed, "max": mx, "scripts": {**merged, **now}}, open(rec_path, "w"), indent=1); print(f"wrote {rec_path}"); return 0
        bad = regressions(json.load(open(rec_path))["scripts"], now)
        for k, was, nowv, why in bad: print(f"REGRESSION {k}: {was} -> {nowv} ({why})")
        return 1 if bad else 0
    targets = [x for x in a if not x.startswith("--") and not x.isdigit()]
    for t in targets:
        r = score(t, mx, seed, jobs); print(json.dumps({k: r[k] for k in ("script", "tests", "total", "killed", "score", "note")}))
        for s in r["survivors"]: print(f"  survivor line {s['line']}: {s['op']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
