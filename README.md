# Tradovate Micro Futures High-Performance Trading Bot

A production-ready, high-performance momentum trading system for Tradovate micro futures, optimized for ultra-low latency execution and comprehensive risk management.

## 🚀 Key Features

- **Ultra-Low Latency**: Sub-millisecond order execution using asyncio and websockets
- **Momentum Strategy**: Detects rapid price movements (7+ ticks in 14 seconds)
- **Risk Management**: Multiple safety layers including stop-loss, take-profit, and trailing stops
- **Performance Monitoring**: Real-time metrics, P&L tracking, and execution quality analysis
- **Micro Futures Optimized**: Specifically designed for MES, MNQ, MYM, M2K contracts
- **Production Ready**: Comprehensive error handling, logging, and failover mechanisms

## 📊 Strategy Overview

The bot implements a momentum-based scalping strategy adapted from the MQL4 Cash-profit algorithm:

- **Entry Signal**: Price movement ≥7 ticks within 14-second window
- **Exit Logic**: 
  - Take Profit: 22 ticks
  - Stop Loss: 10 ticks
  - Trailing Stop: 5 ticks (activates after profit)
- **Position Management**: Maximum 1 concurrent position
- **Risk Control**: Position sizing based on account balance and risk percentage

## 🛠️ Installation

### Prerequisites

- Python 3.9 or higher
- Tradovate account with API access
- Stable internet connection with low latency to CME servers

### Setup Steps

1. **Clone the repository and install dependencies:**

```bash
# Install dependencies
pip install -r requirements.txt

# For optimal performance on Linux/Mac:
pip install uvloop  # Faster event loop
```

2. **Configure credentials (interactive setup):**

```bash
python main_application.py --setup
```

This will prompt you to enter:
- Tradovate username and password
- App ID and version (from Tradovate API dashboard)
- Optional API key and secret

3. **Customize strategy parameters:**

Edit the configuration file created at `~/.tradovate_bot/config.yaml`:

```yaml
strategy:
  time_window_seconds: 14
  min_price_movement_ticks: 7
  take_profit_ticks: 22
  stop_loss_ticks: 10
  trailing_stop_ticks: 5
  max_positions: 1
  risk_percent: 120.0
  
contract:
  symbol: MES
  tick_size: 0.25
  tick_value: 1.25
  margin_requirement: 1320.0
  
environment:
  demo_mode: true  # Start with demo!
  log_level: INFO
```

## 🎮 Usage

### Basic Usage (Demo Mode)

```bash
# Run with default settings (MES, demo mode)
python main_application.py

# Run with specific symbol
python main_application.py --symbol MNQ

# Enable detailed logging
python main_application.py --log-level DEBUG --log-file trading.log
```

### Production Usage (Live Trading)

⚠️ **WARNING**: Live trading involves real money and risk. Test thoroughly in demo mode first!

```bash
# Switch to live trading (will require confirmation)
python main_application.py --live

# Live trading with position cleanup on exit
python main_application.py --live --close-on-exit

# Dry run mode (no orders placed)
python main_application.py --dry-run
```

## 📈 Supported Micro Futures

| Symbol | Product | Tick Size | Tick Value | Margin* |
|--------|---------|-----------|------------|---------|
| MES | Micro E-mini S&P 500 | 0.25 | $1.25 | ~$1,320 |
| MNQ | Micro E-mini Nasdaq-100 | 0.25 | $0.50 | ~$1,760 |
| MYM | Micro E-mini Dow | 1.00 | $0.50 | ~$990 |
| M2K | Micro E-mini Russell 2000 | 0.10 | $0.50 | ~$880 |
| MGC | Micro Gold | 0.10 | $1.00 | ~$1,100 |

*Margin requirements are approximate and subject to change

## 🔍 Performance Monitoring

The bot provides real-time performance metrics:

```
============================================================
           TRADING PERFORMANCE DASHBOARD
============================================================

📊 PERFORMANCE METRICS:
   Total Trades: 45
   Win Rate: 62.2%
   Profit Factor: 1.85
   Net Profit: $234.50
   Max Drawdown: -$87.00 (-4.2%)
   Sharpe Ratio: 1.43

⚡ EXECUTION QUALITY:
   Avg Latency Ms: 12.3
   Max Latency Ms: 45.7
   Ticks Per Second: 987

⚠️  RISK STATUS:
   Daily PnL: $234.50
   Trades Today: 45
   Open Positions: 1
 ✅ Trading Allowed: True
============================================================
```

## ⚙️ Architecture

The system consists of several modular components:

1. **tradovate_momentum_bot.py**: Core trading logic and Tradovate API client
2. **config_manager.py**: Secure credential storage and configuration management
3. **performance_monitor.py**: Real-time metrics and risk management
4. **main_application.py**: Application lifecycle and orchestration

### Performance Optimizations

