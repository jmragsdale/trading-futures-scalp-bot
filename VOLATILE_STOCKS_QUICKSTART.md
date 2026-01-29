# Volatile Stocks 0DTE Options Bot - Quick Start Guide

## 🚀 Getting Started

### Prerequisites
You need Schwab credentials already set up:
```bash
# If not done yet, run SPY bot setup first
python schwab_0dte_main.py --setup
```

### Run the Bot
```bash
# Paper trading - default tickers (NVDA, TSLA, AMD, AAPL, MSFT, META, GOOGL, AMZN)
python volatile_stocks_main.py --paper

# Paper trading - custom tickers
python volatile_stocks_main.py --paper --tickers NVDA,TSLA,AMD

# Single ticker mode
python volatile_stocks_main.py --paper --tickers NVDA

# Debug mode (see everything)
python volatile_stocks_main.py --paper --log-level DEBUG

# Live trading (real money!)
python volatile_stocks_main.py --live
```

---

## ⚙️ Current Configuration

**Signal Detection (Percentage-Based):**
- Time window: **20 seconds**
- Min move: **0.40%** (percentage, not dollars!)
- **Examples:**
  - NVDA $725 → $727.90 (0.40%) in 20s = SIGNAL ✅
  - AMD $120 → $120.48 (0.40%) in 20s = SIGNAL ✅
  - TSLA $245 → $245.98 (0.40%) in 20s = SIGNAL ✅

**Ticker Selection (Scans Every 30s):**
The bot scores all tickers and picks the most volatile one:
- Intraday range >1.5% (must be moving today)
- Prefers stocks in $100-$800 range
- Higher volume = bonus points
- Already trending = bonus points

**Entry Criteria (Options Filtering):**
- Target delta: 0.50 (ATM for faster-moving stocks)
- Max spread: 12%
- Min premium: $1.00
- Min volume: 200 contracts
- Min open interest: 300

**Exit Rules:**
- Take profit: **70%** gain (higher than SPY bot)
- Stop loss: **40%** loss (wider for volatility)
- Trailing stop: 25% (activates at 20% profit)
- EOD exit: 3:55 PM

**Trading Hours:**
- Start: 9:45 AM ET
- Stop: 3:30 PM ET (longer than SPY bot)

---

## 📊 What to Expect

### Signal Frequency
With current settings (0.40% in 20s):
- **8-15 signals per day** across all tickers during normal volatility
- **25+ signals** during high volatility (earnings, tech sector moves)
- **3-5 signals** during slow days
- More frequent than SPY bot (volatile stocks move more)

### Ticker Activity Pattern
```
Default tickers ranked by typical activity:

1. NVDA - Most volatile, best options volume
2. TSLA - Very volatile, excellent options
3. AMD  - Good volatility, decent options
4. META - Moderate volatility, good options
5. MSFT - Lower volatility, excellent options
6. AAPL - Lower volatility, excellent options
7. GOOGL - Moderate volatility, good options
8. AMZN - Moderate volatility, good options
```

**Best for beginners:** Start with just `--tickers NVDA,MSFT,AAPL` (3 most liquid)

### Typical Trade Flow
```
09:45 AM → Bot starts, scanning all 8 tickers
09:47 AM → First scan complete
         → NVDA (score: 52.3) | Range: 2.1% | Price: $725.40
         → Active ticker: NVDA

10:15 AM → NVDA moves $725.40 → $728.30 in 18s (+0.40%)
         → BULLISH signal detected ✅
         → Selects NVDA call with delta 0.51, premium $3.80
         → Places buy order at $3.88 (ask + $0.03)
         → Order fills at $3.86
         → Position opened [NVDA]

10:23 AM → Option now at $5.20 (34% gain)
         → Trailing stop activates at 20% profit
         → Trailing stop set at $4.55 (12.5% below)

10:31 AM → Option peaks at $6.85 (77% gain)
         → Take profit target (70%) HIT ✅
         → Sells at $6.75
         → P&L: +$289 per contract (74.9%)

10:32 AM → Re-scanning tickers (no position)
         → TSLA now most volatile (score: 58.1)
         → Active ticker: TSLA

Total time in trade: 16 minutes
Next trade could be different ticker
```

---

## 🔍 Monitoring Your Bot

### Log Messages You'll See

**Ticker Scanning:**
```
[INFO] Ticker scan: NVDA (score: 45.3) | Range: 2.1% | Price: $725.40
[INFO] Ticker scan: TSLA (score: 51.2) | Range: 2.8% | Price: $245.15
```

**Near Signal (DEBUG mode):**
```
[DEBUG] Near signal [NVDA]: up 0.32% in 15.2s (80% of 0.40% threshold)
```

