#!/usr/bin/env python3
"""
Momentum Scalp Bot — Ross Cameron Style
Trades SHARES (not options) on small-cap momentum stocks.

Strategy:
  1. Pre-market: Scanner finds gapping stocks ($2-$30, 4%+ gap, high rvol)
  2. Market open: Monitor watchlist for entry signals
  3. Entry: VWAP reclaim pullback OR break of pre-market high with volume
  4. Exit: Tight stops (2-3%), quick profit targets (5-10%), trailing stop
  5. Cash account: Max 2-3 trades/day due to T+1 settlement

Key Differences from Options Bot:
  - Trades SHARES via Schwab equity orders
  - Percentage-based position sizing (risk-per-trade model)
  - VWAP-based entries (not raw momentum detection)
  - Cash settlement tracking
  - Designed for $2-$30 small/mid cap stocks
"""

import asyncio
import aiohttp
import json
import time
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

from schwab_0dte_bot import SchwabClient, OptionsConfig
from schwab_config_manager import SchwabConfigManager
from momentum_scanner import MomentumScanner, ScannerConfig, GapCandidate

logger = logging.getLogger(__name__)


# ─── Configuration ────────────────────────────────────────────────────────────

@dataclass
class ScalpConfig:
    """Configuration for the momentum scalp strategy"""

    # ── Position Sizing (Risk-Based) ──
    max_risk_per_trade_pct: float = 3.0     # Risk 3% of account per trade
    max_risk_per_trade_dollars: float = 150.0  # Hard cap: $150 risk per trade
    max_position_pct: float = 50.0          # Max 50% of account in one stock
    max_daily_loss_pct: float = 5.0         # Stop trading after 5% daily loss
    max_daily_loss_dollars: float = 200.0   # Hard cap: $200 daily loss

    # ── Entry Signals ──
    entry_mode: str = "both"  # "vwap", "breakout", "both"

    # VWAP Pullback Entry
    vwap_entry_enabled: bool = True
    vwap_pullback_percent: float = 0.5    # Price within 0.5% of VWAP
    vwap_reclaim_candles: int = 2         # Must hold above VWAP for 2 candles
    min_volume_surge: float = 1.5         # 1.5x avg 1-min volume for entry

    # Pre-Market High Breakout Entry
    breakout_entry_enabled: bool = True
    breakout_buffer_percent: float = 0.2  # Must break PM high by 0.2%
    breakout_volume_multiplier: float = 2.0  # Volume must be 2x on breakout candle

    # ── Exit Rules ──
    stop_loss_percent: float = 2.5        # Initial stop: 2.5% below entry
    take_profit_percent: float = 6.0      # First target: 6%
    take_profit_partial: float = 0.5      # Sell 50% at first target

    # Trailing Stop
    trailing_stop_enabled: bool = True
    trailing_stop_activation_pct: float = 3.0   # Activate after 3% profit
    trailing_stop_distance_pct: float = 1.5     # Trail by 1.5%

    # Time-based exits
    max_hold_minutes: int = 30            # Max hold time per trade
    eod_exit_time: str = "15:50"          # Close all by 3:50 PM
    no_new_entries_after: str = "11:30"   # Ross Cameron focuses on first 2 hours

    # ── Cash Account Constraints ──
    max_trades_per_day: int = 3           # T+1 settlement limits
    cash_buffer_dollars: float = 100.0    # Always keep $100 untouched

    # ── Trading Hours ──
    trading_start: str = "09:30"          # Market open
    trading_end: str = "11:30"            # Focus on morning momentum (extendable)

    # ── Scanning ──
    candle_interval_seconds: int = 60     # 1-minute candles
    quote_poll_interval: float = 0.5      # Poll quotes every 500ms

    # ── Schwab API ──
    api_base: str = "https://api.schwabapi.com"


class EntrySignal(Enum):
    VWAP_RECLAIM = "vwap_reclaim"
    PM_HIGH_BREAKOUT = "pm_high_breakout"


@dataclass
class TradeRecord:
    """Record of a completed trade"""
    symbol: str
    side: str
    shares: int
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    signal_type: str
    pnl_dollars: float
    pnl_percent: float


# ─── VWAP Tracker ─────────────────────────────────────────────────────────────

