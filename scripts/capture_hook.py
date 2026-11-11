#!/usr/bin/env python3
"""Agent hooks that make learning capture automatic (Claude Code hook protocol: JSON on stdin).
  capture_hook.py stop      Stop hook: once per session, after real work (>= THRESHOLD tool calls) with no `brain.py note` call, block the stop
                            once and ask the agent to record durable learnings (or say nothing to record). Never loops (stop_hook_active, marker).
  capture_hook.py prompt    UserPromptSubmit hook: if the user's message looks like a correction ("that's wrong", "no, actually", ...), append it to the
                            inbox as kind=correction (truncated; skipped if it looks like it contains a secret). Prints nothing.
Env: BRAIN_DIR, CAPTURE_THRESHOLD (default 8)."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import brain
B = os.environ.get("BRAIN_DIR") or os.path.dirname(HERE)
CORRECTION = re.compile(r"\b(that'?s (wrong|not (right|correct|true))|that is (wrong|not (right|correct|true))|you'?re wrong|no[,.]? (that|it)'?s not|this is wrong|incorrect|actually[, ]+(it|that|the|we|you)\b|not what i (asked|meant|said)|i (already )?(told|said)|don'?t (do|use|add) that)", re.I)
MAXLEN = 300

def is_correction(prompt): return bool(CORRECTION.search(prompt or ""))

def count_tools(transcript_text):
    """Tool calls in a Claude Code / pi style JSONL transcript (tool_use / toolCall blocks)."""
    n = 0
    for line in transcript_text.splitlines():
        try: e = json.loads(line)
        except Exception: continue
        m = e.get("message") if isinstance(e.get("message"), dict) else e
        c = m.get("content") if isinstance(m, dict) else None
        if isinstance(c, list): n += sum(1 for b in c if isinstance(b, dict) and b.get("type") in ("tool_use", "toolCall"))
    return n

def should_block(payload, transcript_text, marker_exists, threshold):
    if payload.get("stop_hook_active") or marker_exists: return False
    if "brain.py note" in transcript_text: return False
    return count_tools(transcript_text) >= threshold

REASON = "Before finishing: record any durable learning, gotcha, decision or user correction from this session with `python3 scripts/brain.py note <kind> \"<title>\" \"<body>\"` (never secrets/PII). If there is nothing durable, reply 'nothing to record'."

def stop(payload, brain_dir=None, threshold=None):
    brain_dir = brain_dir or B; threshold = threshold or int(os.environ.get("CAPTURE_THRESHOLD", 8))
    sid = re.sub(r"[^A-Za-z0-9_-]", "", str(payload.get("session_id") or "")) or "unknown"
    marker = os.path.join(brain_dir, ".cache", f"captured-{sid}")
    tp = payload.get("transcript_path"); text = ""
    if tp and os.path.exists(tp): text = open(tp, errors="ignore").read()
    if not should_block(payload, text, os.path.exists(marker), threshold): return None
    os.makedirs(os.path.dirname(marker), exist_ok=True); open(marker, "w").write("1")
    return {"decision": "block", "reason": REASON}

def prompt(payload, brain_dir=None):
    brain_dir = brain_dir or B; text = str(payload.get("prompt") or "")
    if not is_correction(text) or brain.SECRET.search(text): return None
    return brain.note("correction", re.sub(r"\s+", " ", text).strip()[:MAXLEN], "auto-captured from a user message; verify, then fix the claim it rejects", brain=brain_dir)

def main(argv):
    mode = argv[0] if argv else ""
    try: payload = json.load(sys.stdin)
    except Exception: payload = {}
    if mode == "stop":
        out = stop(payload)
        if out: print(json.dumps(out))
    elif mode == "prompt": prompt(payload)
    else: print(__doc__); return 2
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