**Signal Detected:**
```
[INFO] BULLISH Signal [NVDA]: +0.42% ($3.05) in 18.1s
[INFO] Selected [NVDA]: NVDA240127C725 | Strike: $725 | Delta: 0.51 | Bid/Ask: $4.20/$4.35 | Vol: 850 | Est. slippage: 1.8%
[INFO] Order placed in 52.15ms: BUY_TO_OPEN 1x NVDA240127C725 @ $4.38
[INFO] Order filled on attempt 1 @ $4.36
[INFO] Position opened [NVDA]: CALL @ $4.36
```

**Position Management:**
```
[INFO] Trailing stop activated at 21.3% profit, stop set at $5.45
[INFO] Trailing stop raised to $6.12 (high: $6.83)
[INFO] Position closed [NVDA]: Take profit hit (74.3%) | Entry: $4.36 | Exit: $7.60 | P&L: $324.00 (74.3%)
```

**Ticker Switching:**
```
[INFO] Ticker scan: AMD (score: 62.5) | Range: 3.2% | Price: $122.45
[Heartbeat] Scanning tickers | Active: AMD
```

### Debug Mode (Recommended)
```bash
python volatile_stocks_main.py --paper --log-level DEBUG
```

Shows:
- All ticker scan scores
- Near-signals (80%+) on all tickers
- Detailed contract selection
- Why contracts are rejected
- Order chase attempts

---

## 🛠️ Tuning Your Strategy

### Too Few Signals? Make It More Aggressive

Edit `volatile_stocks_0dte_bot.py` (lines 38-42):
```python
# In VolatileStockConfig class
min_percent_movement: float = 0.30  # Was 0.40 (easier to trigger)
time_window: int = 25                # Was 20 (longer window)
max_bid_ask_spread: float = 0.15    # Was 0.12 (allow wider spreads)
min_volume: int = 150                # Was 200 (less strict)
```

**Expected result:** 20-35 signals/day

### Too Many Signals? Make It More Conservative

```python
min_percent_movement: float = 0.50  # Was 0.40 (harder to trigger)
time_window: int = 15                # Was 20 (shorter window)
min_volume: int = 500                # Was 200 (stricter liquidity)
min_option_price: float = 1.50       # Was 1.00 (higher premium)
```

**Expected result:** 5-10 signals/day, higher quality

### Adjust Risk Parameters

```python
stop_loss_percent: float = 35.0      # Tighter (was 40%)
take_profit_percent: float = 60.0    # Lower target (was 70%)
trailing_stop_percent: float = 20.0  # Tighter trail (was 25%)
```

### Focus on Specific Tickers

**Most Liquid (Safest):**
```bash
python volatile_stocks_main.py --paper --tickers AAPL,MSFT,NVDA
```

**Most Volatile (Higher Risk/Reward):**
```bash
python volatile_stocks_main.py --paper --tickers NVDA,TSLA,AMD
```

**Single Stock (No Ticker Switching):**
```bash
python volatile_stocks_main.py --paper --tickers NVDA
```

**Avoid Certain Stocks:**
Just omit them from the list (no exclude feature needed).

---

## 🐛 Troubleshooting

### Bot Running But No Signals for Hours

**Check 1: Are tickers volatile enough?**
```bash
# Run with DEBUG to see scan scores
python volatile_stocks_main.py --paper --log-level DEBUG
```

Look for:
```
Ticker scan: NVDA (score: 15.2) | Range: 0.8% | Price: $725.40
```

If `Range < 1.5%`, stocks aren't moving much today.

**Fix:** Lower the threshold or wait for more volatile market.

```python
min_percent_movement: float = 0.25  # Instead of 0.40
min_daily_range_percent: float = 1.0  # Instead of 1.5
```

**Check 2: What's active ticker?**
```
[Heartbeat] Scanning tickers | Active: None
```

If active ticker is `None`, no stocks meet minimum volatility.

**Fix:** Add more tickers or relax volatility requirement:
```python
tickers: List[str] = ["NVDA", "TSLA", "AMD", "AAPL", "MSFT",
                      "META", "GOOGL", "AMZN", "NFLX", "BABA"]
```

### Signals on One Ticker But Not Trading It

**Symptom:** See signal on TSLA but bot is watching NVDA

**Cause:** Bot only monitors the "active" ticker (highest score)

**How it works:**
- Every 30s, bot re-scans and picks best ticker
- Only the active ticker is monitored for signals
- This prevents over-trading across too many stocks

**To monitor all simultaneously:**
Edit `volatile_stocks_0dte_bot.py` line 856:
```python
# Change from:
if self.active_ticker and self.active_ticker in snapshots:
    snap = snapshots[self.active_ticker]
    signal = self.detect_momentum_signal(self.active_ticker, snap)

# To:
for ticker, snap in snapshots.items():
    signal = self.detect_momentum_signal(ticker, snap)
    if signal:
        await self.execute_signal(ticker, signal, snap.price)
        break  # Take first signal found
```

