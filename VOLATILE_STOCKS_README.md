# Volatile Stocks 0DTE Options Trading Bot

A percentage-based momentum trading bot for 0DTE options on liquid, volatile stocks like NVDA, TSLA, AMD, etc.

## Key Differences from SPY Bot

| Feature | SPY Bot | Volatile Stocks Bot |
|---------|---------|---------------------|
| **Momentum Detection** | Dollar-based ($0.20 in 18s) | **Percentage-based (0.4% in 20s)** |
| **Tickers** | SPY only | **Multiple tickers (NVDA, TSLA, AMD, etc.)** |
| **Ticker Selection** | Fixed | **Dynamic - trades the most volatile ticker** |
| **Price Levels** | ~$580 | $100-$800 (adaptable) |
| **Volatility** | Low (SPY is stable) | **High (tech stocks move fast)** |
| **Option Spreads** | 8% max | **10-12% max (volatile stocks = wider spreads)** |
| **Take Profit** | 60% | **70% (wider for volatility)** |
| **Stop Loss** | 35% | **40% (wider for volatility)** |

## Why Percentage-Based?

**Dollar-based doesn't work across different price levels:**
- $0.50 move on SPY ($580) = 0.086%
- $0.50 move on AMD ($120) = 0.42% (5x more volatile!)
- $0.50 move on NVDA ($800) = 0.063% (much less significant)

**Percentage-based normalizes across all stocks:**
- 0.4% move is the same signal whether stock is $100 or $800
- Captures relative momentum, not absolute price changes

## Default Tickers (Ordered by Liquidity)

1. **NVDA** - Nvidia (excellent options volume)
2. **TSLA** - Tesla (very liquid options)
3. **AMD** - Advanced Micro Devices
4. **AAPL** - Apple
5. **MSFT** - Microsoft
6. **META** - Meta/Facebook
7. **GOOGL** - Google
8. **AMZN** - Amazon

These stocks have:
- High daily volume (10M+ shares)
- Liquid options markets
- Good intraday volatility
- Tight bid-ask spreads (for options)

## How It Works

### 1. Ticker Scanning (Every 30 Seconds)
The bot scans all configured tickers and scores them based on:
- **Intraday range** (higher = better)
- **Price level** (prefers $100-$800 range)
- **Volume** (higher = better liquidity)
- **Current momentum** (already moving = more likely to continue)

The highest-scoring ticker becomes the "active ticker" for signal detection.

### 2. Signal Detection (Percentage-Based)
Monitors the active ticker for:
- **0.4% move in 20 seconds** = momentum signal
- **Direction**: Up = BUY CALL, Down = BUY PUT

### 3. Contract Selection
Filters options by:
- Delta: 0.50 (ATM for faster-moving stocks)
- Spread: <10-12% (wider than SPY due to volatility)
- Premium: >$1.00 (lower min than SPY)
- Volume: >200 contracts
- Open Interest: >300

### 4. Position Management
- **Take Profit**: 70% gain
- **Stop Loss**: 40% loss
- **Trailing Stop**: Activates at 20% profit, trails by 25%
- **EOD Exit**: 3:55 PM

## Installation & Setup

### 1. Use Existing Schwab Credentials
No new setup needed! Uses the same credentials as the SPY bot:

```bash
# If you haven't set up credentials yet
python schwab_0dte_main.py --setup
```

### 2. Run the Volatile Stocks Bot

**Paper Trading (Recommended First):**
```bash
python volatile_stocks_main.py --paper
```

**Custom Tickers:**
```bash
python volatile_stocks_main.py --paper --tickers NVDA,TSLA,AMD
```

**Live Trading:**
```bash
python volatile_stocks_main.py --live
```

## Configuration

The bot uses `VolatileStockConfig` in [volatile_stocks_0dte_bot.py](volatile_stocks_0dte_bot.py):

```python
# Default settings
time_window: 20 seconds
min_percent_movement: 0.40%  # Signal threshold

# Options filtering
target_delta: 0.50
max_bid_ask_spread: 0.12  # 12%
min_option_price: $1.00
min_volume: 200
min_open_interest: 300

# Risk management
stop_loss_percent: 40%
take_profit_percent: 70%
trailing_stop_percent: 25%
trailing_stop_activation: 20%
```

