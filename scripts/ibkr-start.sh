#!/usr/bin/env bash
# ibkr-start.sh — Start IBKR gateway in a persistent tmux session, then authenticate.
#
# Usage:
#   ./scripts/ibkr-start.sh              # (re)start gateway + authenticate
#   ./scripts/ibkr-start.sh --auth-only  # skip gateway start, just re-authenticate
#
# The gateway runs in tmux session "ibkr-gateway" — closing your terminal
# does NOT kill the gateway process.
#
# On subsequent calls:
#   - If the tmux session already exists, the gateway is NOT restarted.
#   - The Playwright authentication is always run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TMUX_SESSION="ibkr-gateway"
GATEWAY_URL="${IBEAM_GATEWAY_BASE_URL:-https://localhost:5001}"
AUTH_ONLY=false

for arg in "$@"; do
    [[ "$arg" == "--auth-only" ]] && AUTH_ONLY=true
done

# ── Protected processes ───────────────────────────────────────────────────────
# These processes must NEVER be killed by automated scripts.
# ibkr-start.sh will refuse to restart the gateway if any are found running
# under the protected tmux session, and will only perform a soft reauth instead.
PROTECTED_TMUX_SESSIONS=(
    "ibkr-gateway"   # IBKR Client Portal Gateway (ibeam keepalive)
)
PROTECTED_PROCESS_PATTERNS=(
    "ibeam_starter"  # ibeam session manager
    "clientportal"   # IBKR gateway JVM
    "ibkr-gateway"   # generic gateway marker
)

check_protected() {
    # Returns 0 (true) if any protected process or tmux session is active
    for session in "${PROTECTED_TMUX_SESSIONS[@]}"; do
        if tmux has-session -t "$session" 2>/dev/null; then
            echo "  [protected] tmux session '$session' is running."
            return 0
        fi
    done
    for pattern in "${PROTECTED_PROCESS_PATTERNS[@]}"; do
        if pgrep -f "$pattern" > /dev/null 2>&1; then
            echo "  [protected] process matching '$pattern' is running."
            return 0
        fi
    done
    return 1
}

# ── 1. Start gateway in tmux ─────────────────────────────────────────────────

if [[ "$AUTH_ONLY" == "false" ]]; then
    if check_protected; then
        echo "Protected process detected — skipping gateway restart. Running auth-only."
        AUTH_ONLY=true
    elif tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        echo "tmux session '$TMUX_SESSION' already exists — skipping gateway start."
        echo "  Attach with: tmux attach -t $TMUX_SESSION"
    else
        echo "Starting IBKR gateway in tmux session '$TMUX_SESSION'..."
        tmux new-session -d -s "$TMUX_SESSION" -x 220 -y 50
        tmux send-keys -t "$TMUX_SESSION" "cd '$ROOT' && bash scripts/start-gateway.sh" Enter

        echo "Waiting for gateway to become reachable (up to 30s)..."
        for i in $(seq 1 30); do
            if curl -sk --max-time 2 "$GATEWAY_URL/v1/api/iserver/auth/status" > /dev/null 2>&1; then
                echo "Gateway is up."
                break
            fi
            printf "."
            sleep 1
        done
        echo ""
    fi
fi

# ── 2. Authenticate via Playwright ───────────────────────────────────────────

echo "Running Playwright authentication..."
cd "$ROOT"
uv run python scripts/ibkr-reauth.py
echo "Done. Check Telegram for confirmation."