### No Suitable Contracts (Rejections)

**Symptom:**
```
No suitable CALL contracts for NVDA (checked 35 candidates)
Rejections: wide_spread(>12%)=25, low_vol(<200)=8, low_OI(<300)=2
```

**Cause:** Individual stock options have wider spreads than SPY

**Fix for NVDA/TSLA/AMD:** Relax spread requirement
```python
max_bid_ask_spread: float = 0.18  # 18% instead of 12%
```

**Fix for lower-tier stocks:** Stick to NVDA, AAPL, MSFT only:
```bash
python volatile_stocks_main.py --paper --tickers NVDA,AAPL,MSFT
```

### Orders Not Filling

**Symptom:** "Order not filled after 3 attempts"

**Cause:** Volatile stocks move fast, price runs away

**Fix:** More aggressive order management
```python
limit_offset_cents: float = 0.05    # Was 0.03
chase_increment_cents: float = 0.08  # Was 0.05
max_chase_attempts: int = 5          # Was 3
```

### Wrong Ticker Being Traded

**Symptom:** Want to trade NVDA but bot keeps picking TSLA

**Solution 1:** Trade NVDA only
```bash
python volatile_stocks_main.py --paper --tickers NVDA
```

**Solution 2:** Adjust scoring (edit line 188 in `volatile_stocks_0dte_bot.py`):
```python
# Boost score for preferred tickers
if symbol == "NVDA":
    score += 50  # Heavily favor NVDA
elif symbol in ["AAPL", "MSFT"]:
    score += 30  # Moderately favor mega-caps
```

---

## 📈 Performance Tracking

### Compare Across Tickers

After 50+ trades, analyze per ticker:
```python
# Example analysis
NVDA: 15 trades, 60% win rate, avg P&L: +$42
TSLA: 12 trades, 50% win rate, avg P&L: +$18
AMD:  8 trades,  62% win rate, avg P&L: +$35
AAPL: 5 trades,  80% win rate, avg P&L: +$28

Conclusion: Focus on NVDA and AMD, reduce TSLA exposure
```

### Logging to File
```bash
python volatile_stocks_main.py --live 2>&1 | tee volatile_$(date +%Y%m%d).log
```

---

## ⚠️ Common Mistakes

### 1. Trading Too Many Tickers
**Problem:** Spreads 8 tickers thin, rarely get good setups on any.
**Solution:** Start with 3-4 most liquid (NVDA, AAPL, MSFT).

### 2. Not Accounting for Spreads
**Problem:** Individual stock options have 2-5% wider spreads than SPY.
**Reality:** Your 70% TP might be 65% after spreads. Account for this.

### 3. Trading Around Earnings
**Problem:** Stock can gap 10% on earnings, blowing through stops.
**Solution:** Check earnings calendar, stop bot on earnings days.

### 4. Chasing Hot Stocks
**Problem:** NVDA up 5% today = already ran, less room to move.
**Better:** Bot's scanner handles this - trust the scoring.

### 5. Over-Optimizing Single Ticker
**Problem:** "NVDA gave 5 winners in a row, let me only trade NVDA!"
**Reality:** Every ticker has hot/cold streaks. Diversify.

---

## 🎯 Ticker-Specific Tips

### NVDA (Best Overall)
- **Pros:** Most liquid options, best spreads, high volatility
- **Cons:** Expensive ($700+), large dollar moves needed
- **Best timeframe:** 10:30-11:30 AM, 2:00-3:00 PM
- **Avoid:** First 30min (wild swings), last hour (spreads widen)

### TSLA (High Risk/Reward)
- **Pros:** Extremely volatile, big profit potential
- **Cons:** Wider spreads, unpredictable (Musk tweets)
- **Best timeframe:** First hour, power hour
- **Avoid:** Mid-day lull

### AMD (Balanced)
- **Pros:** Good volatility, reasonable spreads, follows NVDA
- **Cons:** Less liquid than NVDA
- **Best timeframe:** Follows tech sector momentum
- **Tip:** Often moves with NVDA - if NVDA signals, AMD might follow

### AAPL/MSFT (Most Consistent)
- **Pros:** Excellent liquidity, tight spreads, predictable
- **Cons:** Lower volatility = fewer signals
- **Best timeframe:** All day
- **Best for:** Conservative traders, beginners

### META/GOOGL (Moderate)
- **Pros:** Decent volatility, good options
- **Cons:** Can be choppy
- **Best timeframe:** After 10:30 AM

### AMZN (Mixed)
- **Pros:** Good liquidity
- **Cons:** Expensive, lower volatility than NVDA/TSLA
- **Best for:** Large accounts

---

