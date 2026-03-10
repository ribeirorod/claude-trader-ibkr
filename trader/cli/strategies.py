from __future__ import annotations
import asyncio, json
import click
import pandas as pd
import yfinance as yf
from trader.strategies.factory import get_strategy, list_strategies
from trader.strategies.optimizer import Optimizer
from trader.strategies.risk_filter import RiskFilter
from trader.news.benzinga import BenzingaClient
from trader.news.sentiment import SentimentScorer
from trader.cli.__main__ import output_json

@click.group()
def strategies():
    """Strategy signals, backtesting, and parameter optimization."""

def _fetch_ohlcv(ticker: str, interval: str, lookback: str) -> pd.DataFrame:
    df = yf.download(ticker, period=lookback, interval=interval, progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [c.lower() for c in df.columns]
    return df

@strategies.command("run")
@click.argument("ticker")
@click.option("--strategy", default="rsi",
              type=click.Choice(list_strategies()),
              help="Strategy name.")
@click.option("--interval", default="1d", help="Bar interval: 1m, 5m, 1h, 1d.")
@click.option("--lookback", default="90d", help="History window e.g. 30d, 90d, 1y.")
@click.option("--params", default=None,
              help='Override strategy params as JSON e.g. \'{"period":14}\'')
@click.pass_context
def run_strategy(ctx, ticker, strategy, interval, lookback, params):
    """
    Run a strategy on TICKER and return full signal series.

    Example: trader strategies run AAPL --strategy rsi --lookback 90d
    """
    p = json.loads(params) if params else None
    strat = get_strategy(strategy, p)
    df = _fetch_ohlcv(ticker, interval, lookback)
    signals = strat.signals(df)
    output_json({
        "ticker": ticker, "strategy": strategy,
        "signals": signals.tolist(),
        "dates": [str(d) for d in signals.index],
        "latest_signal": int(signals.iloc[-1]),
    })

@strategies.command()
@click.option("--tickers", required=True,
              help="Comma or space-separated tickers e.g. AAPL,MSFT.")
@click.option("--strategy", default="rsi",
              type=click.Choice(list_strategies()),
              help="Strategy: rsi, macd, ma_cross, bnf.")
@click.option("--interval", default="1d", help="Bar interval: 1m, 5m, 1h, 1d.")
@click.option("--lookback", default="90d", help="History window e.g. 30d, 90d, 1y.")
@click.option("--with-news", is_flag=True, default=False,
              help="Apply Benzinga sentiment as signal filter. Requires BENZINGA_API_KEY.")
@click.option("--params", default=None,
              help='JSON strategy params e.g. \'{"period":14}\'')
@click.pass_context
def signals(ctx, tickers, strategy, interval, lookback, with_news, params):
    """
    Generate trading signals for one or more tickers.

    Returns signal 1 (buy), -1 (sell), 0 (hold) per ticker.
    Includes risk filter metadata (filtered, filter_reason).

    Example: trader strategies signals --tickers AAPL,MSFT --strategy rsi --with-news
    """
    ticker_list = [t.strip() for t in tickers.replace(",", " ").split()]
    p = json.loads(params) if params else None
    strat = get_strategy(strategy, p)
    rf = RiskFilter()
    results = []

    async def get_sentiments():
        if not with_news:
            return {}
        client = BenzingaClient(ctx.obj["config"])
        scorer = SentimentScorer()
        try:
            items = await client.get_news(ticker_list, limit=20)
        finally:
            await client.aclose()
        sents = {}
        for ticker in ticker_list:
            ticker_items = [i for i in items if i.ticker == ticker]
            sents[ticker] = scorer.score(ticker, ticker_items)
        return sents

    sentiments = asyncio.get_event_loop().run_until_complete(get_sentiments())

    for ticker in ticker_list:
        try:
            df = _fetch_ohlcv(ticker, interval, lookback)
            sig_series = strat.signals(df)
            raw_signal = int(sig_series.iloc[-1])
            sentiment = sentiments.get(ticker)
            filtered = rf.filter(signal=raw_signal, quote=None,
                                  position=None, sentiment=sentiment)
            results.append({
                "ticker": ticker,
                "signal": filtered["signal"],
                "signal_label": {1: "buy", -1: "sell", 0: "hold"}[filtered["signal"]],
                "strategy": strategy,
                "filtered": filtered["filtered"],
                "filter_reason": filtered["filter_reason"],
                "sentiment_score": sentiment.score if sentiment else None,
            })
        except Exception as e:
            results.append({"ticker": ticker, "error": str(e)})

    output_json(results)

@strategies.command()
@click.argument("ticker")
@click.option("--strategy", default="rsi", type=click.Choice(list_strategies()))
@click.option("--from", "from_date", default="2025-01-01",
              help="Backtest start date YYYY-MM-DD.")
@click.option("--params", default=None)
@click.pass_context
def backtest(ctx, ticker, strategy, from_date, params):
    """
    Backtest STRATEGY on TICKER from FROM date.

    Returns total return %, sharpe ratio, win rate, and trade count.
    Example: trader strategies backtest AAPL --strategy rsi --from 2025-01-01
    """
    import numpy as np
    p = json.loads(params) if params else None
    strat = get_strategy(strategy, p)
    df = yf.download(ticker, start=from_date, progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [c.lower() for c in df.columns]
    sigs = strat.signals(df)
    returns = df["close"].pct_change() * sigs.shift(1)
    sharpe = float(returns.mean() / returns.std() * np.sqrt(252)) if returns.std() else 0.0
    output_json({
        "ticker": ticker, "strategy": strategy, "from": from_date,
        "total_return_pct": round(float(returns.sum() * 100), 2),
        "sharpe": round(sharpe, 3),
        "win_rate": round(float((returns[sigs.shift(1) != 0] > 0).mean()), 3),
        "num_trades": int((sigs.diff().abs() > 0).sum()),
    })

@strategies.command()
@click.argument("ticker")
@click.option("--strategy", default="rsi", type=click.Choice(list_strategies()))
@click.option("--metric", default="sharpe",
              type=click.Choice(["sharpe", "returns", "win_rate"]),
              help="Optimization metric: sharpe (default), returns, win_rate.")
@click.pass_context
def optimize(ctx, ticker, strategy, metric):
    """
    Grid-search best parameters for STRATEGY on TICKER.

    Example: trader strategies optimize AAPL --strategy rsi --metric sharpe
    """
    _grids = {
        "rsi": {"period": [7, 14, 21], "oversold": [25, 30], "overbought": [70, 75]},
        "macd": {"fast": [8, 12], "slow": [21, 26], "signal": [7, 9]},
        "ma_cross": {"fast_window": [10, 20], "slow_window": [40, 50]},
        "bnf": {"lookback": [10, 20], "breakout_pct": [0.01, 0.02]},
    }
    strat_cls = get_strategy(strategy).__class__
    opt = Optimizer()
    df = _fetch_ohlcv(ticker, "1d", "1y")
    best = opt.grid_search(strat_cls, df, _grids.get(strategy, {}), metric=metric)
    output_json({"ticker": ticker, "strategy": strategy, "metric": metric, "best_params": best})
