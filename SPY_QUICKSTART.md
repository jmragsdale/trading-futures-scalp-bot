# SPY 0DTE Options Bot - Quick Start Guide

## 🚀 Getting Started

### First Time Setup
```bash
python schwab_0dte_main.py --setup
```
Follow the wizard to configure Schwab credentials and strategy preset.

### Run the Bot
```bash
# Paper trading (no real orders)
python schwab_0dte_main.py --paper

# Live trading (real money!)
python schwab_0dte_main.py --live

# Check current configuration
python schwab_0dte_main.py --show
```

---

## ⚙️ Current Configuration

**Signal Detection:**
- Time window: **18 seconds**
- Min SPY move: **$0.20** (20 cents)
- **Example**: SPY moves from $580.00 → $580.20 in 18s = SIGNAL ✅

**Entry Criteria (Options Filtering):**
- Target delta: 0.45 (near ATM)
- Max spread: 10%
- Min premium: $1.20
- Min volume: 300 contracts
- Min open interest: 500

**Exit Rules:**
- Take profit: **60%** gain
- Stop loss: **35%** loss
- Trailing stop: 20% (activates at 15% profit)
- EOD exit: 3:55 PM

**Trading Hours:**
- Start: 9:45 AM ET (avoid open volatility)
- Stop: 3:15 PM ET (avoid late-day spread widening)

---

## 📊 What to Expect

### Signal Frequency
With current settings ($0.20 in 18s):
- **5-15 signals per day** during normal volatility
- **20+ signals** during high volatility (Fed days, major news)
- **0-3 signals** during slow, choppy days

### Typical Trade Flow
```
09:45 AM → Bot starts monitoring SPY
10:23 AM → SPY moves $580.00 → $580.22 in 16s
         → BULLISH signal detected ✅
         → Selects SPY call with delta 0.45, premium $2.50
         → Places buy order at $2.52 (ask + $0.02)
         → Order fills at $2.51
         → Position opened

10:31 AM → Option now at $3.50 (39% gain)
         → Trailing stop activates at 15% profit
         → Trailing stop set at $3.15 (10% below current)

10:35 AM → Option peaks at $4.10 (64% gain)
         → Take profit target (60%) HIT ✅
         → Sells at $4.08
         → P&L: +$157 per contract (63%)

Total time in trade: 12 minutes
```

---

## 🔍 Monitoring Your Bot

### Log Messages You'll See

**Normal Operation:**
```
[Heartbeat] Monitoring | SPY: $580.45 | Signals today: checking for $0.20 moves
```

**Near Signal (80%+ of threshold):**
```
Near signal: SPY up $0.16 in 12.1s (80% of $0.20 threshold)
```

**Signal Detected:**
```
BULLISH Signal: SPY +$0.21 in 15.3s
Selected: SPY240127C580 | Strike: $580 | Delta: 0.46 | Bid/Ask: $2.45/$2.50 | Vol: 1250
Order placed in 45.23ms: BUY_TO_OPEN 1x SPY240127C580 @ $2.52
Order filled on attempt 1 @ $2.51
Position opened: CALL @ $2.51
```

**Position Management:**
```
Trailing stop activated at 16.2% profit, stop set at $2.91
Trailing stop raised to $3.55 (high: $3.95)
Position closed: Take profit hit (61.8%) | Entry: $2.51 | Exit: $4.06 | P&L: $155.00 (61.8%)
```

**No Suitable Contracts:**
```
No suitable CALL contracts found (checked 45 candidates)
Rejection breakdown: no_quote=0, low_premium(<$1.20)=15, wide_spread(>10%)=20, low_volume(<300)=8, low_OI(<500)=2
```

### Enable Debug Logging
Edit `~/.schwab_0dte_bot/config.yaml`:
```yaml
environment:
  log_level: DEBUG  # Change from INFO to DEBUG
```

Debug mode shows:
- Near-signals at 80%+ threshold
- Contract selection scoring details
- Order fill attempts and re-pricing
- Detailed rejection reasons

---

## 🛠️ Tuning Your Strategy

### Too Few Signals? Make It More Aggressive

Edit `~/.schwab_0dte_bot/config.yaml`:
```yaml
strategy:
  min_price_movement_dollars: 0.15  # Was 0.20
  time_window_seconds: 20           # Was 18 (longer window = easier to hit)
  max_bid_ask_spread_percent: 0.12  # Was 0.10 (allow wider spreads)
  min_volume: 200                   # Was 300 (less strict)
```

**Expected result:** 15-25 signals/day

### Too Many Signals? Make It More Conservative

```yaml
strategy:
  min_price_movement_dollars: 0.30  # Was 0.20
  time_window_seconds: 15           # Was 18 (shorter window = harder to hit)
  min_volume: 500                   # Was 300 (stricter liquidity)
  min_option_price: 1.50            # Was 1.20 (higher premium = less spread impact)
```

**Expected result:** 3-8 signals/day, higher quality

### Adjust Risk Parameters

```yaml
strategy:
  stop_loss_percent: 30.0      # Tighter stop (was 35%)
  take_profit_percent: 50.0    # Lower target (was 60%)
  trailing_stop_percent: 15.0  # Tighter trail (was 20%)
```

**Trade-off:** More wins but smaller average gains

---

## 🐛 Troubleshooting

### Bot Running But No Signals for Hours

**Check 1: Is the threshold too high?**
```bash
# Watch for near-signals in DEBUG mode
python schwab_0dte_main.py --paper --log-level DEBUG
```
If you see no "Near signal" messages, threshold is too high.

**Check 2: What's the current market volatility?**
SPY needs to move $0.20 in 18 seconds. On slow days, this might not happen.

