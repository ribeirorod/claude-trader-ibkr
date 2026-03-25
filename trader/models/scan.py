from __future__ import annotations
from pydantic import BaseModel

class ScanResult(BaseModel):
    symbol: str
    company_name: str = ""
    conid: int | None = None
    listing_exchange: str = ""
    sec_type: str = ""
    column_value: str = ""   # the scan metric value (e.g. "12.5%" for gainers)
    sector: str = ""         # GICS sector e.g. "Technology", "Energy"
    industry: str = ""       # GICS industry e.g. "Semiconductors"