class VWAPTracker:
    """
    Tracks Volume-Weighted Average Price from 1-minute candles.
    VWAP = Σ(price × volume) / Σ(volume)
    """

    def __init__(self):
        self.cumulative_tp_vol: float = 0.0   # Σ(typical_price × volume)
        self.cumulative_vol: int = 0           # Σ(volume)
        self.vwap: float = 0.0
        self.candle_count: int = 0
        self.candle_volumes: List[int] = []    # For avg volume calculation

    def update(self, high: float, low: float, close: float, volume: int):
        """Update VWAP with a new candle"""
        if volume <= 0:
            return

        typical_price = (high + low + close) / 3.0
        self.cumulative_tp_vol += typical_price * volume
        self.cumulative_vol += volume
        self.candle_count += 1
        self.candle_volumes.append(volume)

        if self.cumulative_vol > 0:
            self.vwap = self.cumulative_tp_vol / self.cumulative_vol

    def get_vwap(self) -> float:
        return self.vwap

    def get_avg_candle_volume(self) -> float:
        """Average volume per 1-min candle"""
        if not self.candle_volumes:
            return 0.0
        return sum(self.candle_volumes) / len(self.candle_volumes)

    def get_recent_avg_volume(self, lookback: int = 5) -> float:
        """Average volume of last N candles"""
        if not self.candle_volumes:
            return 0.0
        recent = self.candle_volumes[-lookback:]
        return sum(recent) / len(recent)

    def reset(self):
        """Reset for new trading day"""
        self.cumulative_tp_vol = 0.0
        self.cumulative_vol = 0
        self.vwap = 0.0
        self.candle_count = 0
        self.candle_volumes = []


# ─── Schwab Share Trading Client ──────────────────────────────────────────────

