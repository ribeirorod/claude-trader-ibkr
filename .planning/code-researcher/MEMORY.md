# Code Researcher Memory

Last updated: 2026-03-10

## Codebase Patterns
- Venue abstraction: `Trader` facade delegates to `IBKRAdapter` -> See: `codebase-overview.md`
- Async-first: All venue methods are async; connection is lazy (on first call)
- sys.path hacking: volatility/composer imports vibe via sys.path.insert, not proper packaging
- Client ID management: global counters in ibkr_data_fetcher.py (300+) and vibe_adapter.py (200+) to avoid conflicts
- New trader/ CLI: click-based, all output JSON, adapter pattern via factory -> See: `dead-code-audit.md`

## Architecture
- Connection: ib_insync==0.9.86 -> TWS/IB Gateway socket (127.0.0.1:7497 default) -> See: `codebase-overview.md`
- New trader/ uses ibkr-rest (Client Portal Gateway HTTPS) as primary adapter
- Strategy pipeline: BaseStrategy.signals(df) -> pd.Series of 1/-1/0 -> See: `dead-code-audit.md`
- Data sources: OHLCV only (yfinance or IBKR historical bars), no real-time streaming
- News: Benzinga REST API (token query param, Accept: application/json header)

## Key Abstractions
- `trader/adapters/base.py`: Adapter ABC -- connect/disconnect/get_account/get_quotes/place_order/etc
- `trader/adapters/factory.py`: get_adapter() dispatches on broker name
- `trader/config.py`: Config dataclass from env vars (has unused fields: ibkr_username, ibkr_password, max_position_pct, default_strategy)
- `trader/models/`: Pydantic models (Account, Balance, Margin, Order, OrderRequest, Position, PnL, Quote, OptionChain, NewsItem, SentimentResult)
- `trader/strategies/factory.py`: Strategy registry (rsi, macd, ma_cross, bnf)

## Gotchas
- PnL model defined but never used -- cli/positions.py computes P&L as inline dict
- Config.ibkr_username/ibkr_password defined but never read by any code
- Config.default_strategy defined but CLI hardcodes default="rsi"
- OptionContract Greeks fields (delta/gamma/theta/vega/implied_vol/open_interest) never populated
- ibkr_tws adapter: Order as IBOrder imported but never used (line 90)
- Options: ZERO support -- _qualify_stock() only creates Stock contracts, normalize_symbol_ibkr is pass-through
- News bulletins: subscribe_news_bulletins is IB SYSTEM bulletins, NOT per-symbol news
- Real-time: No reqMktData/reqRealTimeBars -- only historical bar data available
- Global env mutation: IBKRDataFetcher/VibeTraderAdapter write os.environ['IB_CLIENT_ID'] globally
- Scheduler: silently swallows all exceptions in _run_task
