#!/usr/bin/env bash
# setup-crons.sh — SessionStart hook + standalone installer.
# Reads .claude/crons.json and registers jobs in the system crontab.
# Jobs run via tmux new-window so they stay attached to a live session.
#
# system agent jobs  → run cmd directly (no claude needed)
# other agent jobs   → run via claude -p --agent <name>
#
# Safe to run multiple times — replaces the VIBE-TRADER block each run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CRONS_FILE="$PROJECT_ROOT/.claude/crons.json"
LOG_DIR="$PROJECT_ROOT/.trader/logs"
CLAUDE_BIN="/opt/homebrew/bin/claude"
TMUX_SESSION="trader"

if [ ! -f "$CRONS_FILE" ]; then
  echo "WARNING: .claude/crons.json not found — skipping cron registration."
  exit 0
fi

mkdir -p "$LOG_DIR"

/opt/homebrew/bin/python3.12 - \
  "$CRONS_FILE" "$PROJECT_ROOT" "$LOG_DIR" "$CLAUDE_BIN" "$TMUX_SESSION" <<'PYEOF'
import json, subprocess, sys, shlex
from pathlib import Path

crons_file, project_root, log_dir, claude_bin, tmux_session = sys.argv[1:]
crons = json.loads(Path(crons_file).read_text())

MARKER_BEGIN = "# VIBE-TRADER-CRONS-BEGIN"
MARKER_END   = "# VIBE-TRADER-CRONS-END"

# --- list existing block ---
result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
existing = result.stdout if result.returncode == 0 else ""

inside = False
existing_jobs = []
for line in existing.splitlines():
    if line.strip() == MARKER_BEGIN:
        inside = True
        continue
    if line.strip() == MARKER_END:
        inside = False
        continue
    if inside and line.startswith("# ["):
        existing_jobs.append(line[3:line.index("]")])

if existing_jobs:
    print(f"Existing crons ({len(existing_jobs)}): {', '.join(existing_jobs)}")
else:
    print("No existing vibe-trader crons found.")

# --- build new cron block ---
# Each job runs in a tmux window so it's long-lived and inspectable.
# Ensure the tmux session exists before sending windows to it.
ensure_session = (
    f"tmux has-session -t {shlex.quote(tmux_session)} 2>/dev/null "
    f"|| tmux new-session -d -s {shlex.quote(tmux_session)}"
)

new_lines = [MARKER_BEGIN]
for c in crons:
    agent   = c.get("agent", "system")
    job_id  = c["id"]
    log     = f"{log_dir}/cron-{job_id}.log"

    if agent == "system":
        inner_cmd = c["cmd"]
    else:
        prompt = c["prompt"].replace("'", "'\\''")  # escape single quotes
        inner_cmd = (
            f"{shlex.quote(claude_bin)} -p --dangerously-skip-permissions "
            f"--agent {shlex.quote(agent)} '{prompt}'"
        )

    # Full job command: enter project dir, run, tee to log
    job_cmd = f"cd {shlex.quote(project_root)} && {inner_cmd} 2>&1 | tee -a {shlex.quote(log)}"

    # Guard: skip if a window with this job's name is already running.
    # tmux windows auto-close when the command exits, so an open window = still running.
    guard = (
        f"tmux list-windows -t {shlex.quote(tmux_session)} -F '#{{window_name}}' 2>/dev/null "
        f"| grep -qx {shlex.quote(job_id)}"
    )

    # Open a new tmux window named by job id; window closes automatically on exit.
    tmux_cmd = (
        f"tmux new-window -t {shlex.quote(tmux_session)}: "
        f"-n {shlex.quote(job_id)} "
        f"{shlex.quote(job_cmd)}"
    )

    cron_entry = f"{c['cron']} {ensure_session} && {{ {guard} || {tmux_cmd}; }}"
    new_lines.append(f"# [{job_id}] {c['label']}")
    new_lines.append(cron_entry)

new_lines.append(MARKER_END)
new_block = "\n".join(new_lines)

# --- strip old block, append new ---
filtered = []
inside = False
for line in existing.splitlines():
    if line.strip() == MARKER_BEGIN:
        inside = True
        continue
    if line.strip() == MARKER_END:
        inside = False
        continue
    if not inside:
        filtered.append(line)

base = "\n".join(filtered).rstrip()
new_crontab = (base + "\n\n" + new_block + "\n") if base else (new_block + "\n")

subprocess.run(["crontab", "-"], input=new_crontab, text=True, check=True)
print(f"Registered {len(crons)} cron jobs → tmux session '{tmux_session}'.")
PYEOF
