# Trading Bots Repository - Master Index

This repository contains multiple trading bots for different strategies and markets. Use this guide to navigate to the right bot for your needs.

---

## 🤖 Available Bots

### 1. Schwab 0DTE SPY Options Bot ⭐ RECOMMENDED FOR BEGINNERS
**Strategy:** Dollar-based momentum on SPY 0DTE options
**Difficulty:** Beginner-Friendly
**Quick Start:** [SPY_QUICKSTART.md](SPY_QUICKSTART.md)
**Full Docs:** [README.md](README.md) (see Schwab section)

**Best For:**
- New to options trading
- Want tight spreads and high liquidity
- Prefer single-ticker simplicity
- Risk-averse traders

**Commands:**
```bash
python schwab_0dte_main.py --setup    # First time
python schwab_0dte_main.py --paper    # Paper trading
python schwab_0dte_main.py --live     # Live trading
```

---

### 2. Schwab Volatile Stocks 0DTE Options Bot 🚀
**Strategy:** Percentage-based momentum on NVDA, TSLA, AMD, etc.
**Difficulty:** Intermediate
**Quick Start:** [VOLATILE_STOCKS_QUICKSTART.md](VOLATILE_STOCKS_QUICKSTART.md)
**Full Docs:** [VOLATILE_STOCKS_README.md](VOLATILE_STOCKS_README.md)

**Best For:**
- Want more trading opportunities
- Comfortable with higher volatility
- Experienced options traders
- Seeking higher profit potential

**Commands:**
```bash
python volatile_stocks_main.py --paper                      # Default tickers
python volatile_stocks_main.py --paper --tickers NVDA,TSLA  # Custom
python volatile_stocks_main.py --live                       # Live trading
```

---

### 3. Momentum Scalp Bot (Ross Cameron Style) 💰
**Strategy:** VWAP/breakout scalping on small-cap gappers (SHARES, not options)
**Difficulty:** Intermediate
**Quick Start:** [MOMENTUM_SCALP_QUICKSTART.md](MOMENTUM_SCALP_QUICKSTART.md)

**Best For:**
- Small accounts ($1K-$10K)
- Want fast scalps on momentum stocks
- Comfortable with volatile small caps
- Trading Terminal / scanner users

**Commands:**
```bash
python momentum_scalp_main.py --paper                     # Auto-scan for gappers
python momentum_scalp_main.py --paper --tickers ABCD,XYZ  # Manual tickers
python momentum_scalp_main.py --live                      # Live trading
```

---

### 4. Tradovate Micro Futures Bot 📈
**Strategy:** Tick-based momentum on MES, MNQ futures
**Difficulty:** Advanced
**Quick Start:** [README.md](README.md) (original)
**Full Docs:** [README.md](README.md)

**Best For:**
- Futures traders
- Need 24/5 trading
- Want leverage
- Low capital requirements

**Commands:**
```bash
python main_application.py --setup    # First time
python main_application.py --demo     # Demo trading
python main_application.py --live     # Live trading
```

---

## 🎯 Which Bot Should I Use?

### Quick Decision Tree

```
START HERE
    |
    ├─> New to algorithmic trading?
    |   └─> YES → SPY 0DTE Options Bot (easiest)
    |   └─> NO → Continue...
    |
    ├─> Want to trade options or futures?
    |   ├─> OPTIONS → Continue...
    |   └─> FUTURES → Tradovate Micro Futures Bot
    |
    ├─> Prefer one ticker or multiple?
    |   ├─> ONE TICKER → SPY 0DTE Options Bot
    |   └─> MULTIPLE → Volatile Stocks Bot
    |
    └─> Risk tolerance?
        ├─> LOW/MEDIUM → SPY Bot
        └─> MEDIUM/HIGH → Volatile Stocks Bot
```

### Detailed Comparison

See **[BOT_COMPARISON.md](BOT_COMPARISON.md)** for full head-to-head comparison of SPY vs Volatile Stocks bots.

---

## 📚 Documentation Structure

### Schwab Options Bots (0DTE)
```
SPY Bot:
├── SPY_QUICKSTART.md           ← START HERE (quick reference)
├── README.md                   ← Full documentation
├── schwab_0dte_main.py        ← Entry point
└── schwab_0dte_bot.py         ← Strategy code

Volatile Stocks Bot:
├── VOLATILE_STOCKS_QUICKSTART.md  ← START HERE (quick reference)
├── VOLATILE_STOCKS_README.md      ← Full documentation
├── volatile_stocks_main.py        ← Entry point
└── volatile_stocks_0dte_bot.py   ← Strategy code

Shared:
├── schwab_config_manager.py   ← Credentials (both bots)
├── BOT_COMPARISON.md          ← SPY vs Volatile comparison
└── compare_signal_methods.py  ← Educational tool
```

