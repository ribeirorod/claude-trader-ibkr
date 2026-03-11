#!/usr/bin/env bash
# Starts the IBKR Client Portal Gateway and keeps the session alive via ibeam.
#
# Workflow:
#   1. Run this script — it starts the gateway and ibeam keepalive
#   2. Open https://localhost:5001 in your browser and log in (+ 2FA) once
#   3. ibeam detects the live session and sends /tickle pings every ~60s
#   4. If the session drops, ibeam alerts you — just re-authenticate in browser
#
# To enable fully automatic login (no 2FA prompts):
#   Set IBEAM_AUTHENTICATE=True and IBEAM_KEY=<your TOTP base32 secret> in .env

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load env
set -a
source "$ROOT/.env"
set +a

export IBEAM_GATEWAY_DIR="$ROOT/clientportal.gw"

echo "IBKR Client Portal Gateway — session keepalive mode"
echo "  Account      : $IBEAM_ACCOUNT"
echo "  Gateway URL  : $IBEAM_GATEWAY_BASE_URL"
echo "  Auto-login   : ${IBEAM_AUTHENTICATE:-False}"
echo ""
echo "  → Open $IBEAM_GATEWAY_BASE_URL in your browser and log in once."
echo "  → ibeam will keep the session alive from there."
echo ""

IBEAM_STARTER="$ROOT/.venv/lib/python3.10/site-packages/ibeam/ibeam_starter.py"
exec uv run python "$IBEAM_STARTER" -m