## 🔄 Comparison: Volatile Stocks vs SPY Bot

| Feature | SPY Bot | Volatile Stocks Bot |
|---------|---------|---------------------|
| **Signals/Day** | 5-15 | 8-20 |
| **Avg Spread** | 3-5% | 5-10% |
| **Profit Target** | 60% | 70% |
| **Stop Loss** | 35% | 40% |
| **Complexity** | Simple | Moderate |
| **Best For** | Beginners | Intermediate |
| **Risk Level** | Medium | Medium-High |

**When to use SPY bot:** You want consistency and tight spreads.
**When to use Volatile bot:** You want more action and higher profit potential.

---

## 💡 Pro Tips

1. **Start Small:** Begin with 3 tickers (NVDA, AAPL, MSFT). Expand later.

2. **Watch Correlation:** Tech stocks move together. If NVDA gaps down 3%, expect others to follow.

3. **Sector Rotation:** Some days NVDA leads, other days TSLA. Bot handles this automatically.

4. **Earnings Filter:** Keep a calendar. Don't trade stocks on earnings day.

5. **Check IV Rank:** High implied volatility = wider spreads. Bot accounts for this but be aware.

6. **Compare to SPY Bot:** Run both bots in paper mode. See which fits your style.

7. **Time of Day Matters:**
   - 9:30-10:00: Avoid (too wild)
   - 10:00-11:30: Best (trending moves)
   - 11:30-14:00: Slower (lunch period)
   - 14:00-15:30: Good (afternoon momentum)
   - 15:30-16:00: Avoid (spreads widen)

8. **Slippage Budget:** Assume 3-6% round-trip slippage. If profit < 15%, probably not worth it.

---

## 📞 Quick Reference Commands

```bash
# Paper trading - all default tickers
python volatile_stocks_main.py --paper

# Paper trading - custom tickers
python volatile_stocks_main.py --paper --tickers NVDA,TSLA,AMD

# Single ticker (no switching)
python volatile_stocks_main.py --paper --tickers NVDA

# Debug mode
python volatile_stocks_main.py --paper --log-level DEBUG

# Live trading
python volatile_stocks_main.py --live

# Live with logging
python volatile_stocks_main.py --live 2>&1 | tee trading_$(date +%Y%m%d).log
```

---

## 🎯 Daily Checklist

**Before Market Open:**
- [ ] Check earnings calendar (avoid stocks reporting today)
- [ ] Check futures (trending or choppy?)
- [ ] Review previous day's logs
- [ ] Verify credentials are fresh (< 7 days old)

**After Starting Bot:**
- [ ] Verify ticker scan completes (first 2 minutes)
- [ ] Check which ticker is "active"
- [ ] Watch for first signal within 1-2 hours
- [ ] Monitor fills if in live mode

**End of Day:**
- [ ] Verify all positions closed
- [ ] Review which tickers gave signals
- [ ] Calculate P&L per ticker
- [ ] Update notes on best/worst performers

---

## 📊 Example Daily Performance

**Good Day (High Volatility):**
```
Ticker    Signals   Trades   Win Rate   P&L
NVDA      7         5        60%        +$245
TSLA      5         3        67%        +$180
AMD       4         2        50%        +$35
AAPL      2         1        100%       +$45
-------------------------------------------------
Total     18        11       64%        +$505
```

**Slow Day (Low Volatility):**
```
Ticker    Signals   Trades   Win Rate   P&L
NVDA      2         1        100%       +$65
AAPL      1         1        0%         -$35
MSFT      1         0        N/A        $0
-------------------------------------------------
Total     4         2        50%        +$30
```

---

## 📚 Related Files

- Full documentation: [VOLATILE_STOCKS_README.md](VOLATILE_STOCKS_README.md)
- Strategy code: [volatile_stocks_0dte_bot.py](volatile_stocks_0dte_bot.py)
- Main entry point: [volatile_stocks_main.py](volatile_stocks_main.py)
- Signal comparison: [compare_signal_methods.py](compare_signal_methods.py)
- SPY bot version: [SPY_QUICKSTART.md](SPY_QUICKSTART.md)
- Schwab setup: [README.md](README.md)

---

## 🔧 Code Customization Locations

**Change signal threshold:**
`volatile_stocks_0dte_bot.py` line 40

**Change risk parameters:**
`volatile_stocks_0dte_bot.py` lines 53-56

**Change default tickers:**
`volatile_stocks_0dte_bot.py` line 108

**Change ticker scoring logic:**
`volatile_stocks_0dte_bot.py` lines 163-202

**Monitor all tickers (not just active):**
`volatile_stocks_0dte_bot.py` lines 851-860

---

**Last Updated:** 2026-01-27
**Bot Version:** Volatile Stocks 0DTE Momentum v1.0
