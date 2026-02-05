#!/usr/bin/env python3
"""
Momentum Scalp Bot — Main Entry Point

Workflow:
  1. Pre-market (7:00-9:25): Run gap scanner to find today's watchlist
  2. Market open (9:30): Initialize VWAP, start trading
  3. Trading (9:30-11:30): Scalp momentum stocks
  4. EOD (3:50): Close any remaining positions
  5. Summary: Print daily results

Usage:
  # Paper trading — auto scanner
  python momentum_scalp_main.py --paper

  # Paper trading — manual tickers from Trading Terminal
  python momentum_scalp_main.py --paper --tickers ABCD,EFGH,XYZ

  # Paper trading — wider price range
  python momentum_scalp_main.py --paper --max-price 50

  # Live trading (requires confirmation)
  python momentum_scalp_main.py --live

  # Extended trading hours (past 11:30 AM)
  python momentum_scalp_main.py --paper --extended
"""

import asyncio
import argparse
import logging
import signal
import sys
from datetime import datetime, date, time as dt_time, timedelta
from typing import Optional, List

from momentum_scanner import MomentumScanner, ScannerConfig
from momentum_scalp_bot import (
    MomentumSchwabClient,
    MomentumScalpStrategy,
    ScalpConfig,
)
from schwab_0dte_bot import OptionsConfig
from schwab_config_manager import SchwabConfigManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class MomentumScalpApp:
    """Main application for momentum scalp trading"""

    def __init__(self,
                 config_dir: str = "~/.schwab_0dte_bot",
                 paper_mode: bool = True,
                 manual_tickers: Optional[List[str]] = None,
                 log_level: str = "INFO",
                 extended_hours: bool = False,
                 max_price: float = 30.0,
                 min_gap: float = 4.0,
                 max_trades: int = 3):

        self.config_dir = config_dir
        self.paper_mode = paper_mode
        self.manual_tickers = manual_tickers
        self.extended_hours = extended_hours
        self.running = False

        # Configure scanner
        self.scanner_config = ScannerConfig(
            max_price=max_price,
            min_gap_percent=min_gap,
        )

        # Configure strategy
        self.scalp_config = ScalpConfig(
            max_trades_per_day=max_trades,
        )

        # Extend trading hours if requested
        if extended_hours:
            self.scalp_config.trading_end = "15:30"
            self.scalp_config.no_new_entries_after = "14:00"

        # Set log level
        logging.getLogger().setLevel(getattr(logging, log_level.upper()))

        # Components
        self.config_mgr = SchwabConfigManager(config_dir)
        self.client: Optional[MomentumSchwabClient] = None
        self.scanner: Optional[MomentumScanner] = None
        self.strategy: Optional[MomentumScalpStrategy] = None

    async def initialize(self) -> bool:
        """Initialize all components"""
        logger.info("=" * 60)
        logger.info("  🚀 MOMENTUM SCALP BOT — Initializing")
        logger.info("=" * 60)

        # ── Load Schwab Credentials ──
        credentials = self.config_mgr.load_credentials()
        if not credentials:
            credentials = self.config_mgr.load_credentials_from_keyring()

        if not credentials:
            logger.error(
                "No Schwab credentials found.\n"
                "Run: python schwab_0dte_main.py --setup"
            )
            return False

        # ── Initialize Client ──
        base_config = OptionsConfig(symbol="SPY")  # Placeholder
        self.client = MomentumSchwabClient(base_config, config_manager=self.config_mgr)

        try:
            await self.client.initialize(
                client_id=credentials.client_id,
                client_secret=credentials.client_secret,
                refresh_token=credentials.refresh_token,
            )
            logger.info("✅ Schwab client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Schwab client: {e}")
            return False

        # ── Verify Account ──
        try:
            settled, total = await self.client.get_settled_cash()
            logger.info(f"💰 Account: ${total:.2f} total | ${settled:.2f} available")

            if total < 500:
                logger.warning(f"⚠️  Very small account (${total:.2f}). Bot will use conservative sizing.")
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")

        # ── Initialize Scanner ──
        self.scanner = MomentumScanner(self.client, self.scanner_config)

        if self.manual_tickers:
            self.scanner.add_manual_tickers(self.manual_tickers)

        # ── Initialize Strategy ──
        self.strategy = MomentumScalpStrategy(
            client=self.client,
            config=self.scalp_config,
            scanner=self.scanner,
            paper_mode=self.paper_mode,
        )

        logger.info("✅ All components initialized")
        return True

    async def run_premarket_scan(self) -> bool:
        """Run pre-market scan to find today's watchlist"""
        logger.info("\n📡 Running pre-market momentum scan...")

        watchlist = await self.scanner.scan()

        if not watchlist:
            # If no automatic results but we have manual tickers, use those
            if self.manual_tickers:
                logger.info("No auto-scan results, using manual tickers only")
                watchlist = await self.scanner.scan()

            if not watchlist:
                logger.warning("No momentum candidates found. Try adding tickers manually with --tickers")
                return False

        # Pass to strategy
        self.strategy.set_watchlist(watchlist)
        return True

    async def wait_for_market_open(self):
        """Wait until market opens"""
        now = datetime.now()

        if now.time() >= dt_time(9, 30):
            return  # Already open

        open_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
        wait = (open_time - now).total_seconds()

        if wait > 0:
            minutes = int(wait // 60)
            logger.info(f"⏰ Market opens in {minutes} minutes. Waiting...")

            # Wait in chunks, re-scanning periodically
            while wait > 0:
                chunk = min(wait, self.scanner_config.rescan_interval_seconds)
                await asyncio.sleep(chunk)
                wait -= chunk

                if wait > 60:
                    logger.info(f"⏰ {int(wait // 60)} minutes until market open — re-scanning...")
                    await self.scanner.scan()
                    self.strategy.set_watchlist(self.scanner.watchlist)

    async def run_trading_session(self):
        """Run the main trading session"""
        logger.info("\n🔔 Market is OPEN — starting trading session")

        try:
            await self.strategy.run()
        except asyncio.CancelledError:
            logger.info("Trading session cancelled")
        except Exception as e:
            logger.error(f"Trading session error: {e}", exc_info=True)

    async def run(self):
        """Full workflow: scan → wait → trade → summary"""
        self.running = True

        while self.running:
            try:
                now = datetime.now()

                # Weekend check
                if now.weekday() >= 5:
                    days_until = 7 - now.weekday()
                    logger.info(f"Weekend. Market reopens in {days_until} day(s).")
                    await asyncio.sleep(3600)  # Check every hour
                    continue

                # After market hours
                if now.time() > dt_time(16, 5):
                    # Print summary if we traded today
                    if self.strategy and self.strategy.trades_today:
                        summary = self.strategy.get_daily_summary()
                        logger.info(summary)

                    next_day = (now + timedelta(days=1)).replace(hour=7, minute=0, second=0)
                    wait = (next_day - now).total_seconds()
                    logger.info(f"Market closed. Next pre-market scan at 7:00 AM ({int(wait // 3600)}h)")
                    await asyncio.sleep(min(wait, 3600))
                    continue

                # ── Phase 1: Pre-Market Scan ──
                if now.time() < dt_time(9, 30):
                    found = await self.run_premarket_scan()

                    if not found and not self.manual_tickers:
                        logger.info("No candidates. Will re-scan in 2 minutes...")
                        await asyncio.sleep(120)
                        continue

                    # Wait for open
                    await self.wait_for_market_open()

                # ── Phase 2: Market Open — ensure we have a watchlist ──
                if not self.strategy.watchlist_symbols:
                    logger.info("No watchlist set — running scan now...")
                    found = await self.run_premarket_scan()
                    if not found:
                        logger.warning("Still no candidates. Waiting 5 minutes...")
                        await asyncio.sleep(300)
                        continue

                # ── Phase 3: Trading Session ──
                await self.run_trading_session()

                # ── Phase 4: Post-Session Summary ──
                if self.strategy.trades_today:
                    summary = self.strategy.get_daily_summary()
                    logger.info(summary)

                    # Send to Telegram if configured
                    await self._send_telegram_summary(summary)

                # Wait until next day
                if self.running:
                    now = datetime.now()
                    if now.time() > dt_time(12, 0):
                        # Done for the day
                        next_scan = (now + timedelta(days=1)).replace(hour=7, minute=0, second=0)
                        wait = (next_scan - now).total_seconds()
                        logger.info(f"Session complete. Next scan: tomorrow 7:00 AM")
                        await asyncio.sleep(min(wait, 3600))
                    else:
                        # Short break, will loop back
                        await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Main loop error: {e}", exc_info=True)
                await asyncio.sleep(30)

    async def _send_telegram_summary(self, summary: str):
        """Send daily summary to Telegram (if bot token available)"""
        try:
            import os
            from pathlib import Path

            # Try to load .env
            env_path = Path(__file__).parent / ".env"
            bot_token = None
            chat_id = None

            if env_path.exists():
                with open(env_path) as f:
                    for line in f:
                        if line.startswith("TELEGRAM_BOT_TOKEN="):
                            bot_token = line.split("=", 1)[1].strip()
                        elif line.startswith("TELEGRAM_CHAT_ID="):
                            chat_id = line.split("=", 1)[1].strip()

            # Fallback to env vars
            bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
            chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

            if not bot_token or not chat_id:
                return

            import aiohttp
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": f"📊 Momentum Scalp Bot — Daily Summary\n\n{summary}",
                "parse_mode": "HTML",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        logger.info("📱 Summary sent to Telegram")
                    else:
                        logger.debug(f"Telegram send failed: {resp.status}")

        except Exception as e:
            logger.debug(f"Telegram summary failed: {e}")

    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down...")
        self.running = False

        if self.strategy:
            self.strategy.stop()

            # Close any open position
            if self.strategy.position:
                logger.warning("⚠️  Closing open position on shutdown!")
                pos = self.strategy.position
                quote = await self.client.get_quote(pos.symbol)
                if quote:
                    price = float(quote.get("lastPrice", 0))
                    await self.strategy._exit_shares(
                        pos.symbol, pos.shares, price, "SHUTDOWN EXIT"
                    )

            # Print final summary
            if self.strategy.trades_today:
                logger.info(self.strategy.get_daily_summary())

        await asyncio.sleep(0.5)

        if self.client:
            await self.client.close()

        logger.info("Shutdown complete ✅")


def setup_signal_handlers(app: MomentumScalpApp, loop: asyncio.AbstractEventLoop):
    """Setup Ctrl+C / SIGTERM handlers"""
    def handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(app.shutdown())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handler)
        except NotImplementedError:
            signal.signal(sig, lambda s, f: handler())


