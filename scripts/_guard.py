"""Shrink guard for catalog writers: refuse to replace a catalog with a much smaller one (partial API/cluster failures
must never silently overwrite good data). Override deliberately with BRAIN_ALLOW_SHRINK=1."""
import json, os, sys

class ShrinkError(RuntimeError):
    pass

def check_shrink(path, new_count, count_fn, label, min_ratio=0.7, min_base=20):
    """Raise ShrinkError if new_count < min_ratio * previous count (when the previous file had >= min_base items)."""
    if os.environ.get("BRAIN_ALLOW_SHRINK") == "1" or not os.path.exists(path):
        return
    try:
        old = count_fn(json.load(open(path)))
    except Exception:
        return  # unreadable/old format: don't block
    if old >= min_base and new_count < min_ratio * old:
        raise ShrinkError(f"{label}: refusing to shrink {old} -> {new_count} (< {int(min_ratio * 100)}% of previous); kept previous {path}. "
                          f"If intended: BRAIN_ALLOW_SHRINK=1")

def write_json_guarded(path, obj, count_fn, label, min_ratio=0.7, min_base=20, **dump_kw):
    """Atomic json write behind the shrink guard. Exits the process with code 3 on a refused shrink."""
    try:
        check_shrink(path, count_fn(obj), count_fn, label, min_ratio, min_base)
    except ShrinkError as e:
        print(f"GUARD: {e}", file=sys.stderr)
        sys.exit(3)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, **({"indent": 1} | dump_kw))
    os.replace(tmp, path)
