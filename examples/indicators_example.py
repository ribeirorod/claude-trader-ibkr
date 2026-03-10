"""
Example: Calculate technical indicators from IBKR history data.

This demonstrates how to:
1. Fetch historical data from IBKR
2. Calculate technical indicators using the IndicatorCalculator
3. Use both individual indicator methods and the convenience function
"""

import asyncio
import pandas as pd

from vibe import Trader, IndicatorCalculator, calculate_indicators


async def main():
    # Initialize trader
    trader = Trader()
    
    try:
        # Fetch historical data for AAPL
        print("Fetching historical data for AAPL...")
        df = await trader.history(
            symbol="AAPL",
            start="2024-01-01",
            end=None,  # Current date
            interval="1d"
        )
        
        if df.empty:
            print("No data returned!")
            return
        
        print(f"\nRetrieved {len(df)} bars")
        print("\nOriginal columns:", df.columns.tolist())
        print("\nFirst few rows:")
        print(df.head())
        
        # ========== Method 1: Using convenience function ==========
        print("\n" + "="*60)
        print("Method 1: Calculate all indicators at once")
        print("="*60)
        
        df_with_indicators = calculate_indicators(df)
        print("\nAll calculated indicators:")
        indicator_cols = [col for col in df_with_indicators.columns if col not in df.columns]
        print(indicator_cols)
        
        print("\nLatest indicator values:")
        latest = df_with_indicators.iloc[-1]
        print(f"  Close Price: ${latest['close']:.2f}")
        print(f"  SMA 20: ${latest['sma_20']:.2f}")
        print(f"  SMA 50: ${latest['sma_50']:.2f}")
        print(f"  RSI: {latest['rsi']:.2f}")
        print(f"  MACD: {latest['macd']:.4f}")
        print(f"  MACD Signal: {latest['macd_signal']:.4f}")
        print(f"  Bollinger Upper: ${latest['bb_upper']:.2f}")
        print(f"  Bollinger Lower: ${latest['bb_lower']:.2f}")
        print(f"  ATR: ${latest['atr']:.2f}")
        print(f"  Stochastic %K: {latest['stochastic_k']:.2f}")
        print(f"  Stochastic %D: {latest['stochastic_d']:.2f}")
        
        # ========== Method 2: Using IndicatorCalculator directly ==========
        print("\n" + "="*60)
        print("Method 2: Calculate specific indicators individually")
        print("="*60)
        
        calc = IndicatorCalculator()
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        
        # Calculate specific indicators
        rsi = calc.rsi(close, period=14)
        macd_line, signal_line, histogram = calc.macd(close, fast_period=12, slow_period=26, signal_period=9)
        bb_lower, bb_middle, bb_upper = calc.bollinger_bands(close, window=20, std_dev=2.0)
        atr = calc.atr(high, low, close, period=14)
        stoch_k, stoch_d = calc.stochastic_oscillator(high, low, close, k_window=14, d_window=3)
        obv = calc.obv(close, volume)
        ichimoku = calc.ichimoku_cloud(high, low, close)
        
        print("\nLatest individual indicator values:")
        print(f"  RSI: {rsi.iloc[-1]:.2f}")
        print(f"  MACD Line: {macd_line.iloc[-1]:.4f}")
        print(f"  MACD Signal: {signal_line.iloc[-1]:.4f}")
        print(f"  MACD Histogram: {histogram.iloc[-1]:.4f}")
        print(f"  Bollinger Upper: ${bb_upper.iloc[-1]:.2f}")
        print(f"  Bollinger Middle: ${bb_middle.iloc[-1]:.2f}")
        print(f"  Bollinger Lower: ${bb_lower.iloc[-1]:.2f}")
        print(f"  ATR: ${atr.iloc[-1]:.2f}")
        print(f"  Stochastic %K: {stoch_k.iloc[-1]:.2f}")
        print(f"  Stochastic %D: {stoch_d.iloc[-1]:.2f}")
        print(f"  OBV: {obv.iloc[-1]:,.0f}")
        print(f"  Ichimoku Conversion Line: ${ichimoku['conversion_line'].iloc[-1]:.2f}")
        print(f"  Ichimoku Base Line: ${ichimoku['base_line'].iloc[-1]:.2f}")
        
        # ========== Method 3: Price analysis ==========
        print("\n" + "="*60)
        print("Method 3: Price analysis indicators")
        print("="*60)
        
        highest_high = calc.highest_high(high, period=20)
        lowest_low = calc.lowest_low(low, period=20)
        price_sma_diff = calc.price_sma_difference(close, window=20)
        
        print("\nLatest price analysis:")
        print(f"  Current Close: ${close.iloc[-1]:.2f}")
        print(f"  20-Period Highest High: ${highest_high.iloc[-1]:.2f}")
        print(f"  20-Period Lowest Low: ${lowest_low.iloc[-1]:.2f}")
        print(f"  Price vs SMA20: {price_sma_diff.iloc[-1]:.2f}%")
        
        # ========== Save to CSV for analysis ==========
        output_file = "aapl_with_indicators.csv"
        df_with_indicators.to_csv(output_file, index=False)
        print(f"\n✅ Saved data with indicators to {output_file}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await trader.close()


if __name__ == "__main__":
    asyncio.run(main())

