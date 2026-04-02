from __future__ import annotations
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    ib_host: str = field(default_factory=lambda: os.getenv("IB_HOST", "localhost"))
    ib_port: int = field(default_factory=lambda: int(os.getenv("IB_PORT", "5001")))
    ibkr_mode: str = field(default_factory=lambda: os.getenv("IBKR_MODE", "paper"))
    ib_account: str = field(default_factory=lambda: os.getenv("IB_ACCOUNT", ""))
    ibkr_username: str = field(default_factory=lambda: os.getenv("IBKR_USERNAME", ""))
    ibkr_password: str = field(default_factory=lambda: os.getenv("IBKR_PASSWORD", ""))
    ib_account_paper: str = field(default_factory=lambda: os.getenv("IB_ACCOUNT_PAPER", ""))
    ibkr_username_paper: str = field(default_factory=lambda: os.getenv("IBKR_USERNAME_PAPER", ""))
    ibkr_password_paper: str = field(default_factory=lambda: os.getenv("IBKR_PASSWORD_PAPER", ""))
    benzinga_api_key: str = field(default_factory=lambda: os.getenv("BENZINGA_API_KEY", ""))
    marketaux_api_key: str = field(default_factory=lambda: os.getenv("MARKETAUX_API_KEY", ""))
    massive_api_key: str = field(default_factory=lambda: os.getenv("MASSIVE_API_KEY", ""))
    finnhub_api_key: str = field(default_factory=lambda: os.getenv("FINNHUB_API_KEY", ""))
    alphavantage_api_key: str = field(default_factory=lambda: os.getenv("ALPHAVANTAGE_API_KEY", ""))
    eodhd_api_key: str = field(default_factory=lambda: os.getenv("EODHD_API_KEY", ""))
    max_position_pct: float = field(default_factory=lambda: float(os.getenv("MAX_POSITION_PCT", "0.05")))
    regime_tickers: list = field(
        default_factory=lambda: os.getenv("REGIME_TICKERS", "SPY,QQQ").split(",")
    )
    bear_cash_floor: float = field(
        default_factory=lambda: float(os.getenv("BEAR_CASH_FLOOR", "0.40"))
    )
    caution_cash_floor: float = field(
        default_factory=lambda: float(os.getenv("CAUTION_CASH_FLOOR", "0.25"))
    )
    default_strategy: str = field(default_factory=lambda: os.getenv("DEFAULT_STRATEGY", "rsi"))
    default_broker: str = field(default_factory=lambda: os.getenv("DEFAULT_BROKER", "ibkr-rest"))
    agent_mode: str = field(default_factory=lambda: os.getenv("AGENT_MODE", "supervised"))
    agent_log_path: str = field(default_factory=lambda: os.getenv("AGENT_LOG_PATH", ".trader/logs/agent.jsonl"))
    agent_profile_path: str = field(default_factory=lambda: os.getenv("AGENT_PROFILE_PATH", ".trader/profile.json"))
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    consensus_threshold: int = field(
        default_factory=lambda: int(os.getenv("CONSENSUS_THRESHOLD", "3"))
    )
    watchlist_consensus_threshold: int = field(
        default_factory=lambda: int(os.getenv("WATCHLIST_CONSENSUS_THRESHOLD", "2"))
    )
    discovery_ttl_days: int = field(
        default_factory=lambda: int(os.getenv("DISCOVERY_TTL_DAYS", "14"))
    )
    pipeline_dir: str = field(
        default_factory=lambda: os.getenv("PIPELINE_DIR", ".trader/pipeline")
    )

    @property
    def active_account(self) -> str:
        """Returns the correct account ID based on IBKR_MODE."""
        if self.ibkr_mode == "paper":
            return self.ib_account_paper or self.ib_account
        return self.ib_account

    @property
    def ibkr_rest_base_url(self) -> str:
        return f"https://{self.ib_host}:{self.ib_port}/v1/api"
