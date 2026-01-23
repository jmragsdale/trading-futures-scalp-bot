#!/usr/bin/env python3
"""
Main Application Entry Point for Schwab 0DTE Options Trading Bot

Usage:
    python schwab_0dte_main.py --setup      # First-time setup
    python schwab_0dte_main.py --paper      # Paper trading mode
    python schwab_0dte_main.py --live       # Live trading (requires confirmation)
    python schwab_0dte_main.py --show       # Show current configuration
"""

import asyncio
import argparse
import logging
import signal
import sys
from datetime import datetime, time as dt_time
from typing import Optional

# Import bot components
from schwab_0dte_bot import (
    SchwabClient,
    ZeroDTEMomentumStrategy,
    OptionsConfig,
    OptionType
)
from schwab_config_manager import (
    SchwabConfigManager,
    SchwabCredentials,
    OptionsStrategyParameters,
    UnderlyingConfig,
    setup_credentials_interactive,
    show_current_config
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class TradingApplication:
    """Main application lifecycle manager"""

    def __init__(self, config_dir: str = "~/.schwab_0dte_bot",
                 paper_trading: bool = True,
                 live_flag_explicit: bool = False,
                 log_level: str = "INFO"):
        self.config_mgr = SchwabConfigManager(config_dir)
        self.paper_trading = paper_trading
        self.live_flag_explicit = live_flag_explicit  # True if --live was passed
        self.client: Optional[SchwabClient] = None
        self.strategy: Optional[ZeroDTEMomentumStrategy] = None
        self.running = False

        # Set log level
        logging.getLogger().setLevel(getattr(logging, log_level.upper()))

    async def initialize(self) -> bool:
        """Initialize the trading application"""
        logger.info("Initializing Schwab 0DTE Options Trading Bot...")

        # Load credentials
        credentials = self.config_mgr.load_credentials()
        if not credentials:
            credentials = self.config_mgr.load_credentials_from_keyring()

        if not credentials:
            logger.error("No credentials found. Run with --setup first.")
            return False

        # Load strategy configuration
        params, underlying, environment = self.config_mgr.load_strategy_config()

        # Only use config file paper_trading if --live wasn't explicitly passed
        if not self.live_flag_explicit and 'paper_trading' in environment:
            self.paper_trading = environment['paper_trading']

        # Build options config
        options_config = OptionsConfig(
            time_window=params.time_window_seconds,
            min_price_movement=params.min_price_movement_dollars,
            target_delta=params.target_delta,
            max_bid_ask_spread=params.max_bid_ask_spread_percent,
            stop_loss_percent=params.stop_loss_percent,
            take_profit_percent=params.take_profit_percent,
            no_trade_before=params.no_trade_before,
            no_trade_after=params.no_trade_after,
            symbol=underlying.symbol
        )

        # Initialize client
        self.client = SchwabClient(options_config)

        try:
            await self.client.initialize(
                client_id=credentials.client_id,
                client_secret=credentials.client_secret,
                refresh_token=credentials.refresh_token
            )

            # Update refresh token if it changed
            if self.client.refresh_token != credentials.refresh_token:
                self.config_mgr.update_refresh_token(self.client.refresh_token)

        except Exception as e:
            logger.error(f"Failed to initialize Schwab client: {e}")
            return False

        # Initialize strategy
        self.strategy = ZeroDTEMomentumStrategy(self.client, options_config)

        # Set paper trading flag
        if self.paper_trading:
            logger.info("="*50)
            logger.info("  PAPER TRADING MODE - No real orders will be placed")
            logger.info("="*50)

        return True

    def _is_market_open(self) -> bool:
        """Check if US equity options market is open"""
        now = datetime.now()

        # Check weekday
        if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False

        # Market hours: 9:30 AM - 4:00 PM ET
        market_open = dt_time(9, 30)
        market_close = dt_time(16, 0)
        current_time = now.time()

        return market_open <= current_time <= market_close

    def _time_until_market_open(self) -> Optional[float]:
        """Calculate seconds until market opens"""
        now = datetime.now()

        # If weekend, calculate time until Monday 9:30
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0 and now.time() > dt_time(16, 0):
            days_until_monday = 7 - now.weekday() if now.weekday() < 5 else (7 - now.weekday() + 1)

        if now.weekday() >= 5:
            days_until_monday = 7 - now.weekday()
            if now.weekday() == 6:
                days_until_monday = 1

        # Calculate next market open
        next_open = now.replace(hour=9, minute=30, second=0, microsecond=0)

        if now.time() >= dt_time(16, 0) or now.weekday() >= 5:
            # After close or weekend - next trading day
            if now.weekday() == 4:  # Friday after close
                days_until_monday = 3
            elif now.weekday() == 5:  # Saturday
                days_until_monday = 2
            elif now.weekday() == 6:  # Sunday
                days_until_monday = 1
            else:
                days_until_monday = 1

            from datetime import timedelta
            next_open = (now + timedelta(days=days_until_monday)).replace(
                hour=9, minute=30, second=0, microsecond=0
            )

        return (next_open - now).total_seconds()

    async def run(self):
        """Main trading loop"""
        self.running = True

        logger.info("Starting trading application...")
        logger.info(f"Symbol: SPY | Mode: {'PAPER' if self.paper_trading else 'LIVE'}")

        while self.running:
            try:
                if not self._is_market_open():
                    wait_time = self._time_until_market_open()
                    if wait_time and wait_time > 0:
                        hours = int(wait_time // 3600)
                        minutes = int((wait_time % 3600) // 60)
                        logger.info(f"Market closed. Opens in {hours}h {minutes}m. Waiting...")

                        # Sleep in chunks to allow graceful shutdown
                        sleep_chunk = min(wait_time, 300)  # 5 minute chunks
                        await asyncio.sleep(sleep_chunk)
                        continue

                # Run strategy
                if self.paper_trading:
                    await self._run_paper_trading()
                else:
                    await self.strategy.run()

            except asyncio.CancelledError:
                logger.info("Trading loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in trading loop: {type(e).__name__}: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _run_paper_trading(self):
        """Paper trading mode - simulates trades without placing real orders"""
        logger.info("Paper trading session started")

        paper_position = None
        paper_pnl = 0.0
        paper_trades = []

        while self.running and self._is_market_open():
            try:
                # Get SPY quote
                snapshot = await self.client.get_quote("SPY")

                if snapshot:
                    self.strategy.price_history.append(snapshot)

                    # Check for signals
                    if not paper_position:
                        signal = self.strategy.detect_momentum_signal(snapshot)

                        if signal:
                            # Simulate entry
                            contract = await self.strategy.select_contract(signal, snapshot.price)

                            if contract:
                                paper_position = {
                                    "contract": contract,
                                    "entry_price": contract.mid_price,
                                    "entry_time": datetime.now(),
                                    "signal": signal
                                }
                                logger.info(f"[PAPER] Opened: {signal.value} {contract.symbol} @ ${contract.mid_price:.2f}")

                    # Manage paper position
                    if paper_position:
                        # Get current price
                        chain = await self.client.get_option_chain()
                        current = next(
                            (c for c in chain if c.symbol == paper_position["contract"].symbol),
                            None
                        )

                        if current:
                            entry = paper_position["entry_price"]
                            current_price = current.mid_price
                            pnl_pct = ((current_price - entry) / entry) * 100

                            # Check exits
                            should_exit = False
                            reason = ""

                            if pnl_pct <= -self.strategy.config.stop_loss_percent:
                                should_exit = True
                                reason = "Stop loss"
                            elif pnl_pct >= self.strategy.config.take_profit_percent:
                                should_exit = True
                                reason = "Take profit"
                            elif datetime.now().strftime("%H:%M") >= "15:55":
                                should_exit = True
                                reason = "EOD exit"

                            if should_exit:
                                pnl = (current_price - entry) * 100  # Per contract
                                paper_pnl += pnl
                                paper_trades.append({
                                    "symbol": paper_position["contract"].symbol,
                                    "side": paper_position["signal"].value,
                                    "entry": entry,
                                    "exit": current_price,
                                    "pnl": pnl,
                                    "reason": reason
                                })

                                logger.info(f"[PAPER] Closed: {reason} | P&L: ${pnl:.2f} ({pnl_pct:.1f}%)")
                                logger.info(f"[PAPER] Session P&L: ${paper_pnl:.2f} | Trades: {len(paper_trades)}")
                                paper_position = None

                await asyncio.sleep(0.05)

            except Exception as e:
                logger.error(f"Paper trading error: {type(e).__name__}: {e}", exc_info=True)
                await asyncio.sleep(1)

        # Session summary
        if paper_trades:
            winners = sum(1 for t in paper_trades if t["pnl"] > 0)
            losers = len(paper_trades) - winners
            win_rate = (winners / len(paper_trades)) * 100 if paper_trades else 0

            logger.info("\n" + "="*50)
            logger.info("  PAPER TRADING SESSION SUMMARY")
            logger.info("="*50)
            logger.info(f"  Total Trades: {len(paper_trades)}")
            logger.info(f"  Winners: {winners} | Losers: {losers}")
            logger.info(f"  Win Rate: {win_rate:.1f}%")
            logger.info(f"  Total P&L: ${paper_pnl:.2f}")
            logger.info("="*50 + "\n")

    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down...")
        self.running = False

        # Stop the strategy first (so it stops making API calls)
        if self.strategy:
            self.strategy.stop()

        # Small delay to let the loop exit cleanly
        await asyncio.sleep(0.2)

        # Then close the client session
        if self.client:
            await self.client.close()

        logger.info("Shutdown complete")


def setup_signal_handlers(app: TradingApplication, loop: asyncio.AbstractEventLoop):
    """Setup signal handlers for graceful shutdown"""
    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(app.shutdown())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            signal.signal(sig, lambda s, f: signal_handler())


async def main_async(args):
    """Async main entry point"""
    app = TradingApplication(
        config_dir=args.config_dir,
        paper_trading=not args.live,
        live_flag_explicit=args.live,
        log_level=args.log_level
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
        description="Schwab 0DTE SPY Options Momentum Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python schwab_0dte_main.py --setup          # First-time setup
  python schwab_0dte_main.py --paper          # Paper trading (default)
  python schwab_0dte_main.py --live           # Live trading
  python schwab_0dte_main.py --show           # Show configuration

Risk Warning:
  0DTE options trading is EXTREMELY HIGH RISK. Options can expire
  worthless in hours. Only trade with money you can afford to lose.
        """
    )

    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run interactive setup wizard"
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show current configuration"
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
        "--log-file",
        type=str,
        help="Log to file in addition to console"
    )

    args = parser.parse_args()

    # Setup logging to file if specified
    if args.log_file:
        file_handler = logging.FileHandler(args.log_file)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        logging.getLogger().addHandler(file_handler)

    # Handle setup mode
    if args.setup:
        setup_credentials_interactive()
        return 0

    # Handle show config
    if args.show:
        show_current_config()
        return 0

    # Live trading confirmation
    if args.live:
        print("\n" + "="*60)
        print("  ⚠️  LIVE TRADING MODE WARNING")
        print("="*60)
        print("\n  You are about to start LIVE trading with REAL MONEY.")
        print("  0DTE options are extremely high risk.")
        print("\n  This bot will automatically:")
        print("    - Buy and sell SPY options")
        print("    - Use real funds from your Schwab account")
        print("    - Execute trades based on momentum signals")
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
