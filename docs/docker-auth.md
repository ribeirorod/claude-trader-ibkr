# Docker Authentication

## Claude Agent SDK (OAuth via Max subscription)

The trader container uses `claude_agent_sdk` which spawns `claude` CLI subprocesses.
In Docker, interactive OAuth login doesn't work (headless — no browser). Instead,
pass your OAuth token via the `CLAUDE_CODE_OAUTH_TOKEN` environment variable.

### Setup

1. **Generate a long-lived token** on the host (one-time, interactive):

   ```bash
   claude setup-token
   ```

   This opens a browser, authenticates, and prints a token (`sk-ant-oat01-...`).

2. **Add it to `.env`:**

   ```
   CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...
   ```

3. **Recreate the trader container** (restart won't pick up new env vars):

   ```bash
   docker compose up -d trader
   ```

### How it works

- `__main__.py` strips `ANTHROPIC_API_KEY` from the environment on startup to
  force OAuth (so the Max subscription is used instead of API credits).
- The SDK subprocess inherits `CLAUDE_CODE_OAUTH_TOKEN` from the environment and
  authenticates with it directly — no `~/.claude/.credentials.json` needed.
- The `claude-auth` named volume at `/home/trader/.claude` persists any CLI state
  the SDK writes at runtime.

### Token expiry

OAuth tokens expire periodically (~48h). When the token expires:

1. The agent will return `Not logged in · Please run /login` errors in Telegram.
2. Re-run `claude setup-token` on the host to get a fresh token.
3. Update `CLAUDE_CODE_OAUTH_TOKEN` in `.env` and **recreate** (not restart):
   ```bash
   docker compose up -d trader
   ```
   Note: `docker compose restart` reuses the old env. `up -d` recreates with new values.

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Not logged in · Please run /login` | Token expired or missing | Re-run `claude setup-token`, update `.env`, restart |
| `OAuth error: 500` | Tried `claude login` inside container | Don't — use `CLAUDE_CODE_OAUTH_TOKEN` env var instead |
| Agent works on host but not in Docker | `ANTHROPIC_API_KEY` commented out, no OAuth token set | Add `CLAUDE_CODE_OAUTH_TOKEN` to `.env` |

### Reference

This follows the same pattern as [open-assistant](../../../open-assitant/docker-compose.yaml),
which also uses `CLAUDE_CODE_OAUTH_TOKEN` for headless Docker authentication.

## IBKR Gateway Authentication

The IBKR gateway session is separate — see the `ibkr-healthcheck` cron job and
`scripts/ibkr-reauth.py` (Playwright-based automatic re-authentication).
