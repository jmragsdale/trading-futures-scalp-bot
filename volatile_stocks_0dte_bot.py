#!/usr/bin/env python3
"""
0DTE Options Momentum Trading Bot for Volatile Stocks (NVDA, TSLA, AMD, etc.)
Percentage-based momentum detection for stocks with different price levels

Key Differences from SPY version:
- Percentage-based momentum (not dollar-based)
- Configurable for multiple tickers with liquid options
- Adjusted for higher volatility
- Dynamically selects best ticker based on current volatility
"""

import asyncio
import aiohttp
import json
import time
import logging
import base64
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import deque
from enum import Enum

# Reuse core components from schwab_0dte_bot
from schwab_0dte_bot import (
    OptionType,
    OrderSide,
    OptionContract,
    PriceSnapshot,
    SchwabClient,
    OptionsConfig
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class VolatileStockConfig:
    """Configuration for volatile stock momentum trading"""
    # Tickers to monitor (stocks with liquid options)
    tickers: List[str] = None  # ["NVDA", "TSLA", "AMD", "AAPL", "MSFT", "META", "GOOGL"]

    # Momentum detection - PERCENTAGE BASED
    time_window: int = 20  # seconds to measure momentum
    min_percent_movement: float = 0.40  # 0.4% move in time_window

    # Stock volatility requirements (scan for best ticker)
    min_daily_range_percent: float = 1.5  # Stock must have 1.5%+ intraday range
    preferred_price_range: Tuple[float, float] = (100, 800)  # Prefer $100-$800 stocks

    # Options selection - tuned for volatile stocks
    target_delta: float = 0.50  # Higher delta for faster-moving stocks
    max_bid_ask_spread: float = 0.12  # Allow wider spreads (12%)
    min_option_price: float = 1.00  # Lower minimum premium
    min_volume: int = 200  # Lower volume requirement
    min_open_interest: int = 300  # Lower OI requirement

    # Risk management - wider for volatility
    max_positions: int = 1
    stop_loss_percent: float = 40.0  # Wider stop for volatility
    take_profit_percent: float = 70.0  # Higher target

    # Trailing stop
    use_trailing_stop: bool = True
    trailing_stop_percent: float = 25.0
    trailing_stop_activation: float = 20.0

    # Order execution
    use_aggressive_limit: bool = True
    limit_offset_cents: float = 0.03
    order_timeout_seconds: float = 3.0
    max_chase_attempts: int = 3
    chase_increment_cents: float = 0.05

    # Time filters
    no_trade_before: str = "09:45"
    no_trade_after: str = "15:30"  # Longer window for volatile stocks

    # Scanning
    scan_interval_seconds: int = 30  # Re-scan tickers every 30s

    # Schwab API
    api_base: str = "https://api.schwabapi.com"

    def __post_init__(self):
        if self.tickers is None:
            # Default: Highly liquid volatile stocks
            self.tickers = ["NVDA", "TSLA", "AMD", "AAPL", "MSFT", "META", "GOOGL", "AMZN"]


@dataclass
class TickerSnapshot:
    """Snapshot of a ticker's current state"""
    symbol: str
    price: float
    bid: float
    ask: float
    volume: int
    day_high: float
    day_low: float
    prev_close: float
    timestamp: float

    @property
    def intraday_range_percent(self) -> float:
        """Calculate intraday range as percentage"""
        if self.day_low > 0:
            return ((self.day_high - self.day_low) / self.day_low) * 100
        return 0.0

    @property
    def day_change_percent(self) -> float:
        """Calculate percentage change from previous close"""
        if self.prev_close > 0:
            return ((self.price - self.prev_close) / self.prev_close) * 100
        return 0.0


class VolatileStockClient(SchwabClient):
    """Extended Schwab client for multi-ticker support"""

    async def get_quotes_batch(self, symbols: List[str]) -> Dict[str, TickerSnapshot]:
        """Get quotes for multiple symbols"""
        await self._ensure_valid_token()

        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.config.api_base}/marketdata/v1/quotes"

        # Schwab allows comma-separated symbols
        params = {"symbols": ",".join(symbols)}

        snapshots = {}

        async with self.session.get(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()

                for symbol in symbols:
                    if symbol in data:
                        quote = data[symbol].get("quote", {})
                        if quote:
                            snapshots[symbol] = TickerSnapshot(
                                symbol=symbol,
                                price=quote.get("lastPrice", 0),
                                bid=quote.get("bidPrice", 0),
                                ask=quote.get("askPrice", 0),
                                volume=quote.get("totalVolume", 0),
                                day_high=quote.get("highPrice", 0),
                                day_low=quote.get("lowPrice", 0),
                                prev_close=quote.get("closePrice", 0),
                                timestamp=time.time()
                            )

        return snapshots

    async def get_option_chain_for_symbol(self, symbol: str,
                                          expiration: Optional[date] = None) -> List[OptionContract]:
        """Get option chain for a specific symbol (not just SPY)"""
        await self._ensure_valid_token()

        if expiration is None:
            expiration = date.today()

        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.config.api_base}/marketdata/v1/chains"

        params = {
            "symbol": symbol,
            "contractType": "ALL",
            "includeUnderlyingQuote": "true",
            "strategy": "SINGLE",
            "fromDate": expiration.isoformat(),
            "toDate": expiration.isoformat()
        }

        contracts = []

        async with self.session.get(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()

                # Parse calls
                if "callExpDateMap" in data:
                    for exp_date, strikes in data["callExpDateMap"].items():
                        for strike, options in strikes.items():
                            for opt in options:
                                contracts.append(self._parse_option_for_symbol(opt, OptionType.CALL, symbol))

                # Parse puts
                if "putExpDateMap" in data:
                    for exp_date, strikes in data["putExpDateMap"].items():
                        for strike, options in strikes.items():
                            for opt in options:
                                contracts.append(self._parse_option_for_symbol(opt, OptionType.PUT, symbol))

        return contracts

    def _parse_option_for_symbol(self, opt_data: Dict, option_type: OptionType, symbol: str) -> OptionContract:
        """Parse option data for any symbol"""
        return OptionContract(
            symbol=opt_data.get("symbol", ""),
            underlying=symbol,
            option_type=option_type,
            strike=float(opt_data.get("strikePrice", 0)),
            expiration=date.today(),  # 0DTE
            bid=float(opt_data.get("bid", 0)),
            ask=float(opt_data.get("ask", 0)),
            last=float(opt_data.get("last", 0)),
            delta=float(opt_data.get("delta", 0)),
            gamma=float(opt_data.get("gamma", 0)),
            theta=float(opt_data.get("theta", 0)),
            vega=float(opt_data.get("vega", 0)),
            volume=int(opt_data.get("totalVolume", 0)),
            open_interest=int(opt_data.get("openInterest", 0))
        )


class VolatileStockMomentumStrategy:
    """
    Momentum strategy for volatile stocks using percentage-based signals
    Monitors multiple tickers and trades the one with best setup
    """

    def __init__(self, client: VolatileStockClient, config: VolatileStockConfig, safety_manager=None):
        self.client = client
        self.config = config
        self.safety_manager = safety_manager  # Optional account safety manager

        # Price history per ticker
        self.price_history: Dict[str, deque] = {
            ticker: deque(maxlen=1000) for ticker in config.tickers
        }

        # Signal tracking per ticker
        self.last_signal_time: Dict[str, float] = {ticker: 0 for ticker in config.tickers}
        self.last_signal_price: Dict[str, float] = {ticker: 0 for ticker in config.tickers}

        # Position tracking
        self.current_position: Optional[Dict] = None
        self.current_ticker: Optional[str] = None
        self.running = False

        # Trailing stop tracking
        self.high_water_mark: float = 0.0
        self.trailing_stop_price: float = 0.0
        self.trailing_stop_active: bool = False

        # Ticker scoring
        self.last_scan_time: float = 0
        self.active_ticker: Optional[str] = None
        self.ticker_scores: Dict[str, float] = {}

    def stop(self):
        """Stop the trading loop"""
        self.running = False

    def _is_trading_hours(self) -> bool:
        """Check if within allowed trading hours"""
        now = datetime.now()
        current_time = now.strftime("%H:%M")

        if now.weekday() >= 5:
            return False

        if current_time < self.config.no_trade_before:
            return False
        if current_time > self.config.no_trade_after:
            return False

        return True

    async def scan_best_ticker(self, snapshots: Dict[str, TickerSnapshot]) -> Optional[str]:
        """
        Scan all tickers and return the best one to trade based on:
        - Current intraday range (volatility)
        - Price level (prefer mid-range)
        - Volume
        """
        scores = {}

        for symbol, snap in snapshots.items():
            if snap.price == 0:
                continue

            score = 0

            # Volatility score (higher is better)
            range_pct = snap.intraday_range_percent
            if range_pct >= self.config.min_daily_range_percent:
                score += range_pct * 10  # Weight volatility heavily
            else:
                continue  # Skip if not volatile enough

            # Price level score (prefer mid-range prices)
            min_price, max_price = self.config.preferred_price_range
            if min_price <= snap.price <= max_price:
                score += 20
            elif snap.price < min_price:
                score += 10  # Still ok

            # Volume score (normalized)
            if snap.volume > 1_000_000:
                score += 10

            # Momentum score (already moving)
            abs_change = abs(snap.day_change_percent)
            if abs_change >= 1.0:
                score += abs_change * 5

            scores[symbol] = score

        if not scores:
            return None

        # Return ticker with highest score
        best = max(scores, key=scores.get)
        self.ticker_scores = scores

        logger.info(f"Ticker scan: {best} (score: {scores[best]:.1f}) | "
                   f"Range: {snapshots[best].intraday_range_percent:.2f}% | "
                   f"Price: ${snapshots[best].price:.2f}")

        return best

    def detect_momentum_signal(self, ticker: str, current: TickerSnapshot) -> Optional[OptionType]:
        """
        Detect percentage-based momentum signal
        Returns CALL (bullish), PUT (bearish), or None
        """
        if not self._is_trading_hours():
            return None

        current_time = current.timestamp
        current_price = current.price

        # Initialize reference point
        if self.last_signal_price.get(ticker, 0) == 0:
            self.last_signal_price[ticker] = current_price
            self.last_signal_time[ticker] = current_time
            return None

        # Calculate movement
        time_diff = current_time - self.last_signal_time[ticker]
        price_diff = current_price - self.last_signal_price[ticker]
        percent_move = (price_diff / self.last_signal_price[ticker]) * 100

        # Check for signal within time window
        if time_diff <= self.config.time_window:
            # Log when approaching threshold
            threshold_pct = abs(percent_move) / self.config.min_percent_movement
            if threshold_pct >= 0.80 and threshold_pct < 1.0:
                direction = "up" if percent_move > 0 else "down"
                logger.debug(f"Near signal [{ticker}]: {direction} {abs(percent_move):.2f}% in {time_diff:.1f}s "
                           f"({threshold_pct*100:.0f}% of {self.config.min_percent_movement}% threshold)")

            if abs(percent_move) >= self.config.min_percent_movement:
                if self.current_position is None:
                    # Update reference
                    self.last_signal_price[ticker] = current_price
                    self.last_signal_time[ticker] = current_time

                    if percent_move > 0:
                        logger.info(f"BULLISH Signal [{ticker}]: +{percent_move:.2f}% (${price_diff:.2f}) in {time_diff:.1f}s")
                        return OptionType.CALL
                    else:
                        logger.info(f"BEARISH Signal [{ticker}]: {percent_move:.2f}% (${price_diff:.2f}) in {time_diff:.1f}s")
                        return OptionType.PUT

        # Reset reference if window expired
        if time_diff >= self.config.time_window:
            self.last_signal_price[ticker] = current_price
            self.last_signal_time[ticker] = current_time

        return None

    async def select_contract(self, ticker: str, option_type: OptionType,
                             stock_price: float) -> Optional[OptionContract]:
        """Select best contract for the given ticker"""
        chain = await self.client.get_option_chain_for_symbol(ticker)

        # Filter by type
        candidates = [c for c in chain if c.option_type == option_type]

        # Target delta
        target_delta = self.config.target_delta
        if option_type == OptionType.PUT:
            target_delta = -target_delta

        # Score contracts
        scored = []
        rejection_reasons = {"no_quote": 0, "low_premium": 0, "wide_spread": 0, "low_volume": 0, "low_oi": 0}

        for c in candidates:
            if c.bid <= 0 or c.ask <= 0:
                rejection_reasons["no_quote"] += 1
                continue

            if c.mid_price < self.config.min_option_price:
                rejection_reasons["low_premium"] += 1
                continue

            if c.spread_percent > self.config.max_bid_ask_spread:
                rejection_reasons["wide_spread"] += 1
                continue

            if c.volume < self.config.min_volume:
                rejection_reasons["low_volume"] += 1
                continue

            if c.open_interest < self.config.min_open_interest:
                rejection_reasons["low_oi"] += 1
                continue

            # Scoring
            delta_score = abs(abs(c.delta) - abs(target_delta))
            spread_score = c.spread_percent * 2
            volume_bonus = -min(c.volume / 5000, 0.15)

            score = delta_score + spread_score + volume_bonus
            scored.append((score, c))

        if not scored:
            logger.warning(f"No suitable {option_type.value} contracts for {ticker} "
                          f"(checked {len(candidates)} candidates)")
            logger.warning(f"Rejections: no_quote={rejection_reasons['no_quote']}, "
                          f"low_premium(<${self.config.min_option_price})={rejection_reasons['low_premium']}, "
                          f"wide_spread(>{self.config.max_bid_ask_spread*100:.0f}%)={rejection_reasons['wide_spread']}, "
                          f"low_vol(<{self.config.min_volume})={rejection_reasons['low_volume']}, "
                          f"low_OI(<{self.config.min_open_interest})={rejection_reasons['low_oi']}")
            return None

        # Best contract
        scored.sort(key=lambda x: x[0])
        best = scored[0][1]

        expected_slippage = best.spread / 2
        slippage_pct = (expected_slippage * 2 / best.mid_price) * 100

        logger.info(f"Selected [{ticker}]: {best.symbol} | Strike: ${best.strike} | "
                   f"Delta: {best.delta:.2f} | Bid/Ask: ${best.bid:.2f}/${best.ask:.2f} | "
                   f"Vol: {best.volume} | Est. slippage: {slippage_pct:.1f}%")

        return best

    async def execute_signal(self, ticker: str, signal: OptionType, stock_price: float):
        """Execute trading signal for the given ticker"""
        contract = await self.select_contract(ticker, signal, stock_price)

        if not contract:
            return

        # SAFETY CHECK: Verify we can afford this trade
        if self.safety_manager:
            try:
                account_data = await self.client.get_account_info()

                # Import here to avoid circular dependency
                from schwab_account_safety import AccountInfo

                account_info = AccountInfo(
                    cash_available=account_data['cash'],
                    buying_power=account_data['buyingPower'],
                    account_type=account_data['accountType'],
                    account_value=account_data['liquidationValue']
                )

                can_trade, reason = self.safety_manager.can_trade(account_info, contract.mid_price)

                if not can_trade:
                    logger.warning(f"🛑 TRADE BLOCKED BY SAFETY [{ticker}]: {reason}")
                    logger.warning(f"   Option: {contract.symbol} @ ${contract.mid_price:.2f} (${contract.mid_price * 100:.2f} total)")
                    logger.warning(f"   Account: ${account_info.cash_available:.2f} cash, ${account_info.account_value:.2f} total")
                    return

                # Log safety approval
                max_contracts = self.safety_manager.get_max_contracts_allowed(account_info, contract.mid_price)
                logger.info(f"✅ Safety approved [{ticker}]: ${contract.mid_price:.2f} option (max {max_contracts} contracts allowed)")

            except Exception as e:
                logger.error(f"Safety check failed: {e}. Blocking trade as precaution.")
                return

        # Aggressive limit pricing
        if self.config.use_aggressive_limit:
            limit_price = contract.ask + self.config.limit_offset_cents
        else:
            limit_price = contract.mid_price

        # Place order with retry
        result = await self._place_order_with_fill_check(
            contract, limit_price, OrderSide.BUY_TO_OPEN
        )

        if result and result.get("filled"):
            actual_fill = result.get("fill_price", limit_price)
            self.current_position = {
                "ticker": ticker,
                "contract": contract,
                "entry_price": actual_fill,
                "entry_time": time.time(),
                "order_id": result["orderId"],
                "signal": signal
            }
            self.current_ticker = ticker
            logger.info(f"Position opened [{ticker}]: {signal.value} @ ${actual_fill:.2f}")

    async def _place_order_with_fill_check(self, contract: OptionContract,
                                           initial_limit: float,
                                           side: OrderSide) -> Optional[Dict]:
        """Place order and chase price if not filled"""
        limit_price = initial_limit

        for attempt in range(self.config.max_chase_attempts):
            result = await self.client.place_option_order(
                contract=contract,
                side=side,
                quantity=1,
                limit_price=limit_price
            )

            if not result or "error" in result:
                return None

            order_id = result.get("orderId")
            if not order_id:
                return None

            # Wait for fill
            start_time = time.time()
            while time.time() - start_time < self.config.order_timeout_seconds:
                order_status = await self.client.get_order_status(order_id)

                if order_status:
                    status = order_status.get("status")

                    if status == "FILLED":
                        fill_price = float(order_status.get("price", limit_price))
                        logger.info(f"Order filled on attempt {attempt + 1} @ ${fill_price:.2f}")
                        return {"orderId": order_id, "filled": True, "fill_price": fill_price}

                    elif status in ["CANCELED", "REJECTED", "EXPIRED"]:
                        logger.warning(f"Order {status}")
                        break

                await asyncio.sleep(0.1)

            # Chase price
            await self.client.cancel_order(order_id)

            if attempt < self.config.max_chase_attempts - 1:
                if side == OrderSide.BUY_TO_OPEN:
                    limit_price += self.config.chase_increment_cents
                else:
                    limit_price -= self.config.chase_increment_cents

                logger.info(f"Chasing: attempt {attempt + 2}, new limit ${limit_price:.2f}")

                # Refresh contract
                chain = await self.client.get_option_chain_for_symbol(contract.underlying)
                updated = next((c for c in chain if c.symbol == contract.symbol), None)
                if updated:
                    contract = updated

        return None

    def manage_trailing_stop(self, current_price: float, entry_price: float) -> Tuple[bool, float]:
        """Manage trailing stop"""
        pnl_percent = ((current_price - entry_price) / entry_price) * 100

        if not self.trailing_stop_active:
            if pnl_percent >= self.config.trailing_stop_activation:
                self.trailing_stop_active = True
                self.high_water_mark = current_price
                self.trailing_stop_price = current_price * (1 - self.config.trailing_stop_percent / 100)
                logger.info(f"Trailing stop activated at {pnl_percent:.1f}% profit, "
                           f"stop set at ${self.trailing_stop_price:.2f}")
            return False, 0.0

        # Update high water mark
        if current_price > self.high_water_mark:
            self.high_water_mark = current_price
            new_stop = current_price * (1 - self.config.trailing_stop_percent / 100)

            if new_stop > self.trailing_stop_price:
                self.trailing_stop_price = new_stop
                logger.info(f"Trailing stop raised to ${self.trailing_stop_price:.2f}")

        # Check if hit
        if current_price <= self.trailing_stop_price:
            return True, self.trailing_stop_price

        return False, self.trailing_stop_price

    async def manage_position(self):
        """Manage open position"""
        if not self.current_position:
            return

        ticker = self.current_position["ticker"]
        contract = self.current_position["contract"]
        entry_price = self.current_position["entry_price"]

        # Get current option price
        chain = await self.client.get_option_chain_for_symbol(ticker)
        current_contract = next(
            (c for c in chain if c.symbol == contract.symbol),
            None
        )

        if not current_contract:
            logger.warning(f"Could not find current contract price for {ticker}")
            return

        current_price = current_contract.mid_price
        pnl_percent = ((current_price - entry_price) / entry_price) * 100

        # Exit conditions
        should_exit = False
        exit_reason = ""

        # Trailing stop
        if self.config.use_trailing_stop:
            should_trail_exit, trail_price = self.manage_trailing_stop(current_price, entry_price)
            if should_trail_exit:
                should_exit = True
                exit_reason = f"Trailing stop hit at ${trail_price:.2f} ({pnl_percent:.1f}%)"

        # Stop loss
        if not should_exit and pnl_percent <= -self.config.stop_loss_percent:
            should_exit = True
            exit_reason = f"Stop loss hit ({pnl_percent:.1f}%)"

        # Take profit
        if not should_exit and pnl_percent >= self.config.take_profit_percent:
            should_exit = True
            exit_reason = f"Take profit hit ({pnl_percent:.1f}%)"

        # Time-based exit
        current_time = datetime.now().strftime("%H:%M")
        if current_time >= "15:55":
            should_exit = True
            exit_reason = "End of day exit"

        if should_exit:
            await self._close_position(current_contract, exit_reason)

    async def _close_position(self, contract: OptionContract, reason: str):
        """Close position"""
        if self.config.use_aggressive_limit:
            limit_price = contract.bid - self.config.limit_offset_cents
            limit_price = max(limit_price, 0.01)
        else:
            limit_price = contract.mid_price

        result = await self._place_order_with_fill_check(
            contract, limit_price, OrderSide.SELL_TO_CLOSE
        )

        if result and result.get("filled"):
            entry = self.current_position["entry_price"]
            exit_price = result.get("fill_price", limit_price)
            pnl = (exit_price - entry) * 100
            pnl_percent = ((exit_price - entry) / entry) * 100

            ticker = self.current_position["ticker"]
            logger.info(f"Position closed [{ticker}]: {reason} | Entry: ${entry:.2f} | "
                       f"Exit: ${exit_price:.2f} | P&L: ${pnl:.2f} ({pnl_percent:.1f}%)")

            # Record trade with safety manager
            if self.safety_manager:
                from datetime import datetime
                entry_time = datetime.fromtimestamp(self.current_position["entry_time"])
                exit_time = datetime.now()
                self.safety_manager.record_trade(entry_time, exit_time, pnl)

                # Log safety status
                status = self.safety_manager.get_safety_status()
                logger.info(f"📊 Daily Stats: {status['daily_trades']} trades, "
                           f"${status['daily_pnl']:.2f} P&L, "
                           f"{status['day_trades_last_5_days']} day trades (last 5 days)")

            self.current_position = None
            self.current_ticker = None
            self.trailing_stop_active = False
            self.high_water_mark = 0.0
            self.trailing_stop_price = 0.0
        else:
            # Emergency exit
            logger.warning(f"Fill failed, emergency exit at bid ${contract.bid:.2f}")
            await self.client.place_option_order(
                contract=contract,
                side=OrderSide.SELL_TO_CLOSE,
                quantity=1,
                limit_price=contract.bid - 0.05
            )
            self.current_position = None
            self.current_ticker = None
            self.trailing_stop_active = False
            self.high_water_mark = 0.0
            self.trailing_stop_price = 0.0

    async def run(self):
        """Main trading loop"""
        logger.info("Starting Volatile Stock 0DTE Options Momentum Strategy...")
        logger.info(f"Monitoring: {', '.join(self.config.tickers)}")
        logger.info(f"Signal: {self.config.min_percent_movement}% move in {self.config.time_window}s")
        logger.info(f"Risk: TP={self.config.take_profit_percent}%, SL={self.config.stop_loss_percent}%")

        self.running = True
        last_heartbeat = 0
        heartbeat_interval = 300

        while self.running:
            try:
                current_time = time.time()

                # Periodic heartbeat
                if current_time - last_heartbeat >= heartbeat_interval:
                    if self._is_trading_hours():
                        status = "Scanning tickers" if not self.current_position else f"In position ({self.current_ticker})"
                        logger.info(f"[Heartbeat] {status} | Active: {self.active_ticker or 'None'}")
                    last_heartbeat = current_time

                # Get quotes for all tickers
                snapshots = await self.client.get_quotes_batch(self.config.tickers)

                if not snapshots:
                    await asyncio.sleep(1)
                    continue

                # Store price history
                for symbol, snap in snapshots.items():
                    self.price_history[symbol].append(snap)

                # If no position: scan for best ticker and check signals
                if not self.current_position:
                    # Re-scan periodically for best ticker
                    if current_time - self.last_scan_time >= self.config.scan_interval_seconds:
                        self.active_ticker = await self.scan_best_ticker(snapshots)
                        self.last_scan_time = current_time

                    # Check signal on active ticker
                    if self.active_ticker and self.active_ticker in snapshots:
                        snap = snapshots[self.active_ticker]
                        signal = self.detect_momentum_signal(self.active_ticker, snap)
                        if signal:
                            await self.execute_signal(self.active_ticker, signal, snap.price)

                # Manage existing position
                if self.current_position:
                    await self.manage_position()

                await asyncio.sleep(0.05)

            except Exception as e:
                logger.error(f"Error in trading loop: {type(e).__name__}: {e}", exc_info=True)
                await asyncio.sleep(1)
