# 📋 Jermaine's Trading Playbook

**Account:** $3,000 (Schwab Cash) | **Max Risk/Trade:** $500 | **Timezone:** ET

---

## 🤖 BOTS

### 1. SPY 0DTE Options Bot
**What:** Scalps SPY 0DTE options on intraday momentum
**Signal:** $0.20 move in 18 seconds → buy call or put
**Targets:** 60% TP / 35% SL / trailing stop at 20%
**When:** 9:45 AM – 3:30 PM
**Best for:** Slow, consistent days. Tight spreads, high liquidity.
```bash
cd ~/Documents/jmragsdale/trading-futures-scalp-bot
source venv/bin/activate
python schwab_0dte_main.py --paper
python schwab_0dte_main.py --live
```

---

### 2. Volatile Stocks 0DTE Options Bot
**What:** Same momentum strategy but on NVDA, TSLA, AMD, AAPL, MSFT, META, GOOGL, AMZN
**Signal:** 0.4% move in 20 seconds → buy call or put on hottest ticker
**Targets:** 70% TP / 40% SL / trailing stop at 20%
**When:** 9:45 AM – 3:30 PM
**Best for:** High-volatility days. More signals than SPY bot. Higher risk/reward.
```bash
python volatile_stocks_main.py --paper
python volatile_stocks_main.py --paper --tickers NVDA,TSLA
python volatile_stocks_main.py --live
```

---

### 3. Momentum Scalp Bot (Ross Cameron Style) 💰 NEW
**What:** Trades SHARES on small-cap gappers ($2–$30)
**Signal:** VWAP pullback reclaim OR pre-market high breakout + volume surge
**Targets:** 6% partial TP (sell half) → 1.5% trailing stop on rest / 2.5% hard stop
**When:** Auto-starts 7:00 AM (LaunchAgent) → scans pre-market → trades 9:30–11:30 AM
**Best for:** Small account growth. Fast scalps on crowd momentum. No options Greeks to manage.

**Scanner finds:** 4%+ gap, 2x+ relative volume, $2–$30, news catalyst check (Yahoo/Google News)
**Catalyst scoring:** Strong news = 2x boost | Any news = 1.5x | No news = 0.4x penalty

```bash
python momentum_scalp_main.py --paper                      # Auto-scan
python momentum_scalp_main.py --paper --tickers ABCD,EFGH  # Trading Terminal picks
python momentum_scalp_main.py --paper --extended            # Trade until 2 PM
python momentum_scalp_main.py --paper --min-gap 3           # Lower gap threshold
```

**Position sizing:** Risk-based. 3% of account ($90) per trade. Max 50% in one stock.
**Cash account limit:** 3 trades/day (T+1 settlement). $100 cash buffer always held.

---

### 4. Tradovate Micro Futures Bot
**What:** Tick-based momentum on MES/MNQ micro futures
**When:** 24/5 (futures market)
**Best for:** Futures traders, leverage, low capital requirement.
```bash
python main_application.py --demo
python main_application.py --live
```

---

## 📡 SCANNERS & ALERTS

### Unusual Flow Scanner
**What:** Detects institutional options flow (large premium, sweeps, unusual volume)
**Source:** Unusual Whales API
**Schedule:** Every 15 min during market hours (9:00 AM – 4:00 PM) via OpenClaw cron
**Output:** Telegram alerts with ticker, direction, premium, GEX bias score
**File:** `~/. openclaw/workspace/gex/unusual_flow_scanner.py`

---

### GEX Backend (Gamma Exposure)
**What:** FastAPI server providing real-time gamma exposure levels for SPY/QQQ
**Use:** Identifies key support/resistance (gamma walls, put walls) for entries
**Runs:** Always-on LaunchAgent at `localhost:8000`
**File:** `~/.openclaw/workspace/gex/backend/main.py`
**Plist:** `~/Library/LaunchAgents/com.gex.backend.plist`

---

### SPY 0DTE Analysis (ICT)
**What:** ICT-based analysis (order blocks, FVGs, liquidity sweeps, kill zones)
**Schedule:** 6 daily scans via OpenClaw cron → Telegram
**Best for:** Confluence with GEX levels for A+ setups

---

### Trade War Alerts
**What:** Auto-analyzes thetradewar.com URLs when you send them
**Trigger:** Send any `thetradewar.com/pages/app-*` link
**Output:** Rates each trade setup as 🟢 FAVORABLE / 🟡 CONDITIONAL / 🔴 SKIP
**Config:** See TOOLS.md

---

## ⏰ DAILY SCHEDULE (ALL AUTOMATED)

| Time | What | How |
|------|------|-----|
| 7:00 AM | Momentum Scalp Bot starts, pre-market scan begins | LaunchAgent |
| 9:00 AM | Unusual Flow Scanner starts (every 15 min) | OpenClaw cron |
| 9:30 AM | Market open — Scalp Bot starts trading | Auto |
| 9:30 AM | ICT kill zone scans begin | OpenClaw cron |
| 9:45 AM | SPY/Volatile bots can start (if running) | Manual |
| 11:30 AM | Scalp Bot stops new entries (unless --extended) | Auto |
| 3:50 PM | Scalp Bot closes remaining positions | Auto |
| 4:00 PM | Flow Scanner stops | OpenClaw cron |
| EOD | Scalp Bot sends daily summary to Telegram | Auto |

---

## 🔑 CREDENTIALS & INFRA

| Item | Location |
|------|----------|
| Schwab API (encrypted) | `~/.schwab_0dte_bot/.credentials.enc` |
| Schwab tokens (plaintext!) | `SCHWAB_TOKENS.txt` ⚠️ |
| UW API token | `.env` (443321a2...) |
| Telegram bot token | `.env` (8517310351...) |
| GEX backend | `localhost:8000` |
| OpenClaw config | `~/.openclaw/openclaw.json` |
| All cron jobs | Model: `opus` (15 jobs total) |

---

## 📊 STRATEGY MATRIX — WHICH BOT WHEN?

| Market Condition | Best Bot | Why |
|-----------------|----------|-----|
| Small-cap gapper with news | **Momentum Scalp** | Ross Cameron bread & butter |
| Slow grind, SPY range-bound | **SPY 0DTE** | Tight spreads, consistent signals |
| Tech earnings / big NVDA move | **Volatile Stocks** | Higher profit target on options |
| Overnight futures play | **Tradovate** | 24/5 market access |
| Flow scanner flags unusual call sweep | **Manual trade** using flow + GEX + ICT confluence | A+ setup |

---

## 🧮 THE MATH — $3K → DOWN PAYMENT

| Monthly Return | Month 6 | Month 12 | Month 18 | Month 24 |
|---------------|---------|----------|----------|----------|
| 8% net | $4,762 | $7,580 | $12,068 | $19,213 |
| 15% net | $6,939 | $16,070 | $37,218 | $86,227 |
| 20% net | $8,957 | $26,738 | $79,824 | $238,297 |

**Target:** $150K–$300K for home down payment (10–20% of $1.5M)
**At 15% monthly compounding:** ~20 months
**At 8% monthly compounding:** ~30 months

**Reality:** Factor in drawdowns, flat months, and taxes. Add 6–12 months buffer.

---

*Last updated: 2026-02-05*