### Futures Bot
```
Tradovate Micro Futures:
├── README.md                  ← Full documentation
├── main_application.py        ← Entry point
├── tradovate_api_client.py   ← API client
└── momentum_strategy.py       ← Strategy code
```

---

## 🚀 Getting Started (First Time)

### Step 1: Choose Your Bot
Use the decision tree above or read [BOT_COMPARISON.md](BOT_COMPARISON.md).

**Recommendation for beginners:** Start with **SPY 0DTE Options Bot**

### Step 2: Setup Credentials

**For Schwab Options Bots (SPY or Volatile Stocks):**
```bash
python schwab_0dte_main.py --setup
```
Follow the interactive wizard. You'll need:
- Schwab API Client ID
- Schwab API Client Secret
- Complete OAuth flow in browser

**For Tradovate Futures Bot:**
```bash
python main_application.py --setup
```
You'll need:
- Tradovate username
- Tradovate password
- Tradovate API credentials

### Step 3: Paper Trade
Always start with paper trading to learn the bot's behavior.

**SPY Bot:**
```bash
python schwab_0dte_main.py --paper
```

**Volatile Stocks Bot:**
```bash
python volatile_stocks_main.py --paper
```

**Futures Bot:**
```bash
python main_application.py --demo
```

### Step 4: Monitor & Learn
Watch the bot for 1-2 weeks in paper mode:
- How often do signals trigger?
- What's the win rate?
- How do exits work?
- What are typical P&Ls?

### Step 5: Go Live (When Ready)
Only after you're comfortable with the bot's behavior:

```bash
# SPY Bot
python schwab_0dte_main.py --live

# Volatile Stocks Bot
python volatile_stocks_main.py --live

# Futures Bot
python main_application.py --live
```

**Start with 1 contract** and scale up slowly!

---

## 📖 Recommended Reading Order

### Complete Beginner
1. [SPY_QUICKSTART.md](SPY_QUICKSTART.md) - Read this first
2. [README.md](README.md) - Schwab section only
3. Paper trade SPY bot for 2 weeks
4. [BOT_COMPARISON.md](BOT_COMPARISON.md) - Compare bots
5. Consider expanding to Volatile Stocks bot

### Options Trading Experience
1. [BOT_COMPARISON.md](BOT_COMPARISON.md) - Compare strategies
2. [SPY_QUICKSTART.md](SPY_QUICKSTART.md) - Learn the basics
3. [VOLATILE_STOCKS_QUICKSTART.md](VOLATILE_STOCKS_QUICKSTART.md) - Advanced
4. [compare_signal_methods.py](compare_signal_methods.py) - Run this to understand
5. Paper trade both bots to compare

### Futures Trader
1. [README.md](README.md) - Original documentation
2. Set up Tradovate credentials
3. Demo trade to learn
4. Consider options bots for diversification

---

## 🔧 Configuration Files

### Schwab Options Bots
**Location:** `~/.schwab_0dte_bot/`

```bash
~/.schwab_0dte_bot/
├── config.yaml           # SPY bot settings
├── .credentials.enc      # Encrypted credentials (both bots)
└── .key                  # Encryption key
```

**Edit SPY bot config:**
```bash
nano ~/.schwab_0dte_bot/config.yaml
```

**Edit Volatile bot config:**
```bash
nano volatile_stocks_0dte_bot.py
# See lines 38-95 (VolatileStockConfig class)
```

### Futures Bot
**Location:** Project directory

```bash
./
├── tradovate_credentials.yaml  # Futures bot credentials
└── strategy_config.json        # Futures bot settings
```

---

## 🎓 Learning Resources

### Educational Tools
- **[compare_signal_methods.py](compare_signal_methods.py)** - Shows why percentage vs dollar signals
  ```bash
  python compare_signal_methods.py
  ```

### Video Tutorials (Community)
- Creating YouTube tutorials? Add them here via PR!

### Community
- GitHub Issues: Report bugs or request features
- Discussions: Share strategies and optimizations

---

## ⚠️ Risk Warnings

### All Bots
- **High Risk:** Can lose your entire investment
- **Paper Trade First:** Never start with live money
- **Position Sizing:** Start with 1 contract
- **Stop Losses:** Always active, but can fail in gaps
- **Market Hours:** Options expire worthless at 4 PM
- **Technical Issues:** Internet outage = stranded positions

