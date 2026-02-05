# Momentum Scalp Bot — Quick Start Guide

## 🎯 What This Does

Finds small-cap stocks gapping up in pre-market and scalps the fast moves — Ross Cameron / Warrior Trading style. Trades **SHARES** (not options) for simplicity and better fills on small caps.

---

## ⚡ Quick Start

```bash
# Paper trading — let the scanner find today's runners
python momentum_scalp_main.py --paper

# Paper trading — you pick the tickers from Trading Terminal
python momentum_scalp_main.py --paper --tickers ABCD,EFGH,XYZ

# Debug mode (see everything)
python momentum_scalp_main.py --paper --log-level DEBUG
```

**Prerequisites:** Schwab credentials already set up (`python schwab_0dte_main.py --setup`)

---

## 🔄 Daily Workflow

### 1. Pre-Market (7:00–9:25 AM)
Bot auto-scans for gapping stocks:
- Gap up **4%+** from previous close
- Price **$2–$30** (sweet spot for small accounts)
- Volume **2x+** average (crowd interest)
- Ranks by gap × volume × price score
- Picks top **5 tickers** for the day

**OR** you feed tickers manually from Trading Terminal:
```bash
python momentum_scalp_main.py --paper --tickers SMCI,MARA,RIOT
```

### 2. Market Open (9:30 AM)
Bot starts VWAP tracking and monitors for two entry signals:

**Signal A: VWAP Pullback Reclaim** 📈
- Stock pulls back toward VWAP after initial gap
- Price reclaims above VWAP and holds for 2+ candles
- Volume surges on the reclaim

**Signal B: Pre-Market High Breakout** 🚀
- Price breaks above the pre-market high
- Confirmed by 2x volume on breakout candle

### 3. Trading (9:30–11:30 AM)
- Max **3 trades/day** (cash account T+1 settlement)
- Scalps **5–10% moves** with **2.5% stops**
- Trailing stop activates after **3% profit**
- Partial profit taken at **6%** (50% of position)

### 4. Auto-Close
- Positions closed by **3:50 PM** (if still open)
- Max hold time: **30 minutes** per trade
- Daily loss limit: **$200** (stops trading for the day)

---

## ⚙️ Configuration

### For Your $3K Account (defaults are tuned for this)

| Setting | Default | Meaning |
|---------|---------|---------|
| Risk per trade | 3% ($90) | How much you lose if stopped out |
| Max position | 50% ($1,500) | Biggest single position |
| Stop loss | 2.5% | Exit if trade goes against you |
| Take profit | 6% | First target (sell half) |
| Trailing stop | 1.5% | Trails after 3% profit |
| Max trades/day | 3 | Cash account limit |
| Cash buffer | $100 | Never touch this |

### Adjust Risk (More/Less Aggressive)

```bash
# More conservative (fewer trades, tighter stops)
python momentum_scalp_main.py --paper --max-trades 2

# More aggressive (bigger scanner net)
python momentum_scalp_main.py --paper --min-gap 3 --max-price 50

# Extended hours (trade until 2 PM instead of 11:30)
python momentum_scalp_main.py --paper --extended
```

### Edit Defaults in Code
File: `momentum_scalp_bot.py` → `ScalpConfig` class (top of file)

---

## 📊 Position Sizing Example

**Stock: ABCD @ $8.00 | Stop: $7.80 (2.5%)**

```
Risk per share:  $0.20 ($8.00 - $7.80)
Risk budget:     $90 (3% of $3,000)
Shares:          450 (= $90 / $0.20)
Position cost:   $3,600 → CAPPED at $1,500 (50% limit)
Final shares:    187 (= $1,500 / $8.00)
Actual risk:     $37.40 (187 × $0.20)
```

If the stock hits 6% target ($8.48):
```
Sell 93 shares (half) → profit: $44.64
Remaining 94 shares trail with 1.5% stop
```

---

## 📱 Telegram Notifications

