# Gold Backtest Lab

Compare five rule-based XAUUSD/Gold strategy prototypes on historical candles. This is research code, **not a guaranteed trap-free signal or financial advice**.

## Strategies
1. Liquidity sweep + MSS + FVG
2. Liquidity sweep + MSS + order-block retest
3. Failed breakout reversal
4. Sweep + displacement + FVG
5. Asian-range sweep + London/NY reversal

## Data
The script downloads public OKX historical candles for PAXG-USDT (gold-backed token, NOT broker XAUUSD). Binance API returned HTTP 451 from the GitHub runner, so OKX is used as the market data source. No API key is needed. OKX history availability may vary by instrument and timeframe. Backtest results can be affected by spread, slippage, commissions, data gaps, and candle ambiguity.

## Run locally
```bash
pip install -r requirements.txt
python backtest.py
```

## GitHub Actions
Use **Actions → Gold strategy backtest → Run workflow**. It downloads data, compares strategies and uploads `reports/strategy_comparison.csv` and `reports/trades.csv` as an artifact.

## Method
- Signal timeframe: 15-minute bars (when Yahoo provides them).
- Default stop: ATR-based; target: 2R.
- Conservative same-candle handling: if SL and TP are both touched, count SL first.
- Strategies are compared on the same data. This initial version is a prototype; do not use results to trade live.
- A credible evaluation should add broker-specific spreads, out-of-sample periods, walk-forward validation and independent data.

