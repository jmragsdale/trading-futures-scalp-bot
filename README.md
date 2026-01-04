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
