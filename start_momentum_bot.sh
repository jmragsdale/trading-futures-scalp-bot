#!/bin/bash
# Momentum Scalp Bot — Daily Launcher
# Started by LaunchAgent at 7:00 AM ET on weekdays

BOT_DIR="/Users/jermaineragsdale/Documents/jmragsdale/trading-futures-scalp-bot"
LOG_DIR="$BOT_DIR/logs"
VENV="$BOT_DIR/venv/bin/python"
LOG_FILE="$LOG_DIR/momentum_$(date +%Y%m%d).log"

# Create logs dir
mkdir -p "$LOG_DIR"

# Kill any existing instance
pkill -f "momentum_scalp_main.py" 2>/dev/null
sleep 1

echo "$(date): Starting Momentum Scalp Bot (paper mode)" >> "$LOG_FILE"

# Run the bot — exits after market close
cd "$BOT_DIR"
exec "$VENV" momentum_scalp_main.py --paper >> "$LOG_FILE" 2>&1
