# Trying the hooks in a real Claude Code session

Verified once with Claude Code 2.1.284 (`claude -p`, model haiku): the prompt hook stored the correction in the inbox, the Stop hook blocked once after 9 tool calls (the agent answered "nothing to record"), wrote its per-session marker and did not loop. It needs a logged-in `claude`, so CI cannot run it. To repeat it without touching your real configuration:

```bash
T=$(mktemp -d); cp -r . $T/brain && mkdir $T/proj && for i in 0 1 2 3 4 5 6 7 8; do echo "file $i" > $T/proj/f$i.txt; done
PY="BRAIN_DIR=$T/brain python3 $T/brain/scripts"
cat > $T/settings.json <<JSON
{"hooks": {
  "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "$PY/capture_hook.py prompt"}]}],
  "Stop":             [{"hooks": [{"type": "command", "command": "$PY/capture_hook.py stop"}]}]}}
JSON
cd $T/proj && claude -p "That's wrong. Run cat on f0.txt..f8.txt as nine separate bash calls, then say done." \
  --model haiku --settings $T/settings.json --allowedTools Bash --permission-mode bypassPermissions
ls $T/brain/inbox $T/brain/.cache    # a correction entry and a captured-<session> marker
```
`--settings` layers the hooks on top of your normal settings for that one run, so nothing is installed.