async def main_async(args):
    """Async entry point"""
    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]

    app = MomentumScalpApp(
        config_dir=args.config_dir,
        paper_mode=not args.live,
        manual_tickers=tickers,
        log_level=args.log_level,
        extended_hours=args.extended,
        max_price=args.max_price,
        min_gap=args.min_gap,
        max_trades=args.max_trades,
    )

    loop = asyncio.get_event_loop()
    setup_signal_handlers(app, loop)

    if not await app.initialize():
        return 1

    try:
        await app.run()
    except KeyboardInterrupt:
        pass
    finally:
        await app.shutdown()

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Momentum Scalp Bot — Ross Cameron Style Share Trading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python momentum_scalp_main.py --paper                     # Auto-scan, paper trade
  python momentum_scalp_main.py --paper --tickers ABCD,XYZ  # Manual tickers
  python momentum_scalp_main.py --paper --extended           # Trade until 2 PM
  python momentum_scalp_main.py --paper --min-gap 3          # Lower gap threshold
  python momentum_scalp_main.py --paper --max-price 50       # Include higher-priced stocks
  python momentum_scalp_main.py --live                       # Real money (careful!)

Strategy:
  Finds small-cap stocks gapping up 4%+ in pre-market with high volume.
  Enters on VWAP pullback reclaims or pre-market high breakouts.
  Scalps 5-10% moves with tight 2.5% stops.
  Max 3 trades/day (cash account T+1 settlement).