**Fix:** Lower threshold temporarily
```yaml
min_price_movement_dollars: 0.15  # Or even 0.12 for very slow days
```

### Signals Detected But No Trades

**Likely cause:** No contracts pass the filters

Look for this log message:
```
No suitable CALL/PUT contracts found
Rejection breakdown: ...
```

**Common rejections:**
- `wide_spread`: Spreads >10% → increase `max_bid_ask_spread_percent`
- `low_premium`: Premium <$1.20 → decrease `min_option_price`
- `low_volume`: Volume <300 → decrease `min_volume`

**Quick fix:** Relax all filters
```yaml
max_bid_ask_spread_percent: 0.15
min_option_price: 1.00
min_volume: 200
min_open_interest: 300
```

### Orders Not Filling

**Symptom:** "Order not filled after 3 attempts"

**Cause:** Limit price too far from ask

**Fix:** More aggressive limit pricing
```yaml
limit_offset_cents: 0.05      # Was 0.02 (start closer to ask)
chase_increment_cents: 0.05   # Was 0.03 (chase more aggressively)
max_chase_attempts: 5         # Was 3 (try more times)
```

### Stop Loss Hit Too Often

**Symptom:** Many trades exit at -35% loss

**Cause:** Stops too tight for 0DTE volatility

**Fix:** Widen stops
```yaml
stop_loss_percent: 40.0  # Was 35%
```

Or use trailing stop exclusively (no fixed stop):
- Remove fixed stop logic in code, rely only on trailing stop

---

## 📈 Performance Tracking

### Where to Find Your Results

**Console output shows:**
- Each signal detected
- Entry/exit prices
- P&L per trade
- Session summary

**To save to file:**
```bash
python schwab_0dte_main.py --live --log-file spy_bot_$(date +%Y%m%d).log
```

### Calculate Your Edge

After 20+ trades, calculate:
```
Win Rate = (Winning Trades / Total Trades) × 100
Avg Win = Sum of Winning P&Ls / Number of Wins
Avg Loss = Sum of Losing P&Ls / Number of Losses
Expectancy = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
```

**Target benchmarks:**
- Win rate: 50-65%
- Average win/loss ratio: >1.5:1
- Expectancy: >$30 per trade

---

## ⚠️ Common Mistakes

### 1. Trading Through FOMC/Major Events
SPY can gap violently. **Solution:** Stop bot 30min before scheduled events.

### 2. Not Accounting for Slippage
You'll rarely fill at mid-price. **Reality:** Expect 2-5% slippage on entry/exit.

### 3. Over-optimizing on Small Sample Size
Don't change settings after 3 losing trades. **Rule:** Need 20+ trades for meaningful data.

### 4. Ignoring Theta Decay
At 3:30 PM, theta decay accelerates. **Solution:** Bot stops at 3:15 PM by default.

### 5. Trading Illiquid Strikes
Far OTM options have wide spreads. **Solution:** Stick to delta 0.40-0.50 (near ATM).

---

## 🔐 Security Best Practices

### Credentials
```bash
# Verify credentials are encrypted
ls -la ~/.schwab_0dte_bot/
# Should show: -rw------- .credentials.enc (600 permissions)

# Never commit credentials to git
echo ".credentials.enc" >> .gitignore
echo ".key" >> .gitignore
```

### Token Refresh
Schwab refresh tokens expire after 7 days of inactivity.
**Solution:** Run bot at least once per week (paper mode is fine).

---

## 📞 Quick Reference Commands

```bash
# Setup
python schwab_0dte_main.py --setup

# Run modes
python schwab_0dte_main.py --paper
python schwab_0dte_main.py --live

# Info
python schwab_0dte_main.py --show

# With logging
python schwab_0dte_main.py --live --log-file trading.log
python schwab_0dte_main.py --paper --log-level DEBUG

# Edit config
nano ~/.schwab_0dte_bot/config.yaml
vim ~/.schwab_0dte_bot/config.yaml
```

---

## 🎯 Daily Checklist

**Before Market Open:**
- [ ] Check for scheduled Fed announcements
- [ ] Verify bot config hasn't been accidentally changed
- [ ] Check Schwab API status (schwab.com/status)

**After Starting Bot:**
- [ ] Verify "Heartbeat" messages appear every 5min
- [ ] Watch for first signal to confirm it's working
- [ ] Monitor P&L if in live mode

**End of Day:**
- [ ] Verify all positions closed (should auto-exit at 3:55)
- [ ] Review logs for any errors
- [ ] Calculate daily P&L

---

## 💡 Pro Tips

1. **First Week:** Run paper mode and log EVERYTHING. Analyze patterns before going live.

2. **Position Sizing:** Start with 1 contract until you understand behavior. Scale up slowly.

3. **Market Conditions:** Best on trending days. Worst on choppy, range-bound days.

4. **Time of Day:** Most signals occur 10:30-11:30 AM and 2:00-3:00 PM (NYSE lunch lull avoidance).

5. **Spread Cost is Real:** Your take profit is 60%, but after spreads, net might be 55%. Account for this.

6. **Compare to Buy-and-Hold:** Track if your signals beat simple SPY buy-and-hold. If not, re-evaluate.

---

## 📚 Related Files

- Full documentation: [README.md](README.md)
- Strategy code: [schwab_0dte_bot.py](schwab_0dte_bot.py)
- Main entry point: [schwab_0dte_main.py](schwab_0dte_main.py)
- Config file: `~/.schwab_0dte_bot/config.yaml`
- Volatile stocks version: [VOLATILE_STOCKS_QUICKSTART.md](VOLATILE_STOCKS_QUICKSTART.md)

---

**Last Updated:** 2026-01-27
**Bot Version:** SPY 0DTE Momentum v1.0
