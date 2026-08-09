#!/usr/bin/env bash
# Print the summaries ADK wrote for a session.
#
#     ./show-compaction.sh                 the session you used most recently
#     ./show-compaction.sh two-days-ago    a named one
#
# Compaction records live in an event's `actions.compaction`, not in its
# message content — so the dev UI, which renders events by their content, has
# nothing to show for them. This reads them out of the API instead.
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a

AGENT="${AGENT_URL:-http://127.0.0.1:8000}"
APP="${TRIGGER_APP:-concert}"
USER_ID="user"          # adk web addresses everything as this

if ! curl -sf -m 5 "$AGENT/list-apps" >/dev/null 2>&1; then
  echo "✗ nothing answering at $AGENT — is adk web running in terminal 2?"
  exit 1
fi

if [ $# -ge 1 ]; then
  SESSION="$1"
else
  SESSION=$(curl -s "$AGENT/apps/$APP/users/$USER_ID/sessions" \
    | .venv/bin/python -c "
import sys, json
rows = json.load(sys.stdin)
if not rows: raise SystemExit('')
rows.sort(key=lambda s: s.get('lastUpdateTime', 0))
print(rows[-1]['id'])")
  [ -z "$SESSION" ] && { echo "✗ no sessions yet — go and talk to the agent first"; exit 1; }
fi

echo "→ session $SESSION"
echo ""

curl -s "$AGENT/apps/$APP/users/$USER_ID/sessions/$SESSION" | .venv/bin/python -c "
import sys, json, textwrap

events = json.load(sys.stdin)['events']
found = [e for e in events if (e.get('actions') or {}).get('compaction')]

print(f'  {len(events)} events, {len(found)} compaction summar' + ('y' if len(found)==1 else 'ies'))
print()

if not found:
    print('  Nothing compacted yet. compaction_interval=3, so keep talking —')
    print('  three more turns and ADK will write one.')
    raise SystemExit

for i, e in enumerate(found, 1):
    c = e['actions']['compaction']
    text = (c.get('compactedContent') or {}).get('parts', [{}])[0].get('text', '')
    print(f'  ── summary {i} ' + '─' * 56)
    for line in text.strip().splitlines():
        print(textwrap.fill(line, 74, initial_indent='  ', subsequent_indent='  '))
    print()
"