class MomentumSchwabClient(SchwabClient):
    """
    Extended Schwab client with SHARE trading capabilities.
    Inherits all options functionality + adds equity orders.
    """

    async def place_equity_order(self, symbol: str, instruction: str,
                                  quantity: int, limit_price: Optional[float] = None,
                                  order_type: str = "LIMIT") -> Dict:
        """
        Place a share buy/sell order.

        Args:
            symbol: Stock ticker (e.g., "ABCD")
            instruction: "BUY" or "SELL"
            quantity: Number of shares
            limit_price: Limit price (required for LIMIT orders)
            order_type: "LIMIT" or "MARKET"
        """
        await self._ensure_valid_token()

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        url = f"{self.config.api_base}/trader/v1/accounts/{self.account_hash}/orders"

        order_data = {
            "orderType": order_type,
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": instruction,
                    "quantity": quantity,
                    "instrument": {
                        "symbol": symbol,
                        "assetType": "EQUITY"
                    }
                }
            ]
        }

        if order_type == "LIMIT" and limit_price is not None:
            order_data["price"] = str(round(limit_price, 2))

        start_time = time.perf_counter()

        async with self.session.post(url, headers=headers, json=order_data) as resp:
            latency = (time.perf_counter() - start_time) * 1000

            if resp.status in [200, 201]:
                location = resp.headers.get("Location", "")
                order_id = location.split("/")[-1] if location else ""
                logger.info(
                    f"Order placed in {latency:.0f}ms: {instruction} {quantity}x {symbol} "
                    f"@ ${limit_price:.2f if limit_price else 'MKT'}"
                )
                return {"orderId": order_id, "status": "PLACED", "limit_price": limit_price}
            else:
                error = await resp.text()
                logger.error(f"Equity order failed ({resp.status}): {error[:300]}")
                return {"error": error}

    async def get_quote(self, symbol: str) -> Optional[Dict]:
        """Get real-time quote for a single symbol"""
        await self._ensure_valid_token()
        headers = {"Authorization": f"Bearer {self.access_token}"}

        url = f"{self.config.api_base}/marketdata/v1/quotes"
        params = {"symbols": symbol, "indicative": "true"}

        async with self.session.get(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                if symbol in data:
                    return data[symbol].get("quote", {})
        return None

    async def get_quotes_batch(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get quotes for multiple symbols"""
        await self._ensure_valid_token()
        headers = {"Authorization": f"Bearer {self.access_token}"}

        url = f"{self.config.api_base}/marketdata/v1/quotes"
        params = {"symbols": ",".join(symbols), "indicative": "true"}

        results = {}
        async with self.session.get(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                for sym in symbols:
                    if sym in data:
                        results[sym] = data[sym].get("quote", {})

        return results

    async def get_price_history(self, symbol: str, period_type: str = "day",
                                period: int = 1, freq_type: str = "minute",
                                frequency: int = 1,
                                extended: bool = True) -> List[Dict]:
        """
        Get historical candles for VWAP calculation.
        Returns list of candles: {open, high, low, close, volume, datetime}
        """
        await self._ensure_valid_token()
        headers = {"Authorization": f"Bearer {self.access_token}"}

        url = f"{self.config.api_base}/marketdata/v1/pricehistory"
        params = {
            "symbol": symbol,
            "periodType": period_type,
            "period": period,
            "frequencyType": freq_type,
            "frequency": frequency,
            "needExtendedHoursData": str(extended).lower()
        }

        async with self.session.get(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("candles", [])

        return []

    async def get_equity_positions(self) -> List[Dict]:
        """Get current equity (stock) positions"""
        await self._ensure_valid_token()
        headers = {"Authorization": f"Bearer {self.access_token}"}

        url = f"{self.config.api_base}/trader/v1/accounts/{self.account_hash}"
        params = {"fields": "positions"}

        async with self.session.get(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                positions = data.get("securitiesAccount", {}).get("positions", [])
                return [p for p in positions if p.get("instrument", {}).get("assetType") == "EQUITY"]
        return []

    async def get_settled_cash(self) -> Tuple[float, float]:
        """
        Get settled and unsettled cash for cash account.
        Returns: (settled_cash, total_cash)
        """
        await self._ensure_valid_token()
        headers = {"Authorization": f"Bearer {self.access_token}"}

        url = f"{self.config.api_base}/trader/v1/accounts/{self.account_hash}"

        async with self.session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                balances = data.get("securitiesAccount", {}).get("currentBalances", {})

                total = float(balances.get("cashBalance", 0))
                buying_power = float(balances.get("buyingPower", 0))
                # For cash accounts, buying power ≈ settled cash
                return buying_power, total

        return 0.0, 0.0


# ─── Position Manager ─────────────────────────────────────────────────────────

@dataclass
class OpenPosition:
    """Tracks an open share position"""
    symbol: str
    shares: int
    entry_price: float
    entry_time: float
    signal_type: EntrySignal
    stop_price: float
    target_price: float
    trailing_stop_active: bool = False
    trailing_stop_price: float = 0.0
    high_water_mark: float = 0.0
    partial_filled: bool = False     # True if we already took partial profit
    order_id: Optional[str] = None

    @property
    def cost_basis(self) -> float:
        return self.shares * self.entry_price

    def pnl_at(self, current_price: float) -> Tuple[float, float]:
        """Returns (pnl_dollars, pnl_percent)"""
        pnl = (current_price - self.entry_price) * self.shares
        pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100
        return pnl, pnl_pct


# ─── Main Strategy ────────────────────────────────────────────────────────────

class MomentumScalpStrategy:
    """
    Ross Cameron-style momentum scalping strategy.

    Flow:
    1. Pre-market: Scanner provides watchlist of 3-5 gappers
    2. At open: Initialize VWAP trackers per ticker
    3. Monitor: Poll quotes, update VWAP, check for entry signals
    4. Entry: VWAP reclaim or PM high breakout + volume confirmation
    5. Manage: Tight stops, trail after profit, time-based exit
    6. Repeat until max trades or trading window ends
    """

    def __init__(self, client: MomentumSchwabClient, config: ScalpConfig,
                 scanner: MomentumScanner, paper_mode: bool = True):
        self.client = client
        self.config = config
        self.scanner = scanner
        self.paper_mode = paper_mode

        # Active watchlist
        self.watchlist: List[GapCandidate] = []
        self.watchlist_symbols: List[str] = []

        # VWAP trackers per ticker
        self.vwap_trackers: Dict[str, VWAPTracker] = {}

        # Pre-market data
        self.premarket_highs: Dict[str, float] = {}
        self.premarket_lows: Dict[str, float] = {}

        # Position tracking
        self.position: Optional[OpenPosition] = None
        self.running: bool = False

        # Daily tracking
        self.trades_today: List[TradeRecord] = []
        self.daily_pnl: float = 0.0
        self.settled_cash: float = 0.0
        self.total_cash: float = 0.0
        self.last_reset_date: Optional[date] = None

        # Price history per ticker (recent 1-min candles)
        self.last_candle_time: Dict[str, float] = {}

        # State tracking for signals
        self.candles_above_vwap: Dict[str, int] = {}  # Consecutive candles above VWAP

    def stop(self):
        self.running = False

    # ── Daily Reset ──

    def _reset_daily(self):
        """Reset for new trading day"""
        today = date.today()
        if self.last_reset_date == today:
            return

        logger.info("📅 New trading day — resetting state")
        self.trades_today = []
        self.daily_pnl = 0.0
        self.position = None
        self.vwap_trackers = {}
        self.premarket_highs = {}
        self.premarket_lows = {}
        self.candles_above_vwap = {}
        self.last_candle_time = {}
        self.last_reset_date = today

    # ── Time Checks ──

    def _current_time_str(self) -> str:
        return datetime.now().strftime("%H:%M")

    def _is_trading_hours(self) -> bool:
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        t = self._current_time_str()
        return self.config.trading_start <= t <= self.config.trading_end

    def _is_market_open(self) -> bool:
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        t = self._current_time_str()
        return "09:30" <= t <= "16:00"

    def _can_enter_new_trade(self) -> bool:
        """Check all conditions for new entry"""
        t = self._current_time_str()

        # Time window
        if t > self.config.no_new_entries_after:
            return False

        # Trade count
        if len(self.trades_today) >= self.config.max_trades_per_day:
            logger.info(f"Max trades reached ({self.config.max_trades_per_day})")
            return False

        # Daily loss limit
        if abs(self.daily_pnl) >= self.config.max_daily_loss_dollars and self.daily_pnl < 0:
            logger.warning(f"🛑 Daily loss limit hit: ${self.daily_pnl:.2f}")
            return False

        # Already in position
        if self.position is not None:
            return False

        return True

    # ── Position Sizing ──

    def calculate_position_size(self, entry_price: float, stop_price: float) -> int:
        """
        Calculate shares based on risk.
        shares = risk_dollars / (entry_price - stop_price)
        """
        risk_per_share = abs(entry_price - stop_price)
        if risk_per_share <= 0:
            return 0

        # Available cash (settled only)
        available = self.settled_cash - self.config.cash_buffer_dollars
        if available <= 0:
            logger.warning(f"No settled cash available (${self.settled_cash:.2f} - ${self.config.cash_buffer_dollars} buffer)")
            return 0

        # Risk-based sizing
        risk_dollars = min(
            self.total_cash * (self.config.max_risk_per_trade_pct / 100),
            self.config.max_risk_per_trade_dollars
        )

        shares_by_risk = int(risk_dollars / risk_per_share)

        # Position cap (max % of account)
        max_position_dollars = self.total_cash * (self.config.max_position_pct / 100)
        shares_by_cap = int(max_position_dollars / entry_price)

        # Cash constraint
        shares_by_cash = int(available / entry_price)

        shares = min(shares_by_risk, shares_by_cap, shares_by_cash)

        # Minimum 1 share
        shares = max(shares, 0)

        if shares > 0:
            total_cost = shares * entry_price
            actual_risk = shares * risk_per_share
            logger.info(
                f"Position size: {shares} shares @ ${entry_price:.2f} = "
                f"${total_cost:.2f} | Risk: ${actual_risk:.2f} "
                f"(stop @ ${stop_price:.2f})"
            )

        return shares

    # ── VWAP & Candle Updates ──

    async def update_candles(self):
        """Fetch latest 1-min candles and update VWAP trackers"""
        for symbol in self.watchlist_symbols:
            try:
                candles = await self.client.get_price_history(
                    symbol, period_type="day", period=1,
                    freq_type="minute", frequency=1,
                    extended=False
                )

                if not candles:
                    continue

                tracker = self.vwap_trackers.get(symbol)
                if not tracker:
                    tracker = VWAPTracker()
                    self.vwap_trackers[symbol] = tracker

                last_time = self.last_candle_time.get(symbol, 0)

                for candle in candles:
                    candle_ts = candle.get("datetime", 0) / 1000  # ms → s
                    if candle_ts <= last_time:
                        continue

                    tracker.update(
                        high=candle["high"],
                        low=candle["low"],
                        close=candle["close"],
                        volume=candle["volume"]
                    )
                    self.last_candle_time[symbol] = candle_ts

                    # Track candles above VWAP
                    if tracker.vwap > 0:
                        if candle["close"] > tracker.vwap:
                            self.candles_above_vwap[symbol] = \
                                self.candles_above_vwap.get(symbol, 0) + 1
                        else:
                            self.candles_above_vwap[symbol] = 0

            except Exception as e:
                logger.error(f"Error updating candles for {symbol}: {e}")

    # ── Entry Signal Detection ──

    def detect_vwap_entry(self, symbol: str, quote: Dict) -> Optional[Tuple[float, float]]:
        """
        Detect VWAP pullback reclaim entry.

        Signal fires when:
        1. Price pulled back near VWAP (within threshold %)
        2. Price is reclaiming above VWAP
        3. Has held above VWAP for N candles
        4. Volume is above average

        Returns: (entry_price, stop_price) or None
        """
        if not self.config.vwap_entry_enabled:
            return None

        tracker = self.vwap_trackers.get(symbol)
        if not tracker or tracker.vwap <= 0:
            return None

        price = float(quote.get("lastPrice", 0))
        if price <= 0:
            return None

        vwap = tracker.vwap
        distance_pct = ((price - vwap) / vwap) * 100

        # Price must be above VWAP but close to it (pullback zone)
        if not (0 < distance_pct <= self.config.vwap_pullback_percent):
            return None

        # Must have held above VWAP for N candles
        candles_above = self.candles_above_vwap.get(symbol, 0)
        if candles_above < self.config.vwap_reclaim_candles:
            return None

        # Volume confirmation
        recent_vol = tracker.get_recent_avg_volume(3)
        avg_vol = tracker.get_avg_candle_volume()
        if avg_vol > 0 and recent_vol < avg_vol * self.config.min_volume_surge:
            return None

        # Entry at current price, stop below VWAP
        entry_price = price
        stop_price = vwap * (1 - self.config.stop_loss_percent / 100)

        logger.info(
            f"📈 VWAP RECLAIM signal [{symbol}]: "
            f"Price ${price:.2f} | VWAP ${vwap:.2f} | "
            f"Distance {distance_pct:.2f}% | "
            f"Candles above: {candles_above}"
        )

        return entry_price, stop_price

    def detect_breakout_entry(self, symbol: str, quote: Dict) -> Optional[Tuple[float, float]]:
        """
        Detect pre-market high breakout.

        Signal fires when:
        1. Price breaks above pre-market high
        2. Breakout is confirmed by volume surge
        3. Not a fakeout (buffer %)

        Returns: (entry_price, stop_price) or None
        """
        if not self.config.breakout_entry_enabled:
            return None

        pm_high = self.premarket_highs.get(symbol)
        if not pm_high or pm_high <= 0:
            return None

        price = float(quote.get("lastPrice", 0))
        if price <= 0:
            return None

        # Must break PM high by buffer amount
        breakout_level = pm_high * (1 + self.config.breakout_buffer_percent / 100)

        if price < breakout_level:
            return None

        # Volume confirmation
        tracker = self.vwap_trackers.get(symbol)
        if tracker:
            recent_vol = tracker.get_recent_avg_volume(1)  # Last candle
            avg_vol = tracker.get_avg_candle_volume()
            if avg_vol > 0 and recent_vol < avg_vol * self.config.breakout_volume_multiplier:
                return None

        # Entry at current price, stop below PM high
        entry_price = price
        stop_price = pm_high * (1 - self.config.stop_loss_percent / 100)

        logger.info(
            f"🚀 PM HIGH BREAKOUT signal [{symbol}]: "
            f"Price ${price:.2f} | PM High ${pm_high:.2f} | "
            f"Break by +{((price - pm_high) / pm_high) * 100:.2f}%"
        )

        return entry_price, stop_price

    # ── Trade Execution ──

    async def execute_entry(self, symbol: str, entry_price: float,
                            stop_price: float, signal_type: EntrySignal):
        """Execute a buy order"""
        shares = self.calculate_position_size(entry_price, stop_price)

        if shares <= 0:
            logger.warning(f"Cannot size position for {symbol} — insufficient funds or risk too high")
            return

        target_price = entry_price * (1 + self.config.take_profit_percent / 100)

        if self.paper_mode:
            logger.info(
                f"📝 PAPER BUY: {shares}x {symbol} @ ${entry_price:.2f} | "
                f"Stop: ${stop_price:.2f} | Target: ${target_price:.2f}"
            )
            self.position = OpenPosition(
                symbol=symbol,
                shares=shares,
                entry_price=entry_price,
                entry_time=time.time(),
                signal_type=signal_type,
                stop_price=stop_price,
                target_price=target_price,
                high_water_mark=entry_price,
            )
            self.settled_cash -= shares * entry_price
            return

        # Live order — use limit slightly above ask for fill
        ask = entry_price * 1.002  # 0.2% above for quick fill
        limit = round(ask, 2)

        result = await self._place_order_with_chase(symbol, "BUY", shares, limit)

        if result and result.get("filled"):
            fill_price = result.get("fill_price", limit)
            # Recalculate stop relative to actual fill
            stop_price = fill_price * (1 - self.config.stop_loss_percent / 100)
            target_price = fill_price * (1 + self.config.take_profit_percent / 100)

            self.position = OpenPosition(
                symbol=symbol,
                shares=shares,
                entry_price=fill_price,
                entry_time=time.time(),
                signal_type=signal_type,
                stop_price=stop_price,
                target_price=target_price,
                high_water_mark=fill_price,
                order_id=result.get("orderId"),
            )

            logger.info(
                f"✅ BOUGHT: {shares}x {symbol} @ ${fill_price:.2f} | "
                f"Stop: ${stop_price:.2f} | Target: ${target_price:.2f}"
            )

    async def _place_order_with_chase(self, symbol: str, instruction: str,
                                       quantity: int, limit_price: float,
                                       max_attempts: int = 3) -> Optional[Dict]:
        """Place order and chase if not filled"""
        price = limit_price

        for attempt in range(max_attempts):
            result = await self.client.place_equity_order(
                symbol=symbol,
                instruction=instruction,
                quantity=quantity,
                limit_price=price,
                order_type="LIMIT"
            )

            if not result or "error" in result:
                return None

            order_id = result.get("orderId")
            if not order_id:
                return None

            # Wait for fill
            for _ in range(30):  # 3 seconds
                status = await self.client.get_order_status(order_id)
                if status:
                    s = status.get("status")
                    if s == "FILLED":
                        fill = float(status.get("price", price))
                        return {"orderId": order_id, "filled": True, "fill_price": fill}
                    elif s in ["CANCELED", "REJECTED", "EXPIRED"]:
                        break
                await asyncio.sleep(0.1)

            # Cancel and retry with more aggressive price
            await self.client.cancel_order(order_id)

            if attempt < max_attempts - 1:
                if instruction == "BUY":
                    price = round(price * 1.003, 2)  # Chase up 0.3%
                else:
                    price = round(price * 0.997, 2)  # Chase down 0.3%
                logger.info(f"Chasing {instruction}: attempt {attempt + 2}, new limit ${price:.2f}")

        return None

    # ── Position Management ──

    async def manage_position(self):
        """Manage open position: stop loss, take profit, trailing stop, time exit"""
        if not self.position:
            return

        pos = self.position
        quote = await self.client.get_quote(pos.symbol)

        if not quote:
            return

        price = float(quote.get("lastPrice", 0))
        if price <= 0:
            return

        pnl, pnl_pct = pos.pnl_at(price)

        should_exit = False
        exit_reason = ""
        exit_shares = pos.shares

        # ── Stop Loss ──
        if price <= pos.stop_price:
            should_exit = True
            exit_reason = f"STOP LOSS hit @ ${price:.2f} ({pnl_pct:+.1f}%)"

        # ── Take Profit (Partial) ──
        if not should_exit and pnl_pct >= self.config.take_profit_percent and not pos.partial_filled:
            partial_shares = int(pos.shares * self.config.take_profit_partial)
            if partial_shares > 0:
                logger.info(f"🎯 Partial TP: Selling {partial_shares}/{pos.shares} shares at ${price:.2f} (+{pnl_pct:.1f}%)")
                await self._exit_shares(pos.symbol, partial_shares, price,
                                         f"Partial TP (+{pnl_pct:.1f}%)")
                pos.shares -= partial_shares
                pos.partial_filled = True
                # Tighten stop to breakeven after partial
                pos.stop_price = max(pos.stop_price, pos.entry_price)
                logger.info(f"Stop moved to breakeven @ ${pos.entry_price:.2f}")
                return  # Don't full exit yet

        # ── Trailing Stop ──
        if not should_exit and self.config.trailing_stop_enabled:
            if pnl_pct >= self.config.trailing_stop_activation_pct:
                if not pos.trailing_stop_active:
                    pos.trailing_stop_active = True
                    pos.high_water_mark = price
                    pos.trailing_stop_price = price * (1 - self.config.trailing_stop_distance_pct / 100)
                    logger.info(f"Trailing stop activated @ ${pos.trailing_stop_price:.2f} (high: ${price:.2f})")

                if price > pos.high_water_mark:
                    pos.high_water_mark = price
                    new_trail = price * (1 - self.config.trailing_stop_distance_pct / 100)
                    if new_trail > pos.trailing_stop_price:
                        pos.trailing_stop_price = new_trail

                if price <= pos.trailing_stop_price:
                    should_exit = True
                    exit_reason = f"TRAILING STOP hit @ ${price:.2f} ({pnl_pct:+.1f}%)"

        # ── Time Exit ──
        if not should_exit:
            hold_minutes = (time.time() - pos.entry_time) / 60
            if hold_minutes >= self.config.max_hold_minutes:
                should_exit = True
                exit_reason = f"TIME EXIT ({hold_minutes:.0f} min)"

        # ── EOD Exit ──
        if not should_exit:
            if self._current_time_str() >= self.config.eod_exit_time:
                should_exit = True
                exit_reason = "EOD EXIT"

        # ── Execute Exit ──
        if should_exit:
            await self._exit_shares(pos.symbol, pos.shares, price, exit_reason)
            self.position = None

    async def _exit_shares(self, symbol: str, shares: int, price: float, reason: str):
        """Sell shares"""
        if self.paper_mode:
            logger.info(f"📝 PAPER SELL: {shares}x {symbol} @ ${price:.2f} | {reason}")
            fill_price = price
        else:
            # Use limit slightly below bid for quick fill
            limit = round(price * 0.998, 2)
            result = await self._place_order_with_chase(symbol, "SELL", shares, limit)

            if result and result.get("filled"):
                fill_price = result.get("fill_price", limit)
            else:
                # Emergency market order
                logger.warning(f"Limit sell failed, using MARKET order for {symbol}")
                await self.client.place_equity_order(symbol, "SELL", shares, order_type="MARKET")
                fill_price = price  # Approximate

        # Record trade
        if self.position:
            entry = self.position.entry_price
            pnl = (fill_price - entry) * shares
            pnl_pct = ((fill_price - entry) / entry) * 100

            record = TradeRecord(
                symbol=symbol,
                side="SELL",
                shares=shares,
                entry_price=entry,
                exit_price=fill_price,
                entry_time=datetime.fromtimestamp(self.position.entry_time),
                exit_time=datetime.now(),
                signal_type=self.position.signal_type.value,
                pnl_dollars=pnl,
                pnl_percent=pnl_pct,
            )
            self.trades_today.append(record)
            self.daily_pnl += pnl
            self.settled_cash += shares * fill_price  # Goes to unsettled actually

            emoji = "💰" if pnl > 0 else "💸"
            logger.info(
                f"{emoji} CLOSED [{symbol}]: {reason} | "
                f"Entry: ${entry:.2f} → Exit: ${fill_price:.2f} | "
                f"P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%) | "
                f"Daily: ${self.daily_pnl:+.2f} ({len(self.trades_today)} trades)"
            )

    # ── Main Trading Loop ──

    async def run(self):
        """Main trading loop"""
        self.running = True
        self._reset_daily()

        # Get account info
        try:
            self.settled_cash, self.total_cash = await self.client.get_settled_cash()
            logger.info(f"💰 Account: ${self.total_cash:.2f} total, ${self.settled_cash:.2f} settled")
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            return

        logger.info("=" * 60)
        logger.info(f"  🚀 MOMENTUM SCALP BOT — {'PAPER' if self.paper_mode else 'LIVE'} MODE")
        logger.info(f"  Watchlist: {', '.join(self.watchlist_symbols)}")
        logger.info(f"  Entry modes: {self.config.entry_mode}")
        logger.info(f"  Risk/trade: {self.config.max_risk_per_trade_pct}% (max ${self.config.max_risk_per_trade_dollars})")
        logger.info(f"  Max trades: {self.config.max_trades_per_day}/day")
        logger.info(f"  Trading window: {self.config.trading_start} - {self.config.no_new_entries_after}")
        logger.info("=" * 60)

        last_candle_update = 0
        last_heartbeat = 0
        candle_interval = self.config.candle_interval_seconds

        while self.running:
            try:
                now = time.time()

                # Heartbeat
                if now - last_heartbeat >= 300:
                    status = "SCANNING" if not self.position else f"IN POSITION ({self.position.symbol})"
                    logger.info(
                        f"[Heartbeat] {status} | Trades: {len(self.trades_today)} | "
                        f"P&L: ${self.daily_pnl:+.2f}"
                    )
                    last_heartbeat = now

                if not self._is_market_open():
                    await asyncio.sleep(5)
                    continue

                # Update candles + VWAP every minute
                if now - last_candle_update >= candle_interval:
                    await self.update_candles()
                    last_candle_update = now

                # Manage existing position
                if self.position:
                    await self.manage_position()
                    await asyncio.sleep(self.config.quote_poll_interval)
                    continue

                # Look for new entries
                if self._can_enter_new_trade() and self._is_trading_hours():
                    quotes = await self.client.get_quotes_batch(self.watchlist_symbols)

                    for symbol in self.watchlist_symbols:
                        if symbol not in quotes:
                            continue

                        quote = quotes[symbol]

                        # Try VWAP entry
                        if self.config.entry_mode in ("vwap", "both"):
                            result = self.detect_vwap_entry(symbol, quote)
                            if result:
                                entry_price, stop_price = result
                                await self.execute_entry(
                                    symbol, entry_price, stop_price,
                                    EntrySignal.VWAP_RECLAIM
                                )
                                break

                        # Try breakout entry
                        if self.config.entry_mode in ("breakout", "both"):
                            result = self.detect_breakout_entry(symbol, quote)
                            if result:
                                entry_price, stop_price = result
                                await self.execute_entry(
                                    symbol, entry_price, stop_price,
                                    EntrySignal.PM_HIGH_BREAKOUT
                                )
                                break

                await asyncio.sleep(self.config.quote_poll_interval)

            except Exception as e:
                logger.error(f"Error in scalp loop: {type(e).__name__}: {e}", exc_info=True)
                await asyncio.sleep(2)

    def set_watchlist(self, candidates: List[GapCandidate]):
        """Set watchlist from scanner results"""
        self.watchlist = candidates
        self.watchlist_symbols = [c.symbol for c in candidates]
        self.premarket_highs = {c.symbol: c.day_high for c in candidates}
        self.premarket_lows = {c.symbol: c.day_low for c in candidates}

        # Initialize VWAP trackers
        for sym in self.watchlist_symbols:
            self.vwap_trackers[sym] = VWAPTracker()
            self.candles_above_vwap[sym] = 0

    def get_daily_summary(self) -> str:
        """Get end-of-day summary"""
        if not self.trades_today:
            return "No trades today."

        wins = [t for t in self.trades_today if t.pnl_dollars > 0]
        losses = [t for t in self.trades_today if t.pnl_dollars <= 0]
        win_rate = len(wins) / len(self.trades_today) * 100

        avg_win = sum(t.pnl_dollars for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.pnl_dollars for t in losses) / len(losses) if losses else 0

        lines = [
            f"\n{'=' * 50}",
            f"  📊 DAILY SUMMARY — {date.today().isoformat()}",
            f"{'=' * 50}",
            f"  Trades: {len(self.trades_today)} | Win Rate: {win_rate:.0f}%",
            f"  Wins: {len(wins)} (avg ${avg_win:+.2f}) | Losses: {len(losses)} (avg ${avg_loss:+.2f})",
            f"  Daily P&L: ${self.daily_pnl:+.2f}",
            f"{'=' * 50}",
        ]

        for t in self.trades_today:
            emoji = "✅" if t.pnl_dollars > 0 else "❌"
            lines.append(
                f"  {emoji} {t.symbol}: {t.shares}sh | "
                f"${t.entry_price:.2f}→${t.exit_price:.2f} | "
                f"${t.pnl_dollars:+.2f} ({t.pnl_percent:+.1f}%) | {t.signal_type}"
            )

        return "\n".join(lines)