## Customization Examples

### More Aggressive (More Signals)
Edit `volatile_stocks_0dte_bot.py`:
```python
min_percent_movement: 0.25  # 0.25% instead of 0.40%
time_window: 25  # Longer window
```

### More Conservative (Fewer, Higher Quality Signals)
```python
min_percent_movement: 0.60  # 0.6% instead of 0.40%
time_window: 15  # Shorter window
min_volume: 500  # Higher liquidity requirement
```

### Focus on Specific Stocks
```bash
# Only trade NVDA
python volatile_stocks_main.py --paper --tickers NVDA

# Only trade mega-cap tech
python volatile_stocks_main.py --paper --tickers AAPL,MSFT,GOOGL,AMZN
```

## Advantages Over SPY Bot

1. **More Signals**: Volatile stocks move faster than SPY
2. **Higher Profit Potential**: 70% TP vs 60% for SPY
3. **Adaptability**: Switches to the most active stock automatically
4. **Works Across Price Levels**: Percentage-based = works for $100 or $800 stocks

## Disadvantages vs SPY Bot

1. **Wider Spreads**: Options on individual stocks have wider bid-ask spreads
2. **Higher Risk**: Individual stocks are more volatile than SPY
3. **Lower Liquidity**: Even liquid stocks have less option volume than SPY
4. **Headline Risk**: Single-stock news can cause unexpected moves

## Risk Warnings

⚠️ **This strategy is HIGHER RISK than the SPY bot:**

- Individual stocks can gap on news
- Earnings announcements can cause extreme volatility
- Options on volatile stocks have wider spreads
- Slippage can be higher
- 0DTE options can expire worthless in minutes

**Only trade with money you can afford to lose completely.**

## Monitoring & Debugging

**Enable DEBUG logging** to see:
- Ticker scanning scores
- Near-signals (80%+ of threshold)
- Contract selection details

```bash
python volatile_stocks_main.py --paper --log-level DEBUG
```

Sample DEBUG output:
```
[INFO] Ticker scan: NVDA (score: 45.3) | Range: 2.1% | Price: $725.40
[DEBUG] Near signal [NVDA]: up 0.32% in 15.2s (80% of 0.40% threshold)
[INFO] BULLISH Signal [NVDA]: +0.42% ($3.05) in 18.1s
[INFO] Selected [NVDA]: NVDA240127C725 | Delta: 0.51 | Bid/Ask: $4.20/$4.35
```

## Backtesting Suggestions

Before going live, test with different parameters:

1. **Threshold Testing**: Try 0.3%, 0.4%, 0.5% thresholds
2. **Ticker Selection**: Test single tickers vs multi-ticker
3. **Time Windows**: Test 15s, 20s, 25s windows
4. **Risk Parameters**: Adjust TP/SL for your risk tolerance

## Production Deployment

For 24/7 operation:

```bash
# With logging
python volatile_stocks_main.py --live --log-level INFO 2>&1 | tee volatile_bot.log

# Or use systemd/supervisor for auto-restart
```

## Comparison: When to Use Which Bot?

| Use SPY Bot When... | Use Volatile Stocks Bot When... |
|---------------------|----------------------------------|
| You want consistency | You want more action |
| You prefer tight spreads | You can handle wider spreads |
| You're risk-averse | You want higher profit potential |
| Market is slow | You want multiple opportunities |
| Testing the strategy | You're experienced with options |

## Future Enhancements

Potential improvements:
- [ ] Add earnings calendar filter (avoid trading near earnings)
- [ ] Implement multi-position support (trade 2-3 tickers simultaneously)
- [ ] Add implied volatility filters
- [ ] Include sector rotation logic
- [ ] Add time-of-day weighting (different tickers perform better at different times)

## Questions?

The code is well-documented. Key files:
- [volatile_stocks_0dte_bot.py](volatile_stocks_0dte_bot.py) - Core strategy
- [volatile_stocks_main.py](volatile_stocks_main.py) - Main entry point
- [schwab_0dte_bot.py](schwab_0dte_bot.py) - Shared Schwab API client

For setup questions, see the original [README.md](README.md).
