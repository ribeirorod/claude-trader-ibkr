from __future__ import annotations
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    ib_host: str = field(default_factory=lambda: os.getenv("IB_HOST", "127.0.0.1"))
    ib_port: int = field(default_factory=lambda: int(os.getenv("IB_PORT", "5000")))
    ib_account: str = field(default_factory=lambda: os.getenv("IB_ACCOUNT", ""))
    ibkr_username: str = field(default_factory=lambda: os.getenv("IBKR_USERNAME", ""))
    ibkr_password: str = field(default_factory=lambda: os.getenv("IBKR_PASSWORD", ""))
    benzinga_api_key: str = field(default_factory=lambda: os.getenv("BENZINGA_API_KEY", ""))
    max_position_pct: float = field(default_factory=lambda: float(os.getenv("MAX_POSITION_PCT", "0.05")))
    default_strategy: str = field(default_factory=lambda: os.getenv("DEFAULT_STRATEGY", "rsi"))
    default_broker: str = field(default_factory=lambda: os.getenv("DEFAULT_BROKER", "ibkr-rest"))
    agent_mode: str = field(default_factory=lambda: os.getenv("AGENT_MODE", "autonomous"))
    agent_log_path: str = field(default_factory=lambda: os.getenv("AGENT_LOG_PATH", ".trader/logs/agent.jsonl"))
    agent_profile_path: str = field(default_factory=lambda: os.getenv("AGENT_PROFILE_PATH", ".trader/profile.json"))

    @property
    def ibkr_rest_base_url(self) -> str:
        return f"https://{self.ib_host}:{self.ib_port}/v1/api"
