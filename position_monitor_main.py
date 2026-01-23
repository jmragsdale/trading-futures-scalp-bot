#!/usr/bin/env python3
"""
Position Monitor Main Entry Point

A simplified runner for the Tradovate position monitor bot.
Monitors manually-entered positions and manages stops/targets automatically.

Usage:
    python position_monitor_main.py              # Demo mode (default)
    python position_monitor_main.py --live       # Live trading
    python position_monitor_main.py --setup      # First-time setup
    python position_monitor_main.py --show       # Show configuration
"""

import asyncio
import argparse
import logging
import signal
import sys
from typing import Optional

from tradovate_position_monitor import (
    PositionMonitorApp,
    MonitorConfig
)
from config_manager import (
    ConfigManager,
    TradovateCredentials,
    setup_credentials_interactive
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def show_config():
    """Display current configuration"""
    config_mgr = ConfigManager()
    credentials = config_mgr.load_credentials()

    print("\n" + "=" * 60)
    print("  POSITION MONITOR CONFIGURATION")
    print("=" * 60)

    if credentials:
        print(f"\n  Tradovate Username: {credentials.username}")
        print(f"  App ID: {credentials.app_id}")
        print(f"  App Version: {credentials.app_version}")
    else:
        print("\n  No credentials found. Run with --setup first.")

    print("\n  Default Settings:")
    print("  -----------------")
    print("  Symbol: MES")
    print("  EMA Period: 20")
    print("  Stop Offset: 4 ticks")
    print("  Breakeven Trigger: 3R")
    print("  Take Profit: 2.5R")
    print("  Webhook Port: 5000")
    print("\n" + "=" * 60)


def setup_signal_handlers(app: PositionMonitorApp, loop: asyncio.AbstractEventLoop):
    """Setup graceful shutdown handlers"""
    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(app.shutdown())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            signal.signal(sig, lambda s, f: signal_handler())


async def main_async(args):
    """Async main entry point"""

    # Load credentials
    config_mgr = ConfigManager()
    credentials = config_mgr.load_credentials()

    if not credentials:
        credentials = config_mgr.load_credentials_from_keyring()

    if not credentials:
        logger.error("No credentials found. Run with --setup first.")
        return 1

    # Build configuration
    config = MonitorConfig(
        symbol=args.symbol,
        ema_length=args.ema,
        stop_offset_ticks=args.stop_offset,
        breakeven_r=args.be_r,
        take_profit_r=args.tp_r,
        webhook_port=args.port,
        demo_mode=not args.live
    )

    # Initialize app
    app = PositionMonitorApp(config)

    # Setup signal handlers
    loop = asyncio.get_event_loop()
    setup_signal_handlers(app, loop)

    # Initialize
    if not await app.initialize(
        credentials.username,
        credentials.password,
        credentials.app_id,
        credentials.app_version
    ):
        logger.error("Failed to initialize. Check credentials and connection.")
        return 1

    # Run
    try:
        await app.run()
    except KeyboardInterrupt:
        pass
    finally:
        await app.shutdown()

    return 0


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Tradovate Position Monitor - Auto-manage stops and targets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python position_monitor_main.py              # Start in demo mode
  python position_monitor_main.py --live       # Start in live mode
  python position_monitor_main.py --symbol MNQ # Monitor MNQ instead of MES
  python position_monitor_main.py --ema 10     # Use EMA(10) for stops
  python position_monitor_main.py --be-r 2.0   # Breakeven at 2R instead of 3R

TradingView Webhook Format:
  POST http://your-server:5000/webhook
  Body: {"alert_type": "breakeven"} or {"alert_type": "stop_out"} or {"alert_type": "timeout"}
        """
    )

    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run interactive credential setup"
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show current configuration"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run in LIVE mode (default: demo)"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="MES",
        help="Futures contract symbol (default: MES)"
    )
    parser.add_argument(
        "--ema",
        type=int,
        default=20,
        help="EMA period for stop calculation (default: 20)"
    )
    parser.add_argument(
        "--stop-offset",
        type=int,
        default=4,
        help="Stop offset in ticks beyond EMA (default: 4)"
    )
    parser.add_argument(
        "--be-r",
        type=float,
        default=3.0,
        help="R-multiple to trigger breakeven (default: 3.0)"
    )
    parser.add_argument(
        "--tp-r",
        type=float,
        default=2.5,
        help="R-multiple for take profit (default: 2.5)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Webhook server port (default: 5000)"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )

    args = parser.parse_args()

    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level.upper()))

    # Handle setup
    if args.setup:
        setup_credentials_interactive()
        return 0

    # Handle show config
    if args.show:
        show_config()
        return 0

    # Live trading confirmation
    if args.live:
        print("\n" + "=" * 60)
        print("  LIVE TRADING MODE WARNING")
        print("=" * 60)
        print("\n  This will manage REAL positions with REAL money.")
        print("  The bot will:")
        print("    - Place and modify stop orders automatically")
        print("    - Close positions at take profit targets")
        print("    - React to TradingView webhook alerts")
        print("\n  Make sure you understand the risks.")
        print("=" * 60)

        confirm = input("\n  Type 'I UNDERSTAND' to continue: ")
        if confirm != "I UNDERSTAND":
            print("\n  Live trading cancelled.")
            return 0

        print("\n  Starting live position monitor...")

    # Use uvloop if available
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("Using uvloop for enhanced performance")
    except ImportError:
        pass

    # Run
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
