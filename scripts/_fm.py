import re, yaml
def frontmatter(path):
    t = open(path, errors="ignore").read()
    m = re.match(r'^---\n(.*?)\n---\n?(.*)', t, re.S)
    if not m: return {}, t
    try:
        fm = yaml.safe_load(m.group(1)) or {}
        if not isinstance(fm, dict): return {"_parse_error": True}, m.group(2)
        return fm, m.group(2)
    except Exception: return {"_parse_error": True}, m.group(2)
