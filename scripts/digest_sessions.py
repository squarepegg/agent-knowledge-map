#!/usr/bin/env python3
"""Compress agent session JSONL (pi, Claude Code, Codex CLI) into small redacted digests for mining learnings into the brain (no LLM).
Dirs: BRAIN_SESSION_GLOBS = os.pathsep-separated "kind=glob" pairs (kind pi|claude|codex); default covers ~/.pi/agent/sessions and ~/.claude/projects."""
import json, glob, os, re, sys, hashlib
OUT = os.path.join(os.environ.get("BRAIN_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "digests")
CAP = 14000
SECRET = re.compile(r'(?i)(token|secret|password|api[_-]?key|authorization|bearer)\S*[=: ]+\S+|eyJ[\w-]{20,}\.[\w-]+\.[\w-]+|AKIA[0-9A-Z]{16}')
def clean(s, n): s = SECRET.sub("[REDACTED]", s or ""); s = re.sub(r'\s+', ' ', s).strip(); return s[:n]
def text_of(c):
    if isinstance(c, str): return c
    if isinstance(c, list): return " ".join(b.get("text","") for b in c if isinstance(b, dict) and b.get("type")=="text")
    return ""
def digest_pi(path):
    lines, cwd, calls = [], "", {}
    for raw in open(path, errors="ignore"):
        try: e = json.loads(raw)
        except: continue
        t = e.get("type")
        if t == "session": cwd = e.get("cwd",""); continue
        if t in ("compaction","branch_summary"): lines.append("SUMMARY: "+clean(e.get("summary"),2500)); continue
        if t != "message": continue
        m = e.get("message",{}); r = m.get("role")
        if r == "user":
            s = clean(text_of(m.get("content")), 700)
            if s and not s.startswith("<"): lines.append("USER: "+s)
        elif r == "assistant":
            for b in m.get("content") or []:
                if b.get("type") == "toolCall":
                    a = b.get("arguments") or {}
                    calls[b.get("id")] = (b.get("name"), clean(a.get("command") or a.get("code") or json.dumps(a), 300))
        elif r == "toolResult":
            name, arg = calls.get(m.get("toolCallId"), (m.get("toolName"), ""))
            out = clean(text_of(m.get("content")), 300)
            err = m.get("isError") or re.search(r'(?i)(error|denied|expired|not found|unauthori[sz]ed|forbidden|timed? ?out|could not|failed|no such)', out[:300] or "")
            if name and name.startswith("mcp") or (name and "__" in name): lines.append(f"MCP {name}: {arg[:150]}")
            if err: lines.append(f"ERR [{name}] {arg} => {out}")
            elif name in ("bash","hypa_shell"): lines.append(f"CMD {arg[:200]}")
    return cwd, lines
def digest_claude(path):
    lines, cwd = [], ""
    for raw in open(path, errors="ignore"):
        try: e = json.loads(raw)
        except: continue
        cwd = e.get("cwd") or cwd
        m = e.get("message") or {}
        if e.get("type") == "user" and isinstance(m.get("content"), str):
            lines.append("USER: "+clean(m["content"],700))
        elif e.get("type") == "summary": lines.append("SUMMARY: "+clean(e.get("summary"),1500))
        for b in (m.get("content") if isinstance(m.get("content"), list) else []):
            if b.get("type")=="tool_use": lines.append(f"CALL {b.get('name')}: "+clean(json.dumps(b.get('input')),200))
            if b.get("type")=="tool_result" and b.get("is_error"): lines.append("ERR "+clean(text_of(b.get("content")) if not isinstance(b.get("content"),str) else b["content"],300))
    return cwd, lines
ERR_RX = re.compile(r'(?i)(error|denied|expired|not found|unauthori[sz]ed|forbidden|timed? ?out|could not|failed|no such)')
def digest_codex(path):
    """Codex CLI rollout JSONL: session_meta.payload.cwd; response_item payloads message(user|assistant) / function_call / function_call_output."""
    lines, cwd, calls = [], "", {}
    for raw in open(path, errors="ignore"):
        try: e = json.loads(raw)
        except Exception: continue
        p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        if e.get("type") == "session_meta": cwd = p.get("cwd") or cwd; continue
        if e.get("type") != "response_item": continue
        t = p.get("type")
        if t == "message" and p.get("role") == "user":
            s_ = clean(" ".join(b.get("text", "") for b in p.get("content") or [] if isinstance(b, dict) and b.get("type") == "input_text"), 700)
            if s_ and not s_.startswith("<"): lines.append("USER: " + s_)
        elif t == "function_call":
            try: a = json.loads(p.get("arguments") or "{}")
            except Exception: a = {}
            cmd = a.get("cmd") or a.get("command") or p.get("arguments") or ""
            calls[p.get("call_id")] = (p.get("name"), clean(cmd if isinstance(cmd, str) else json.dumps(cmd), 300))
        elif t == "function_call_output":
            name, arg = calls.get(p.get("call_id"), (None, ""))
            out = clean(p.get("output") if isinstance(p.get("output"), str) else json.dumps(p.get("output")), 300)
            lines.append(f"ERR [{name}] {arg} => {out}" if ERR_RX.search(out[:300]) else f"CMD {arg[:200]}")
    return cwd, lines
def squash(lines):
    # dedupe consecutive CMDs, keep USER/SUMMARY/ERR priority under cap
    seen, out = set(), []
    for l in lines:
        k = l[:120]
        if k in seen and not l.startswith("USER"): continue
        seen.add(k); out.append(l)
    body = "\n".join(out)
    if len(body) > CAP:
        pri = [l for l in out if l.startswith(("USER","SUMMARY","ERR","MCP"))]
        body = "\n".join(pri)
        if len(body) > CAP: body = body[:CAP//2] + "\n...[trimmed]...\n" + body[-CAP//2:]
    return body
def session_globs(env=None):
    raw = os.environ.get("BRAIN_SESSION_GLOBS") if env is None else env
    if not raw: return [("pi", os.path.expanduser("~/.pi/agent/sessions/*/*.jsonl")), ("claude", os.path.expanduser("~/.claude/projects/*/*.jsonl")), ("codex", os.path.expanduser("~/.codex/sessions/*/*/*/rollout-*.jsonl"))]
    return [tuple(x.split("=", 1)) for x in raw.split(os.pathsep) if "=" in x]
ADAPTERS = {"pi": digest_pi, "claude": digest_claude, "codex": digest_codex}
def main():
    idx = []
    os.makedirs(OUT, exist_ok=True)
    files = [(p, kind) for kind, g in session_globs() for p in glob.glob(g)]
    for p, kind in files:
        cwd, lines = ADAPTERS[kind](p)
        if len([l for l in lines if l.startswith("USER")]) == 0: continue
        body = squash(lines)
        if len(body) < 400: continue
        sid = hashlib.md5(p.encode()).hexdigest()[:8]
        name = f"{kind}-{os.path.basename(p)[:10]}-{sid}.txt"
        open(os.path.join(OUT,name),"w").write(f"# source: {p}\n# cwd: {cwd}\n{body}\n")
        idx.append((name, cwd, len(body)))
    json.dump(idx, open(os.path.join(OUT,"_index.json"),"w"), indent=0)
    print(len(idx), "digests", sum(i[2] for i in idx)//1000, "KB")

if __name__ == "__main__":
    main()
