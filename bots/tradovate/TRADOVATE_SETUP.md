# Tradovate Futures Bot Setup Guide

## 🎯 What You Need

To get the Tradovate momentum bot running, I need the following credentials from you:

---

## 📋 Required Information

### 1. **Tradovate Account Credentials**

**For Demo/Paper Trading:**
- [ ] Demo account username
- [ ] Demo account password
- [ ] App ID (from Tradovate developer portal)
- [ ] App version

**For Live Trading (after testing):**
- [ ] Live account username  
- [ ] Live account password
- [ ] App ID
- [ ] App version

---

### 2. **Tradovate API Access Setup**

**Steps to get API credentials:**

1. **Go to Tradovate Developer Portal:**
   - Demo: https://demo.tradovate.com/
   - Live: https://trader.tradovate.com/

2. **Create API Application:**
   - Settings → API Apps → Create New App
   - App Name: "Momentum Scalp Bot"
   - App Version: "1.0"
   - Copy your **App ID** and **App Secret** (if required)

3. **Enable API Access:**
   - Make sure "Market Data" and "Trading" permissions are enabled

---

## 🔧 What I'll Do Once You Provide Credentials

### Step 1: Add credentials to `.env` file
```bash
# Tradovate API (Demo)
TRADOVATE_DEMO_USERNAME=your_demo_username
TRADOVATE_DEMO_PASSWORD=your_demo_password
TRADOVATE_DEMO_APP_ID=your_app_id
TRADOVATE_DEMO_APP_VERSION=1.0

# Tradovate API (Live - leave empty for now)
TRADOVATE_LIVE_USERNAME=
TRADOVATE_LIVE_PASSWORD=
TRADOVATE_LIVE_APP_ID=
TRADOVATE_LIVE_APP_VERSION=
```

### Step 2: Create launcher script
I'll create `start_tradovate_bot.sh` with proper configuration.

### Step 3: Test connection
Run a test to verify API access and account connection.

### Step 4: Configure strategy
Set up the momentum parameters for your account size and risk tolerance.

---

## 📊 Current Bot Configuration

**Strategy (from `tradovate_momentum_bot.py`):**
- **Time Window:** 14 seconds
- **Min Price Movement:** 7 ticks
- **Max Positions:** 1
- **Take Profit:** 25 ticks
- **Stop Loss:** 12 ticks
- **Trailing Stop:** 6 ticks

**Supported Instruments:**
- MES (Micro E-mini S&P 500)
- MNQ (Micro E-mini Nasdaq)
- MYM (Micro E-mini Dow)
- M2K (Micro E-mini Russell 2000)

**Default Instrument:** MESZ24 (MES December 2024 contract)

---

## 🚀 Quick Start Commands (After Setup)

### Demo/Paper Trading:
```bash
cd /Users/jermaineragsdale/Documents/jmragsdale/trading-futures-scalp-bot
source venv/bin/activate
python tradovate_momentum_bot.py --demo --symbol MES
```

### Live Trading (After testing):
```bash
python tradovate_momentum_bot.py --live --symbol MES
```

---

## ⚙️ Optional: Strategy Customization

**If you want to adjust the strategy, let me know:**

1. **Account Size:** What's your starting capital?
2. **Risk per Trade:** What % of account are you comfortable risking?
3. **Instruments:** MES, MNQ, or both?
4. **Trading Hours:** Specific hours you want to trade?
5. **Max Daily Loss:** Stop trading after X loss?

---

## 📝 What to Send Me

**Reply with:**

```
Demo Username: _______
Demo Password: _______
App ID: _______
App Version: 1.0

Account Size: $_______
Risk per Trade: ____%
Preferred Instrument: MES / MNQ / both
```

**Optional (for customization):**
- Max positions at once: 1 (default) or more?
- Take profit target: 25 ticks (default) or adjust?
- Stop loss: 12 ticks (default) or adjust?

---

## 🛡️ Safety Features Already Built In

✅ Position limits (max 1 concurrent)  
✅ Stop loss on every trade (12 ticks)  
✅ Take profit targets (25 ticks)  
✅ Trailing stops (6 ticks)  
✅ Slippage protection  
✅ Order timeout (2 seconds)  
✅ Demo mode for testing  

---

## 🔍 Compatibility Check

**Your Current Displacement Strategy:**
- You're trading MNQ on 1m/2m charts
- Using displacement zones + refills
- Targeting 2:1 R/R

**This Momentum Bot:**
- Different strategy (tick-based momentum, not displacement)
- Much faster timeframe (14-second windows)
- Lower R/R but higher frequency
- Could complement your displacement trades

**Recommendation:** Run this in DEMO first to see if you like the style. It's more scalp-heavy vs. your current swing-style displacement trades.

---

## ❓ Questions?

Let me know if you need help with:
- Getting Tradovate API access
- Understanding the strategy differences
- Adjusting parameters
- Setting up alerts/notifications

Once you provide credentials, I'll have you up and running in ~10 minutes.