- **Asyncio/Websockets**: Non-blocking I/O for maximum throughput
- **Connection Pooling**: Reuses HTTP connections for API calls
- **Message Queue**: Buffers market data to prevent loss during processing
- **Minimal Latency**: Direct market data feed without intermediaries
- **Efficient Data Structures**: Uses deques and numpy arrays for fast computations

## 🔒 Security Best Practices

1. **Never hardcode credentials** - Use the secure config manager
2. **Use demo mode first** - Test thoroughly before live trading
3. **Set up API restrictions** - Limit API keys to trading permissions only
4. **Monitor actively** - Keep the performance dashboard visible
5. **Use stop losses** - Always have risk management in place
6. **Regular backups** - Save configuration and logs regularly

## 📝 Risk Disclaimer

**IMPORTANT**: Trading futures involves substantial risk of loss and is not suitable for all investors. Past performance is not indicative of future results. The high degree of leverage can work against you as well as for you. Before trading, you should carefully consider your investment objectives, level of experience, and risk appetite.

This software is provided "as is" without warranty of any kind. The authors are not responsible for any losses incurred through the use of this software.

## 🤝 Contributing

Contributions are welcome! Please ensure any pull requests:
1. Include comprehensive tests
2. Follow PEP 8 style guidelines
3. Include documentation updates
4. Pass all existing tests

## 📄 License

This project is provided for educational purposes. Please ensure you comply with Tradovate's API terms of service and all applicable regulations.

## 🆘 Support

For issues or questions:
1. Check the logs in `~/.tradovate_bot/` directory
2. Run with `--log-level DEBUG` for detailed diagnostics
3. Ensure market is open (Sunday 6PM - Friday 5PM ET)
4. Verify API credentials are valid

## 🚦 Quick Start Checklist

- [ ] Install Python 3.9+
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Get Tradovate API credentials
- [ ] Run setup: `python main_application.py --setup`
- [ ] Test in demo mode: `python main_application.py --demo`
- [ ] Monitor performance dashboard
- [ ] Adjust parameters in config.yaml
- [ ] Paper trade for at least 1 week
- [ ] Consider live trading only after profitable demo results

Remember: Start small, test thoroughly, and never trade with money you can't afford to lose!

---

# Schwab 0DTE SPY Options Bot - Quick Start Guide

A momentum-based scalping bot for 0DTE (zero days to expiration) SPY options using the Schwab API.

## Prerequisites

