# trader/news/factory.py
from __future__ import annotations
from trader.news.chain import NewsProviderChain
from trader.news.base import NewsProvider


def get_news_provider(config) -> NewsProviderChain:
    """
    Build the news provider chain from config.
    Order: Marketaux → Benzinga → Massive
    Providers with empty API keys are skipped.
    """
    providers: list[NewsProvider] = []

    if getattr(config, "marketaux_api_key", ""):
        from trader.news.marketaux import MarketauxProvider
        providers.append(MarketauxProvider(config.marketaux_api_key))

    if getattr(config, "benzinga_api_key", ""):
        from trader.news.benzinga import BenzingaClient
        providers.append(BenzingaClient(config))

    if getattr(config, "massive_api_key", ""):
        from trader.news.massive import MassiveProvider
        providers.append(MassiveProvider(config.massive_api_key))

    return NewsProviderChain(providers)
