#!/bin/bash
# Tradovate REST Bot Launcher

cd /Users/jermaineragsdale/Documents/jmragsdale/trading-futures-scalp-bot

# Activate virtual environment
source venv/bin/activate

# Create logs directory
mkdir -p logs

# Set unbuffered output
export PYTHONUNBUFFERED=1

echo "🚀 Starting Tradovate REST Bot"
echo "Account: DEMO4600924 ($49,870.78)"
echo "Symbol: MES"
echo ""
echo "Press Ctrl+C to stop"
echo "=========================="
echo ""

# Run the bot (unbuffered)
python -u tradovate_rest_bot.py 2>&1 | tee -a logs/tradovate_rest_$(date +%Y%m%d).log
