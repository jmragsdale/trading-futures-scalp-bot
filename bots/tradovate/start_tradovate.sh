#!/bin/bash
# Tradovate Momentum Bot Launcher

cd /Users/jermaineragsdale/Documents/jmragsdale/trading-futures-scalp-bot

# Activate virtual environment
source venv/bin/activate

# Set environment variables
export PYTHONUNBUFFERED=1

# Check if symbol is provided
SYMBOL=${1:-MES}

echo "🚀 Starting Tradovate Momentum Bot"
echo "Account: DEMO4600924"
echo "Balance: \$49,870.78"
echo "Symbol: $SYMBOL"
echo "Mode: DEMO"
echo ""
echo "Press Ctrl+C to stop"
echo "=========================="
echo ""

# Run the bot
python tradovate_momentum_bot.py \
    --demo \
    --symbol "$SYMBOL" \
    2>&1 | tee -a logs/tradovate_$(date +%Y%m%d).log
