#!/usr/bin/env python3
"""Test whether claude-agent-sdk uses Max subscription (keychain) or API key billing."""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Load .env but immediately strip the API key
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))

os.environ.pop("CLAUDECODE", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

print(f"ANTHROPIC_API_KEY set: {'ANTHROPIC_API_KEY' in os.environ}")
print(f"CLAUDE_CODE_OAUTH_TOKEN set: {'CLAUDE_CODE_OAUTH_TOKEN' in os.environ}")
print("Spawning SDK client...\n")

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    TextBlock,
    ResultMessage,
)


async def main():
    options = ClaudeAgentOptions(
        cwd=str(ROOT),
        allowed_tools=[],
        permission_mode="bypassPermissions",
        model="claude-opus-4-6",
        max_turns=1,
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query("Reply with exactly the words: MAX_AUTH_OK")
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print("Response:", block.text)
            elif isinstance(msg, ResultMessage) and msg.result:
                print("Result:", msg.result)


asyncio.run(main())
