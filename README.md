# Setup Guide - IBKR Trading MVP

## Quick Start

### 1. Create Virtual Environment
```bash
cd /Users/beam/projects/vibe/trader
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure IBKR Connection
```bash
cp .env.example .env
```

Edit `.env` with your IBKR settings:
- `IB_HOST=127.0.0.1` (localhost if TWS/Gateway is on same machine)
- `IB_PORT=7497` (paper trading) or `7496` (live trading)
- `IB_CLIENT_ID=101` (unique ID for this connection)
- `IB_ACCOUNT=` (optional, your IBKR account number)

### 4. IBKR TWS/Gateway Setup

**Before running, ensure TWS or IB Gateway is configured:**

1. Download and install TWS or IB Gateway from IBKR
2. Open TWS → **File** → **Global Configuration** → **API** → **Settings**
3. Enable "**Enable ActiveX and Socket Clients**"
4. Set "**Socket Port**" to `7497` (paper) or `7496` (live)
5. **CRITICAL:** Uncheck "**Read-Only API**" to allow order submission
6. Add `127.0.0.1` to "**Trusted IP Addresses**"
7. Click **OK** and restart TWS/Gateway

### 5. Test Connection
```bash
python examples/one_off.py
```

This will:
- Connect to IBKR
- Place a 1-share market order for AAPL (paper account)
- Fetch AAPL daily history

## Common Issues

### Connection Refused
- Ensure TWS/Gateway is running
- Verify `IB_PORT` matches TWS API settings
- Check `127.0.0.1` is in trusted IPs

### Order Rejected
- Ensure "Read-Only API" is **disabled** in TWS
- Verify you have sufficient paper/live account balance
- Check symbol is valid and market is open

### qualifyContracts Failed
- Symbol may be invalid or delisted
- Try a well-known symbol like "AAPL" first
- Ensure market data subscription is active

## Running Scheduled Strategy
```bash
python examples/scheduled.py
```

Runs a breakout strategy every 10 seconds (demo).

## Next Steps
- Add your actual trading strategy logic in `examples/scheduled.py`
- Extend `vibe/venues/ibkr.py` for options/futures (use `Option`, `Future` contracts)
- Add structured logging for production monitoring

### Immediate (v0.2):
- Add logging to scheduler task failures
- Implement reconnection handler
- Add order rejection reason to OrderResponse
Add order rejection reason to OrderResponse
### Soon (v0.3):
- Options/futures support (contracts already in ib_insync)
- Real-time market data subscriptions
- Position tracking
### Later (v1.0):
- Risk limits (max position size, daily loss limits)
- Performance instrumentation (latency metrics)
- Multi-venue routing (crypto exchanges)