### Specific Warnings

**0DTE Options (SPY & Volatile Stocks Bots):**
- Options can expire worthless in hours
- Theta decay accelerates near close
- Spreads widen in low liquidity
- Single-day expiration = no overnight recovery

**Futures (Tradovate Bot):**
- Leverage can amplify losses
- 24-hour markets = overnight gaps
- Margin calls possible
- News events can cause extreme volatility

**ONLY TRADE WITH MONEY YOU CAN AFFORD TO LOSE COMPLETELY**

---

## 🛠️ Troubleshooting

### Issue: Bot not taking trades
**For SPY/Volatile bots:** See quickstart guides:
- [SPY_QUICKSTART.md](SPY_QUICKSTART.md#-troubleshooting)
- [VOLATILE_STOCKS_QUICKSTART.md](VOLATILE_STOCKS_QUICKSTART.md#-troubleshooting)

**For Futures bot:** See [README.md](README.md#troubleshooting)

### Issue: Credentials expired
**Schwab:** Refresh tokens expire after 7 days inactivity
```bash
python schwab_0dte_main.py --setup  # Re-run setup
```

**Tradovate:** Tokens expire after session
```bash
python main_application.py --setup  # Re-authenticate
```

### Issue: Orders not filling
Check quickstart guides for order management settings:
- Increase chase attempts
- Use more aggressive limit pricing
- Check spread widening (might be near close)

---

## 📊 Performance Tracking

### Recommended Metrics
Track these for all bots:
- **Win Rate:** % of profitable trades
- **Avg Win / Avg Loss Ratio:** >1.5:1 is good
- **Expectancy:** (Win% × Avg Win) - (Loss% × Avg Loss)
- **Max Drawdown:** Worst losing streak
- **Sharpe Ratio:** Risk-adjusted returns

### Logging to File
```bash
# SPY Bot
python schwab_0dte_main.py --live --log-file spy_$(date +%Y%m%d).log

# Volatile Stocks Bot
python volatile_stocks_main.py --live 2>&1 | tee volatile_$(date +%Y%m%d).log

# Futures Bot
python main_application.py --live --log-file futures_$(date +%Y%m%d).log
```

### Analysis Tools
- Parse logs for trades
- Calculate metrics in spreadsheet
- Track per-ticker performance (Volatile bot)
- Compare bot performance head-to-head

---

## 🤝 Contributing

Contributions welcome! Areas of interest:
- Additional strategy implementations
- Performance optimizations
- Better risk management
- Documentation improvements
- Bug fixes

See individual bot documentation for code structure.

---

## 📞 Quick Reference - All Bots

```bash
# SPY 0DTE OPTIONS BOT
python schwab_0dte_main.py --setup     # Initial setup
python schwab_0dte_main.py --show      # Show config
python schwab_0dte_main.py --paper     # Paper trade
python schwab_0dte_main.py --live      # Live trade

# VOLATILE STOCKS 0DTE OPTIONS BOT
python volatile_stocks_main.py --paper                      # Paper (default)
python volatile_stocks_main.py --paper --tickers NVDA       # Single ticker
python volatile_stocks_main.py --paper --tickers NVDA,TSLA  # Custom list
python volatile_stocks_main.py --live                       # Live trade

# TRADOVATE MICRO FUTURES BOT
python main_application.py --setup     # Initial setup
python main_application.py --demo      # Demo account
python main_application.py --live      # Live trade

# UTILITIES
python compare_signal_methods.py      # Educational tool
```

---

## 📝 License

See individual bot files for license information.

---

## 🎯 Quick Navigation

| Document | Purpose |
|----------|---------|
| **[INDEX.md](INDEX.md)** | This file - master navigation |
| **[BOT_COMPARISON.md](BOT_COMPARISON.md)** | Compare SPY vs Volatile bots |
| **[SPY_QUICKSTART.md](SPY_QUICKSTART.md)** | SPY bot quick reference |
| **[VOLATILE_STOCKS_QUICKSTART.md](VOLATILE_STOCKS_QUICKSTART.md)** | Volatile bot quick reference |
| **[VOLATILE_STOCKS_README.md](VOLATILE_STOCKS_README.md)** | Volatile bot full docs |
| **[README.md](README.md)** | Original futures bot + Schwab section |
| **[compare_signal_methods.py](compare_signal_methods.py)** | Educational tool |

---

**Last Updated:** 2026-01-27
**Repository Version:** Multi-Bot v2.0

**Get Started Now:** Choose your bot above and jump to the quickstart guide! 🚀
