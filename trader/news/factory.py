# trader/news/factory.py
from __future__ import annotations
from trader.news.chain import NewsProviderChain
from trader.news.base import NewsProvider


def get_news_provider(config) -> NewsProviderChain:
    """
    Build the news provider chain from config.
    Order: Marketaux → Benzinga
    Providers with empty API keys are skipped.

    Note: MASSIVE_API_KEY is reserved for EOD stock/options data (separate
    module from their news API). Massive news requires an additional paid
    plan per asset class (~$30/month each) — not included here.
    """
    providers: list[NewsProvider] = []

    if getattr(config, "marketaux_api_key", ""):
        from trader.news.marketaux import MarketauxProvider
        providers.append(MarketauxProvider(config.marketaux_api_key))

    if getattr(config, "benzinga_api_key", ""):
        from trader.news.benzinga import BenzingaClient
        providers.append(BenzingaClient(config))

    return NewsProviderChain(providers)
