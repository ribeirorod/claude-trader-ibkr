from trader.pipeline.models import (
    Candidate, CandidateSet, Proposal, ProposalSet, ProposalOrder,
    ProposalSizing,
)

def test_candidate_creation():
    c = Candidate(
        ticker="AAPL",
        source="watchlist",
        priority="high",
        asset_class="stock",
        sector="Technology",
        scan_sources=[],
        scan_score=0,
    )
    assert c.ticker == "AAPL"
    assert c.priority == "high"

def test_candidate_set_counts():
    cs = CandidateSet(
        run_id="2026-03-26T02:30:00Z",
        regime="bull",
        sectors={
            "Technology": [
                Candidate(ticker="AAPL", source="watchlist", priority="high",
                          asset_class="stock", sector="Technology"),
                Candidate(ticker="CRWD", source="discovery", priority="normal",
                          asset_class="stock", sector="Technology"),
            ]
        },
    )
    assert cs.total_candidates == 2
    assert cs.watchlist_count == 1
    assert cs.discovery_count == 1

def test_proposal_creation():
    order = ProposalOrder(
        side="buy", order_type="bracket", contract_type="stock",
        qty=8, price=142.50, stop_loss=135.80, take_profit=156.00,
    )
    sizing = ProposalSizing(
        atr=4.20, risk_per_share=6.70,
        position_value=1140.00, pct_of_nlv=3.8,
    )
    p = Proposal(
        rank=1, ticker="NVDA", source="watchlist", direction="long",
        consensus=5,
        strategies_agree=["rsi", "macd", "momentum", "pullback", "ma_cross"],
        strategies_disagree=["bnf"],
        conviction="high",
        order=order, sizing=sizing,
        news_context="Beat Q4 estimates",
    )
    assert p.consensus == 5
    assert p.order.side == "buy"

def test_proposal_set_serialization():
    ps = ProposalSet(
        run_id="2026-03-26T02:30:00Z",
        regime="caution",
        available_capital=15000.0,
        sectors={},
    )
    d = ps.model_dump()
    assert d["regime"] == "caution"
    assert d["total_proposals"] == 0