- Python 3.9+
- Schwab brokerage account with options approval
- Registered app at [developer.schwab.com](https://developer.schwab.com)
- Your app's **Client ID** and **Client Secret**
- Callback URL registered as `https://127.0.0.1:8081`

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Get Your Refresh Token

Run the authentication helper to get your Schwab refresh token:

```bash
python schwab_8081_fixed.py
```

This will:
1. Prompt for your Client ID and Secret
2. Open Schwab login in your browser
3. Capture the OAuth callback automatically
4. Display your refresh token

Save the refresh token - you'll need it for setup.

### 3. Run Setup Wizard

```bash
python schwab_0dte_main.py --setup
```

Enter your credentials when prompted:
- Client ID
- Client Secret
- Redirect URI (press Enter for default `https://127.0.0.1:8081`)

### 4. Start Paper Trading

```bash
python schwab_0dte_main.py --paper
```

### 5. View Current Configuration

```bash
python schwab_0dte_main.py --show
```

## Command Reference

| Command | Description |
|---------|-------------|
| `python schwab_0dte_main.py --setup` | First-time setup wizard |
| `python schwab_0dte_main.py --paper` | Paper trading mode (default) |
| `python schwab_0dte_main.py --live` | Live trading (requires confirmation) |
| `python schwab_0dte_main.py --show` | Display current configuration |
| `python schwab_0dte_main.py --log-level DEBUG` | Enable debug logging |

## Configuration

After setup, configuration is stored in `~/.schwab_0dte_bot/config.yaml`:

```yaml
strategy:
  time_window_seconds: 14        # Momentum detection window
  min_price_movement_dollars: 0.50  # Min SPY move to trigger
  target_delta: 0.45             # Option delta target
  max_bid_ask_spread_percent: 0.08  # Max acceptable spread
  stop_loss_percent: 35.0        # Stop loss trigger
  take_profit_percent: 60.0      # Take profit trigger
  use_trailing_stop: true        # Enable trailing stop
  trailing_stop_activation: 15.0 # Activate after 15% profit
  trailing_stop_percent: 20.0    # Trail 20% below high
  no_trade_before: "09:45"       # Start trading time
  no_trade_after: "15:00"        # Stop trading time

underlying:
  symbol: SPY

environment:
  paper_trading: true
  log_level: INFO
```

## Strategy Overview

The bot monitors SPY price movements and trades 0DTE options based on momentum signals:

- **Entry**: Detects rapid price movement ($0.50+ in 14 seconds)
- **Option Selection**: Targets ~0.45 delta options with tight bid-ask spreads
- **Exit Rules**:
  - Trailing Stop: Activates at +15% profit, trails 20% below high-water mark
  - Stop Loss: -35% (fixed, fallback if trailing not active)
  - Take Profit: +60% (fixed)
  - EOD Exit: Forces close at 3:55 PM ET

## Risk Warning

**0DTE options trading is EXTREMELY HIGH RISK.** Options can expire worthless within hours. The high leverage works both ways - you can lose your entire investment quickly.

- Always start with paper trading
- Only trade with money you can afford to lose
- Monitor positions actively
- Refresh tokens expire after 7 days of inactivity

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "No credentials found" | Run `--setup` first |
| Login page won't load | Ensure callback URL is `https://127.0.0.1:8081` in Schwab developer portal |
| Token expired | Re-run `python schwab_8081_fixed.py` to get new refresh token |
| Port 8081 in use | Run `lsof -ti:8081 \| xargs kill -9` then try again |

## Files

| File | Purpose |
|------|---------|
| `schwab_0dte_main.py` | Main entry point and trading loop |
| `schwab_0dte_bot.py` | Core trading logic and Schwab API client |
| `schwab_config_manager.py` | Credential storage and configuration |
| `schwab_8081_fixed.py` | OAuth helper for getting refresh tokens |

---

# Tradovate Position Monitor Bot

A position management bot that monitors manually-entered trades and automatically manages stops and targets based on TradingView signals.

## Features

- **Manual Entry, Auto Management**: Enter trades yourself, let the bot handle stop loss and take profit
- **EMA-Based Stops**: Stop loss calculated from EMA(20) + 4 tick offset
- **R-Based Targets**: Breakeven at 3R, take profit at 2.5R
- **TradingView Integration**: Receives webhook alerts for stop out, breakeven, and timeout signals
- **Real-time Monitoring**: Tracks positions and updates stops as price moves

## Quick Start

### 1. Setup Credentials

```bash
python position_monitor_main.py --setup
```

### 2. Start Monitor (Demo Mode)

```bash
python position_monitor_main.py
```

### 3. Configure TradingView Alerts

Set up alerts in TradingView to send webhooks to:
```
http://your-server-ip:5000/webhook
```

Alert JSON format:
```json
{"alert_type": "breakeven"}
{"alert_type": "stop_out"}
{"alert_type": "timeout"}
```

## Command Reference

| Command | Description |
|---------|-------------|
| `python position_monitor_main.py` | Start in demo mode |
| `python position_monitor_main.py --live` | Start in live mode |
| `python position_monitor_main.py --setup` | Credential setup |
| `python position_monitor_main.py --show` | Show configuration |
| `python position_monitor_main.py --symbol MNQ` | Monitor MNQ |
| `python position_monitor_main.py --ema 10` | Use EMA(10) |
| `python position_monitor_main.py --be-r 2.0` | Breakeven at 2R |

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `--symbol` | MES | Futures contract to monitor |
| `--ema` | 20 | EMA period for stop calculation |
| `--stop-offset` | 4 | Ticks beyond EMA for stop |
| `--be-r` | 3.0 | R-multiple to trigger breakeven |
| `--tp-r` | 2.5 | R-multiple for take profit |
| `--port` | 5000 | Webhook server port |

## How It Works

1. **Position Detection**: When you enter a trade manually, the bot detects the new position
2. **Initial Stop**: Places a stop order at EMA(20) - 4 ticks (for longs) or EMA(20) + 4 ticks (for shorts)
3. **R-Calculation**: Calculates your risk (entry to initial stop) and R-multiples
4. **Stop Trailing**: As price moves favorably, stop trails based on EMA
5. **Breakeven**: When profit reaches 3R, stop moves to breakeven + 1 tick
6. **Take Profit**: At 2.5R profit, position is closed at market
7. **Alert Response**: TradingView webhooks can trigger immediate stop out or breakeven

## Example Session

```
============================================================
  TRADOVATE POSITION MONITOR
============================================================

  Mode: DEMO
  Symbol: MES
  EMA Period: 20
  Stop Offset: 4 ticks
  Breakeven: 3.0R
  Take Profit: 2.5R

  Webhook: http://localhost:5000/webhook

  Waiting for positions...
============================================================

2024-01-15 10:30:15 - Now tracking: LONG 1 @ 4850.25
2024-01-15 10:30:15 - Initial stop: 4847.25 | Risk: 3.00 (12 ticks)
2024-01-15 10:30:15 - BE target: 4859.25 (3.0R)
2024-01-15 10:30:15 - TP target: 4857.75 (2.5R)
2024-01-15 10:35:22 - Stop modified to 4848.50
2024-01-15 10:42:18 - R-multiple reached 3.2R - triggering breakeven
2024-01-15 10:42:18 - Moved to breakeven @ 4850.50
2024-01-15 10:48:33 - Take profit target reached (2.6R) - closing position
```

## Webhook Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhook` | POST | Receive TradingView alerts |
| `/health` | GET | Health check with current status |

### Health Check Response

```json
{
  "status": "healthy",
  "positions": 1,
  "last_price": 4855.25,
  "ema": 4852.50
}
```