Daily summary auto-sends to your Telegram. Already configured in `.env`:
```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

---

## 🏗️ Architecture

```
                         ┌───────────────────┐
 Trading Terminal ──────▶│ momentum_scanner  │ (manual tickers)
                         │                   │
 Schwab API movers ─────▶│ Pre-market scan   │ (auto-scan)
                         └────────┬──────────┘
                                  │ Watchlist (3-5 tickers)
                                  ▼
                         ┌───────────────────┐
                         │ momentum_scalp_bot│
                         │                   │
                         │ • VWAP tracker    │
                         │ • Entry detection │
                         │ • Position mgmt   │
                         │ • Cash tracking   │
                         └────────┬──────────┘
                                  │
                                  ▼
                         ┌───────────────────┐
                         │ Schwab API        │
                         │ (share orders)    │
                         │ + Account Safety  │
                         └───────────────────┘
```

### Files

| File | Purpose |
|------|---------|
| `momentum_scalp_main.py` | Entry point (run this) |
| `momentum_scalp_bot.py` | Core strategy + Schwab share trading |
| `momentum_scanner.py` | Pre-market gap scanner |
| `.env` | Telegram credentials |

---

## 🧪 Testing

### Step 1: Verify Scanner Works
```bash
# Run scanner only to see what it finds
python -c "
import asyncio
from momentum_scanner import MomentumScanner, ScannerConfig
from momentum_scalp_bot import MomentumSchwabClient
from schwab_0dte_bot import OptionsConfig
from schwab_config_manager import SchwabConfigManager

async def test():
    mgr = SchwabConfigManager('~/.schwab_0dte_bot')
    creds = mgr.load_credentials()
    client = MomentumSchwabClient(OptionsConfig(symbol='SPY'), config_manager=mgr)
    await client.initialize(creds.client_id, creds.client_secret, creds.refresh_token)
    scanner = MomentumScanner(client)
    results = await scanner.scan()
    print(f'Found {len(results)} candidates')
    await client.close()

asyncio.run(test())
"
```

### Step 2: Paper Trade for 1 Week
```bash
python momentum_scalp_main.py --paper --log-level DEBUG
```

Watch for:
- Are the right stocks being found?
- Do entry signals make sense?
- Are stops and targets reasonable?
- What's the simulated win rate?

### Step 3: Go Live (Small)
```bash
python momentum_scalp_main.py --live --max-trades 1
```

Start with **1 trade per day max**. Scale up after proving consistency.

---

## 🆚 Compared to Your Other Bots

| Feature | SPY 0DTE Bot | Volatile Stocks Bot | **Momentum Scalp Bot** |
|---------|-------------|--------------------|-----------------------|
| Instrument | SPY options | Tech stock options | **Shares** |
| Tickers | SPY only | NVDA, TSLA, etc. | **Dynamic (scanner)** |
| Price range | $580+ | $100-$800 | **$2-$30** |
| Signal | $0.20/18s | 0.4%/20s | **VWAP + breakout** |
| Hold time | Minutes | Minutes | **Seconds to minutes** |
| Target | 60% option | 70% option | **5-10% shares** |
| Account size | Any | Any | **$1K+ (ideal $3K+)** |
| Complexity | Low | Medium | **Medium** |

---

## ⚠️ Risk Warnings

- Small-cap momentum stocks can drop **20%+ in minutes**
- The 2.5% stop loss is your lifeline — **never widen it**
- Cash account = T+1 settlement. After 3 trades, you're done for the day.
- **Most small-cap gappers fade.** The scanner filters for quality, but some will fail.
- Paper trade for at least 1 week before going live.
- **Only trade money you can afford to lose.**

---

## 🎯 The Math (Why This Works for Account Growth)

```
Starting account: $3,000
Avg position: 200 shares @ $8 = $1,600
Win rate: 55% (conservative)
Avg win: +5% = +$80
Avg loss: -2.5% = -$40

Per trade expectancy: (0.55 × $80) - (0.45 × $40) = $26
Trades/day: 2.5 avg
Daily expectancy: $65

Monthly (20 trading days): $1,300
→ 43% monthly return on $3K

Compounded: $3K → $4.3K → $6.2K → $8.8K → $12.6K → $18K → $26K...
```

**Reality check:** These are theoretical. Actual results depend on execution, market conditions, and discipline. A 55% win rate with 2:1 R:R is achievable but takes practice.

---

**Built on top of your existing Schwab trading infrastructure.**
**Last Updated:** 2026-02-05
