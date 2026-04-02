"""Canonical Yahoo Finance ticker map.

Maps short tickers (as stored in watchlists and used throughout the system)
to their yfinance-compatible symbols with exchange suffixes.

This is the single source of truth — do NOT duplicate this map elsewhere.
"""

from __future__ import annotations

YF_TICKER_MAP: dict[str, str] = {
    # --- Core UCITS ETFs ---
    "CSPX": "CSPX.L",
    "VUSA": "VUSA.AS",
    "IWDA": "IWDA.L",
    "SWDA": "SWDA.L",
    "EQQQ": "EQQQ.L",
    "IMEU": "IMEU.L",
    "EMIM": "EMIM.L",
    # --- Commodity / precious metals ETCs ---
    "SGLN": "SGLN.L",
    "PHAU": "PHAU.L",
    "4GLD": "4GLD.DE",
    "SGLD": "SGLD.L",
    "PHAG": "PHAG.L",
    # --- Bond ETFs ---
    "AGGH": "AGGG.L",
    "IBTA": "IBTA.L",
    "IDTL": "IDTL.L",
    # --- Sector / thematic ETFs ---
    "IUES": "IUES.L",
    "XLES": "XLES.L",
    # --- Inverse / short ETFs (UCITS) ---
    "XSPD": "DXS3.DE",
    "XISP": "XISP.L",
    "DSPX": "DSPX.L",
    "XISX": "DBPD.DE",
    "SUK2": "SUK2.L",
    "SEU5": "DXS5.DE",
    "SQQQ": "SQQQ.L",
    # --- European defense / industrials ---
    "RHM": "RHM.DE",
    "BA.": "BA.L",
    "HO": "HO.PA",
    "LDO": "LDO.MI",
    "SAAB-B": "SAAB-B.ST",
    "ARMR": "ARMR.L",
    "EUDF": "EUDF.PA",
}


def resolve_yf_ticker(ticker: str) -> str:
    """Return the yfinance symbol for a ticker.

    Adds exchange suffix for known UCITS ETFs and EU-listed instruments.
    Unknown tickers pass through unchanged.
    """
    return YF_TICKER_MAP.get(ticker.upper(), ticker)
