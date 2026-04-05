from trader.market.ticker_map import YF_TICKER_MAP, resolve_yf_ticker


def test_resolve_known_ucits_etf():
    assert resolve_yf_ticker("CSPX") == "CSPX.L"
    assert resolve_yf_ticker("VUSA") == "VUSA.AS"
    assert resolve_yf_ticker("IWDA") == "IWDA.L"


def test_resolve_case_insensitive():
    assert resolve_yf_ticker("cspx") == "CSPX.L"
    assert resolve_yf_ticker("Vusa") == "VUSA.AS"


def test_resolve_unknown_passthrough():
    assert resolve_yf_ticker("AAPL") == "AAPL"
    assert resolve_yf_ticker("MSFT") == "MSFT"


def test_resolve_eu_defense_tickers():
    assert resolve_yf_ticker("RHM") == "RHM.DE"
    assert resolve_yf_ticker("BA.") == "BA.L"
    assert resolve_yf_ticker("LDO") == "LDO.MI"
    assert resolve_yf_ticker("SAAB-B") == "SAAB-B.ST"
    assert resolve_yf_ticker("ARMR") == "ARMR.L"
    assert resolve_yf_ticker("HO") == "HO.PA"
    assert resolve_yf_ticker("EUDF") == "EUDF.PA"


def test_resolve_precious_metals_etcs():
    assert resolve_yf_ticker("4GLD") == "4GLD.DE"
    assert resolve_yf_ticker("SGLD") == "SGLD.L"
    assert resolve_yf_ticker("PHAG") == "PHAG.L"


def test_resolve_inverse_etfs():
    assert resolve_yf_ticker("XSPD") == "DXS3.DE"
    assert resolve_yf_ticker("XISP") == "XISP.L"
    assert resolve_yf_ticker("DSPX") == "DSPX.L"


def test_ticker_map_is_dict():
    assert isinstance(YF_TICKER_MAP, dict)
    assert len(YF_TICKER_MAP) > 0
