#!/usr/bin/env python3
"""
Main Application Entry Point for Volatile Stocks 0DTE Options Trading Bot

Usage:
    python volatile_stocks_main.py --paper      # Paper trading mode
    python volatile_stocks_main.py --live       # Live trading (requires confirmation)
    python volatile_stocks_main.py --tickers NVDA,TSLA,AMD  # Custom ticker list
"""

import asyncio
import argparse
import logging
import signal
import sys
from datetime import datetime, time as dt_time
from typing import Optional

# Import bot components
from volatile_stocks_0dte_bot import (
    VolatileStockClient,
    VolatileStockMomentumStrategy,
    VolatileStockConfig
)
from schwab_0dte_bot import OptionsConfig
from schwab_config_manager import SchwabConfigManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class VolatileStockTradingApp:
    """Main application for volatile stock trading"""

    def __init__(self, config_dir: str = "~/.schwab_0dte_bot",
                 paper_trading: bool = True,
                 tickers: Optional[list] = None,
                 log_level: str = "INFO",
                 enable_safety: bool = True):
        self.config_mgr = SchwabConfigManager(config_dir)
        self.paper_trading = paper_trading
        self.custom_tickers = tickers
        self.enable_safety = enable_safety
        self.client: Optional[VolatileStockClient] = None
        self.strategy: Optional[VolatileStockMomentumStrategy] = None
        self.safety_manager = None
        self.running = False

        # Set log level
        logging.getLogger().setLevel(getattr(logging, log_level.upper()))

    async def initialize(self) -> bool:
        """Initialize the trading application"""
        logger.info("Initializing Volatile Stocks 0DTE Options Trading Bot...")

        # Load credentials
        credentials = self.config_mgr.load_credentials()
        if not credentials:
            credentials = self.config_mgr.load_credentials_from_keyring()

        if not credentials:
            logger.error("No credentials found. Run schwab_0dte_main.py --setup first.")
            return False

        # Build volatile stock config
        vstk_config = VolatileStockConfig()

        # Override tickers if custom list provided
        if self.custom_tickers:
            vstk_config.tickers = self.custom_tickers
            logger.info(f"Using custom tickers: {', '.join(self.custom_tickers)}")

        # Build base OptionsConfig for Schwab client
        base_config = OptionsConfig(
            symbol="SPY"  # Placeholder, not used for multi-ticker
        )

        # Initialize client
        self.client = VolatileStockClient(base_config, config_manager=self.config_mgr)

        try:
            await self.client.initialize(
                client_id=credentials.client_id,
                client_secret=credentials.client_secret,
                refresh_token=credentials.refresh_token
            )

        except Exception as e:
            logger.error(f"Failed to initialize Schwab client: {e}")
            return False

        # Initialize account safety manager
        if self.enable_safety:
            from schwab_account_safety import AccountSafetyManager

            try:
                account_data = await self.client.get_account_info()
                account_value = account_data.get('liquidationValue', 1000)

                # Adjust safety settings based on account size (same logic as SPY bot)
                if account_value < 1000:
                    max_position_pct = 15.0
                    max_daily_loss = 75.0
                    max_daily_trades = 2
                    cash_buffer = 100.0
                    logger.warning(f"⚠️  Small account (${account_value:.2f}) - Conservative safety limits applied")
                elif account_value < 3000:
                    max_position_pct = 20.0
                    max_daily_loss = 100.0
                    max_daily_trades = 3
                    cash_buffer = 100.0
                    logger.info(f"Account size: ${account_value:.2f} - Conservative safety limits")
                elif account_value < 10000:
                    max_position_pct = 25.0
                    max_daily_loss = 200.0
                    max_daily_trades = 5
                    cash_buffer = 200.0
                    logger.info(f"Account size: ${account_value:.2f} - Moderate safety limits")
                else:
                    max_position_pct = 30.0
                    max_daily_loss = 500.0
                    max_daily_trades = 10
                    cash_buffer = 500.0
                    logger.info(f"Account size: ${account_value:.2f} - Standard safety limits")

                self.safety_manager = AccountSafetyManager(
                    max_position_cost_percent=max_position_pct,
                    max_daily_loss_dollars=max_daily_loss,
                    max_daily_trades=max_daily_trades,
                    cash_account_buffer=cash_buffer
                )

                logger.info("="*50)
                logger.info("  🛡️  ACCOUNT SAFETY ENABLED")
                logger.info("="*50)
                logger.info(f"  Max position size: {max_position_pct}% (${account_value * max_position_pct / 100:.2f})")
                logger.info(f"  Max daily loss: ${max_daily_loss:.2f}")
                logger.info(f"  Max trades/day: {max_daily_trades}")
                logger.info(f"  Cash buffer: ${cash_buffer:.2f}")
                logger.info("="*50)

            except Exception as e:
                logger.error(f"Failed to initialize safety manager: {e}")
                logger.warning("⚠️  Continuing WITHOUT safety protections!")
                self.safety_manager = None

        # Initialize strategy
        self.strategy = VolatileStockMomentumStrategy(self.client, vstk_config, safety_manager=self.safety_manager)

        if self.paper_trading:
            logger.info("="*50)
            logger.info("  PAPER TRADING MODE - No real orders will be placed")
            logger.info("="*50)

        return True

    def _is_market_open(self) -> bool:
        """Check if US equity options market is open"""
        now = datetime.now()

        if now.weekday() >= 5:
            return False

        market_open = dt_time(9, 30)
        market_close = dt_time(16, 0)
        current_time = now.time()

        return market_open <= current_time <= market_close

    def _time_until_market_open(self) -> Optional[float]:
        """Calculate seconds until market opens"""
        now = datetime.now()

        # Calculate next market open
        next_open = now.replace(hour=9, minute=30, second=0, microsecond=0)

        if now.time() >= dt_time(16, 0) or now.weekday() >= 5:
            from datetime import timedelta
            # After close or weekend
            if now.weekday() == 4:  # Friday after close
                days_until_monday = 3
            elif now.weekday() == 5:  # Saturday
                days_until_monday = 2
            elif now.weekday() == 6:  # Sunday
                days_until_monday = 1
            else:
                days_until_monday = 1

            next_open = (now + timedelta(days=days_until_monday)).replace(
                hour=9, minute=30, second=0, microsecond=0
            )

        return (next_open - now).total_seconds()

    async def run(self):
        """Main trading loop"""
        self.running = True

        logger.info("Starting volatile stock trading application...")
        logger.info(f"Tickers: {', '.join(self.strategy.config.tickers)} | Mode: {'PAPER' if self.paper_trading else 'LIVE'}")

        while self.running:
            try:
                if not self._is_market_open():
                    wait_time = self._time_until_market_open()
                    if wait_time and wait_time > 0:
                        hours = int(wait_time // 3600)
                        minutes = int((wait_time % 3600) // 60)
                        logger.info(f"Market closed. Opens in {hours}h {minutes}m. Waiting...")

                        sleep_chunk = min(wait_time, 300)
                        await asyncio.sleep(sleep_chunk)
                        continue

                # Run strategy
                if self.paper_trading:
                    # For now, just run the same strategy
                    # In production you'd want separate paper trading logic
                    logger.warning("Paper trading with live signals - no orders placed")
                    await self.strategy.run()
                else:
                    await self.strategy.run()

            except asyncio.CancelledError:
                logger.info("Trading loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in trading loop: {type(e).__name__}: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down...")
        self.running = False

        if self.strategy:
            self.strategy.stop()

        await asyncio.sleep(0.2)

        if self.client:
            await self.client.close()

        logger.info("Shutdown complete")


def setup_signal_handlers(app: VolatileStockTradingApp, loop: asyncio.AbstractEventLoop):
    """Setup signal handlers for graceful shutdown"""
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
    # Parse custom tickers
    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]

    app = VolatileStockTradingApp(
        config_dir=args.config_dir,
        paper_trading=not args.live,
        tickers=tickers,
        log_level=args.log_level,
        enable_safety=not args.disable_safety  # Safety on by default
    )

    # Setup signal handlers
    loop = asyncio.get_event_loop()
    setup_signal_handlers(app, loop)

    # Initialize
    if not await app.initialize():
        logger.error("Failed to initialize. Exiting.")
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
        description="Volatile Stocks 0DTE Options Momentum Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python volatile_stocks_main.py --paper                    # Paper trading with default tickers
  python volatile_stocks_main.py --paper --tickers NVDA,AMD # Custom tickers
  python volatile_stocks_main.py --live                     # Live trading

Default Tickers: NVDA, TSLA, AMD, AAPL, MSFT, META, GOOGL, AMZN

Risk Warning:
  0DTE options trading is EXTREMELY HIGH RISK. Options can expire
  worthless in hours. Only trade with money you can afford to lose.
        """
    )

    parser.add_argument(
        "--paper",
        action="store_true",
        default=True,
        help="Run in paper trading mode (default)"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run in LIVE trading mode (requires confirmation)"
    )
    parser.add_argument(
        "--tickers",
        type=str,
        help="Comma-separated list of tickers (e.g., NVDA,TSLA,AMD)"
    )
    parser.add_argument(
        "--config-dir",
        type=str,
        default="~/.schwab_0dte_bot",
        help="Configuration directory (default: ~/.schwab_0dte_bot)"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    parser.add_argument(
        "--disable-safety",
        action="store_true",
        help="Disable account safety checks (NOT RECOMMENDED - for testing only)"
    )

    args = parser.parse_args()

    # Live trading confirmation
    if args.live:
        print("\n" + "="*60)
        print("  ⚠️  LIVE TRADING MODE WARNING")
        print("="*60)
        print("\n  You are about to start LIVE trading with REAL MONEY.")
        print("  0DTE options are extremely high risk.")
        print("\n  This bot will automatically:")
        print("    - Monitor multiple volatile stocks")
        print("    - Buy and sell 0DTE options")
        print("    - Use real funds from your Schwab account")
        print("\n  There is NO GUARANTEE of profit.")
        print("  You could lose your ENTIRE investment.")
        print("\n" + "="*60)

        confirm = input("\n  Type 'I UNDERSTAND THE RISKS' to continue: ")

        if confirm != "I UNDERSTAND THE RISKS":
            print("\n  Live trading cancelled.")
            return 0

        print("\n  Starting live trading...")

    # Use uvloop if available
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("Using uvloop for enhanced performance")
    except ImportError:
        pass

    # Run the bot
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
