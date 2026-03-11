#!/usr/bin/env bash
# setup-crons.sh — reads .claude/crons.json and prints registration instructions
# for the portfolio-conductor agent cron schedules.
#
# This script is called by the Claude Code SessionStart hook.
# Its output is injected as a system message, prompting Claude to register
# the cron jobs via CronCreate at the start of every session.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CRONS_FILE="$PROJECT_ROOT/.claude/crons.json"

if [ ! -f "$CRONS_FILE" ]; then
  echo "WARNING: .claude/crons.json not found — portfolio agent crons not registered."
  exit 0
fi

echo "PORTFOLIO AGENT CRONS — REGISTRATION REQUIRED"
echo "=============================================="
echo "The following cron schedules must be registered via CronCreate for the"
echo "autonomous portfolio agent system to run. Please call CronCreate for each:"
echo ""

/opt/homebrew/bin/python3.12 - <<'PYEOF'
import json, sys
from pathlib import Path

crons_path = Path(__file__).parent.parent / ".claude" / "crons.json"
crons = json.loads(crons_path.read_text())

for i, c in enumerate(crons, 1):
    print(f"  [{i}] {c['label']}")
    print(f"      cron:   {c['cron']}")
    print(f"      agent:  {c['agent']}")
    print(f"      slot:   {c['slot']}")
    print()

print("Call CronCreate once for each entry above using the 'prompt' field from")
print(f".claude/crons.json. All 3 are recurring=true.")
PYEOF
