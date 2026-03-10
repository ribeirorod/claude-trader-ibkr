# Code Researcher Memory

Last updated: 2026-03-10

## Codebase Patterns
- Venue abstraction: `Trader` facade delegates to `IBKRAdapter` -> See: `codebase-overview.md`
- Async-first: All venue methods are async; connection is lazy (on first call)
- sys.path hacking: volatility/composer imports vibe via sys.path.insert, not proper packaging
- Client ID management: global counters in ibkr_data_fetcher.py (300+) and vibe_adapter.py (200+) to avoid conflicts

## Architecture
- Connection: ib_insync==0.9.86 -> TWS/IB Gateway socket (127.0.0.1:7497 default) -> See: `codebase-overview.md`
- Strategy pipeline: BaseStrategy.execute() -> backtest() -> signals series (1/-1/0) -> See: `codebase-overview.md`
- Data sources: OHLCV only (yfinance or IBKR historical bars), no real-time streaming
- News: 4 IBKR endpoints wrapped (providers, historical headlines, article body, system bulletins)

## Key Abstractions
- `vibe/trader.py`: Trader facade -- buy/sell/bracket/positions/news/history
- `vibe/venues/ibkr.py`: IBKRAdapter -- all ib_insync interaction
- `vibe/models.py`: OrderResponse dataclass, enums (Side, OrderType, TimeInForce, OrderStatus)
- `volatility/composer/strategies/base.py`: BaseStrategy ABC -- execute()/backtest()/sharpe
- `volatility/composer/tools/vibe_adapter.py`: VibeTraderAdapter -- signals to orders bridge

## Gotchas
- Options: ZERO support -- _qualify_stock() only creates Stock contracts, normalize_symbol_ibkr is pass-through
- News bulletins: subscribe_news_bulletins is IB SYSTEM bulletins, NOT per-symbol news
- Real-time: No reqMktData/reqRealTimeBars -- only historical bar data available
- Global env mutation: IBKRDataFetcher/VibeTraderAdapter write os.environ['IB_CLIENT_ID'] globally
- Scheduler: silently swallows all exceptions in _run_task