Best performance: First 2 hours after market open (9:30-11:30 AM).
        """
    )

    parser.add_argument("--paper", action="store_true", default=True,
                        help="Paper trading mode (default)")
    parser.add_argument("--live", action="store_true",
                        help="LIVE trading mode (real money)")
    parser.add_argument("--tickers", type=str,
                        help="Manual tickers from Trading Terminal (comma-separated)")
    parser.add_argument("--extended", action="store_true",
                        help="Extended trading hours (until 2 PM instead of 11:30 AM)")
    parser.add_argument("--max-price", type=float, default=30.0,
                        help="Max stock price for scanner (default: $30)")
    parser.add_argument("--min-gap", type=float, default=4.0,
                        help="Minimum gap %% for scanner (default: 4%%)")
    parser.add_argument("--max-trades", type=int, default=3,
                        help="Max trades per day (default: 3)")
    parser.add_argument("--config-dir", type=str, default="~/.schwab_0dte_bot",
                        help="Schwab config directory")
    parser.add_argument("--log-level", type=str, default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    args = parser.parse_args()

    # Live trading confirmation
    if args.live:
        print("\n" + "=" * 60)
        print("  ⚠️  LIVE TRADING — REAL MONEY WARNING")
        print("=" * 60)
        print("\n  This bot will BUY and SELL SHARES with REAL money.")
        print("  Momentum stocks are volatile. You can lose money fast.")
        print(f"\n  Settings:")
        print(f"    Max trades/day: {args.max_trades}")
        print(f"    Scanner price range: $2 - ${args.max_price}")
        print(f"    Min gap: {args.min_gap}%")
        if args.tickers:
            print(f"    Manual tickers: {args.tickers}")
        print("\n" + "=" * 60)

        confirm = input("\n  Type 'I ACCEPT THE RISK' to continue: ")
        if confirm != "I ACCEPT THE RISK":
            print("\n  Cancelled.")
            return 0

    # Run
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass

    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
