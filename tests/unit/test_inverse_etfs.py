import json
from pathlib import Path
from trader.market.inverse_etfs import find_inverse, load_inverse_map

SAMPLE_MAP = {
    "index_hedges": {
        "SP500": {
            "ticker": "XISX",
            "name": "Xtrackers S&P 500 Inverse Daily Swap UCITS ETF",
            "exchange": "XETRA",
            "leverage": -1,
            "ter": 0.50,
        },
        "NASDAQ100": {
            "ticker": "SQQQ",
            "name": "WisdomTree NASDAQ 100 3x Daily Short",
            "exchange": "LSE",
            "leverage": -3,
            "ter": 0.75,
        },
    },
    "sector_hedges": {
        "technology": {
            "ticker": "SQQQ",
            "name": "WisdomTree NASDAQ 100 3x Daily Short",
            "leverage": -3,
        },
        "semiconductors": {
            "ticker": "XISX",
            "name": "Xtrackers S&P 500 Inverse Daily Swap UCITS ETF",
            "leverage": -1,
        },
    },
    "usage_rules": {
        "max_hold_days": 20,
        "max_portfolio_pct": 10,
        "prefer_1x_over_leveraged": True,
    },
}


def test_find_inverse_sp500_ticker():
    result = find_inverse("CSPX", SAMPLE_MAP)
    assert result == "XISX"


def test_find_inverse_nasdaq_ticker():
    result = find_inverse("EQQQ", SAMPLE_MAP)
    assert result == "SQQQ"


def test_find_inverse_by_sector():
    result = find_inverse("NVDA", SAMPLE_MAP, sector="technology")
    assert result == "SQQQ"


def test_find_inverse_unmapped_ticker():
    result = find_inverse("AAPL", SAMPLE_MAP)
    assert result is None


def test_find_inverse_case_insensitive():
    result = find_inverse("cspx", SAMPLE_MAP)
    assert result == "XISX"


def test_load_inverse_map_from_file(tmp_path):
    f = tmp_path / "inverse_etfs.json"
    f.write_text(json.dumps(SAMPLE_MAP))
    result = load_inverse_map(f)
    assert result["index_hedges"]["SP500"]["ticker"] == "XISX"
    assert result["usage_rules"]["max_portfolio_pct"] == 10


def test_load_inverse_map_missing_file():
    result = load_inverse_map(Path("/nonexistent/inverse_etfs.json"))
    assert result == {}
