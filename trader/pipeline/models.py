from __future__ import annotations
from pydantic import BaseModel, computed_field


class CandidateNews(BaseModel):
    headline: str
    sentiment: float


class Candidate(BaseModel):
    ticker: str
    source: str = "discovery"          # "watchlist" | "discovery"
    priority: str = "normal"           # "high" | "normal"
    asset_class: str = "stock"         # "stock" | "etf"
    sector: str = ""
    scan_sources: list[str] = []
    scan_score: int = 0
    news: list[CandidateNews] = []


class GeoContext(BaseModel):
    """Geopolitical / macro context surfaced during discovery."""
    severity: str = "none"  # "high" | "medium" | "low" | "none"
    events: list[str] = []
    affected_sectors: list[str] = []
    block_new_longs: bool = False
    hedge_suggested: bool = False


class CandidateSet(BaseModel):
    run_id: str
    regime: str
    sectors: dict[str, list[Candidate]]
    geo_context: GeoContext = GeoContext()

    @computed_field
    @property
    def total_candidates(self) -> int:
        return sum(len(v) for v in self.sectors.values())

    @computed_field
    @property
    def watchlist_count(self) -> int:
        return sum(
            1 for candidates in self.sectors.values()
            for c in candidates if c.source == "watchlist"
        )

    @computed_field
    @property
    def discovery_count(self) -> int:
        return self.total_candidates - self.watchlist_count


class ProposalOrder(BaseModel):
    side: str
    order_type: str
    contract_type: str = "stock"
    qty: int = 0
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    right: str | None = None
    expiry: str | None = None
    strike: float | None = None


class ProposalSizing(BaseModel):
    atr: float
    risk_per_share: float
    position_value: float
    pct_of_nlv: float


class Proposal(BaseModel):
    rank: int
    ticker: str
    source: str = "discovery"
    direction: str
    consensus: int
    strategies_agree: list[str] = []
    strategies_disagree: list[str] = []
    conviction: str = "medium"
    order: ProposalOrder
    sizing: ProposalSizing | None = None
    news_context: str = ""
    sector: str = ""


class SectorProposals(BaseModel):
    summary: str = ""
    proposals: list[Proposal] = []


class ProposalSet(BaseModel):
    run_id: str
    regime: str
    available_capital: float = 0.0
    geo_context: GeoContext = GeoContext()
    sectors: dict[str, SectorProposals] = {}

    @computed_field
    @property
    def total_proposals(self) -> int:
        return sum(len(sp.proposals) for sp in self.sectors.values())
