#!/usr/bin/env python3
"""
0DTE SPY Options Momentum Trading Bot for Schwab
Adapted from the futures momentum strategy for options trading

Key Features:
- Schwab API integration (formerly TD Ameritrade)
- 0DTE options focus with automatic strike selection
- Momentum-based entry signals
- Options-specific risk management (theta decay awareness)
- Delta-based position sizing
"""

import asyncio
import aiohttp
import json
import time
import logging
import base64
import hashlib
import secrets
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import deque
from enum import Enum
from urllib.parse import urlencode

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class OptionType(Enum):
    CALL = "CALL"
    PUT = "PUT"


class OrderSide(Enum):
    BUY_TO_OPEN = "BUY_TO_OPEN"
    SELL_TO_CLOSE = "SELL_TO_CLOSE"
    BUY_TO_CLOSE = "BUY_TO_CLOSE"
    SELL_TO_OPEN = "SELL_TO_OPEN"


@dataclass
class OptionsConfig:
    """Configuration for 0DTE options trading"""
    # Strategy parameters
    time_window: int = 14  # seconds to measure momentum
    min_price_movement: float = 0.50  # SPY dollars (not ticks)
    max_positions: int = 1

    # Options-specific - ADJUSTED for slippage
    target_delta: float = 0.45  # Slightly higher delta = higher premium = spread less impactful
    max_bid_ask_spread: float = 0.08  # Tighter spread requirement (was 0.10)
    min_option_price: float = 1.50  # Minimum premium to trade (spread less % impact on higher priced)
    min_volume: int = 500  # Minimum volume for liquidity
    min_open_interest: int = 1000  # Minimum OI for liquidity

    # Risk management - WIDENED for slippage reality
    stop_loss_percent: float = 35.0  # INCREASED from 30 - wider to avoid slippage-triggered stops
    take_profit_percent: float = 60.0  # INCREASED from 50 - need higher target to overcome spread
    max_theta_decay_risk: float = 0.05  # Max acceptable theta as % of premium

    # Slippage-aware order settings
    use_aggressive_limit: bool = True  # Use ask+offset for buys, bid-offset for sells
    limit_offset_cents: float = 0.02  # $0.02 above ask for buys (to get filled)
    order_timeout_seconds: float = 3.0  # Wait for fill before re-pricing
    max_chase_attempts: int = 3  # How many times to chase price
    chase_increment_cents: float = 0.03  # Add this much each chase attempt

    # Time filters (avoid dangerous periods)
    no_trade_after: str = "15:00"  # EARLIER cutoff (was 15:30) - spreads widen late
    no_trade_before: str = "09:45"  # No trades in first 15 min
    avoid_first_minutes_after_open: int = 15  # Extra buffer for volatility

    # Underlying
    symbol: str = "SPY"

    # Schwab API
    api_base: str = "https://api.schwabapi.com"
    auth_url: str = "https://api.schwabapi.com/v1/oauth/authorize"
    token_url: str = "https://api.schwabapi.com/v1/oauth/token"


@dataclass
class OptionContract:
    """Represents an option contract"""
    symbol: str  # OCC symbol (e.g., SPY240119C00470000)
    underlying: str
    option_type: OptionType
    strike: float
    expiration: date
    bid: float
    ask: float
    last: float
    delta: float
    gamma: float
    theta: float
    vega: float
    volume: int
    open_interest: int

    @property
    def mid_price(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def spread_percent(self) -> float:
        if self.mid_price > 0:
            return self.spread / self.mid_price
        return float('inf')


@dataclass
class PriceSnapshot:
    """SPY price snapshot"""
    timestamp: float
    price: float
    bid: float
    ask: float
    volume: int = 0


class SchwabClient:
    """
    Schwab API client for options trading
    Handles OAuth2 authentication and trading operations
    """

    def __init__(self, config: OptionsConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self.account_hash: Optional[str] = None

    async def initialize(self, client_id: str, client_secret: str, refresh_token: str):
        """
        Initialize the client with OAuth credentials

        Note: Schwab uses OAuth2 with PKCE. For automated trading:
        1. First-time: Complete OAuth flow in browser to get refresh_token
        2. Subsequent: Use refresh_token to get new access_token
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token

        self.session = aiohttp.ClientSession()

        # Get access token using refresh token
        await self._refresh_access_token()

        # Get account hash
        await self._get_account_hash()

        logger.info(f"Schwab client initialized. Account: {self.account_hash[:8]}...")

    async def _refresh_access_token(self):
        """Refresh the access token"""
        auth_string = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        headers = {
            "Authorization": f"Basic {auth_string}",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token
        }

        async with self.session.post(
            self.config.token_url,
            headers=headers,
            data=data
        ) as resp:
            if resp.status == 200:
                token_data = await resp.json()
                self.access_token = token_data["access_token"]
                self.refresh_token = token_data.get("refresh_token", self.refresh_token)
                expires_in = token_data.get("expires_in", 1800)
                self.token_expiry = datetime.now() + timedelta(seconds=expires_in - 60)
                logger.info("Access token refreshed")
            else:
                error = await resp.text()
                raise Exception(f"Token refresh failed: {error}")

    async def _ensure_valid_token(self):
        """Ensure we have a valid access token"""
        if not self.token_expiry or datetime.now() >= self.token_expiry:
            await self._refresh_access_token()

    async def _get_account_hash(self):
        """Get the account hash needed for trading"""
        await self._ensure_valid_token()

        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.config.api_base}/trader/v1/accounts/accountNumbers"

        async with self.session.get(url, headers=headers) as resp:
            if resp.status == 200:
                accounts = await resp.json()
                if accounts:
                    self.account_hash = accounts[0]["hashValue"]
            else:
                raise Exception(f"Failed to get accounts: {await resp.text()}")

    async def get_quote(self, symbol: str = "SPY") -> Optional[PriceSnapshot]:
        """Get real-time quote for underlying"""
        await self._ensure_valid_token()

        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.config.api_base}/marketdata/v1/quotes"
        params = {"symbols": symbol}

        async with self.session.get(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                if symbol in data:
                    quote = data[symbol]["quote"]
                    return PriceSnapshot(
                        timestamp=time.time(),
                        price=quote.get("lastPrice", 0),
                        bid=quote.get("bidPrice", 0),
                        ask=quote.get("askPrice", 0),
                        volume=quote.get("totalVolume", 0)
                    )
        return None

    async def get_option_chain(self, symbol: str = "SPY",
                                expiration: Optional[date] = None) -> List[OptionContract]:
        """
        Get option chain for 0DTE
        Returns calls and puts for today's expiration
        """
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
                                contracts.append(self._parse_option(opt, OptionType.CALL))

                # Parse puts
                if "putExpDateMap" in data:
                    for exp_date, strikes in data["putExpDateMap"].items():
                        for strike, options in strikes.items():
                            for opt in options:
                                contracts.append(self._parse_option(opt, OptionType.PUT))

        return contracts

    def _parse_option(self, opt_data: Dict, option_type: OptionType) -> OptionContract:
        """Parse option data from API response"""
        return OptionContract(
            symbol=opt_data.get("symbol", ""),
            underlying=self.config.symbol,
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

    async def place_option_order(self, contract: OptionContract,
                                  side: OrderSide, quantity: int = 1,
                                  limit_price: Optional[float] = None) -> Dict:
        """Place an option order"""
        await self._ensure_valid_token()

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        url = f"{self.config.api_base}/trader/v1/accounts/{self.account_hash}/orders"

        # Always use LIMIT for options - MARKET orders get terrible fills
        order_type = "LIMIT"
        if limit_price is None:
            limit_price = contract.mid_price

        order_data = {
            "orderType": order_type,
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": side.value,
                    "quantity": quantity,
                    "instrument": {
                        "symbol": contract.symbol,
                        "assetType": "OPTION"
                    }
                }
            ],
            "price": str(round(limit_price, 2))
        }

        start_time = time.perf_counter()

        async with self.session.post(url, headers=headers, json=order_data) as resp:
            latency = (time.perf_counter() - start_time) * 1000

            if resp.status in [200, 201]:
                location = resp.headers.get("Location", "")
                order_id = location.split("/")[-1] if location else ""
                logger.info(f"Order placed in {latency:.2f}ms: {side.value} {quantity}x {contract.symbol} @ ${limit_price:.2f}")
                return {"orderId": order_id, "status": "PLACED", "limit_price": limit_price}
            else:
                error = await resp.text()
                logger.error(f"Order failed: {error}")
                return {"error": error}

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order"""
        await self._ensure_valid_token()

        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.config.api_base}/trader/v1/accounts/{self.account_hash}/orders/{order_id}"

        async with self.session.delete(url, headers=headers) as resp:
            if resp.status in [200, 204]:
                logger.info(f"Order {order_id} cancelled")
                return True
            return False

    async def get_order_status(self, order_id: str) -> Optional[Dict]:
        """Get detailed order status"""
        await self._ensure_valid_token()

        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.config.api_base}/trader/v1/accounts/{self.account_hash}/orders/{order_id}"

        async with self.session.get(url, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
        return None

    async def get_positions(self) -> List[Dict]:
        """Get current option positions"""
        await self._ensure_valid_token()

        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.config.api_base}/trader/v1/accounts/{self.account_hash}"
        params = {"fields": "positions"}

        async with self.session.get(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                positions = data.get("securitiesAccount", {}).get("positions", [])
                # Filter for options only
                return [p for p in positions if p.get("instrument", {}).get("assetType") == "OPTION"]
        return []

    async def close(self):
        """Clean up"""
        if self.session:
            await self.session.close()


class ZeroDTEMomentumStrategy:
    """
    0DTE Options momentum strategy
    Buys calls on bullish momentum, puts on bearish momentum
    """

    def __init__(self, client: SchwabClient, config: OptionsConfig):
        self.client = client
        self.config = config
        self.price_history = deque(maxlen=1000)
        self.last_signal_time = 0
        self.last_signal_price = 0
        self.current_position: Optional[Dict] = None
        self.position_entry_price = 0

    def _is_trading_hours(self) -> bool:
        """Check if within allowed trading hours"""
        now = datetime.now()
        current_time = now.strftime("%H:%M")

        # Check if it's a weekday
        if now.weekday() >= 5:
            return False

        # Check time bounds
        if current_time < self.config.no_trade_before:
            return False
        if current_time > self.config.no_trade_after:
            return False

        return True

    def detect_momentum_signal(self, current: PriceSnapshot) -> Optional[OptionType]:
        """
        Detect momentum signal for options
        Returns CALL (bullish), PUT (bearish), or None
        """
        if not self._is_trading_hours():
            return None

        current_time = current.timestamp
        current_price = current.price

        # Initialize reference point
        if self.last_signal_price == 0:
            self.last_signal_price = current_price
            self.last_signal_time = current_time
            return None

        # Calculate movement
        time_diff = current_time - self.last_signal_time
        price_diff = current_price - self.last_signal_price

        # Check for signal within time window
        if time_diff <= self.config.time_window:
            if abs(price_diff) >= self.config.min_price_movement:
                if self.current_position is None:
                    # Update reference
                    self.last_signal_price = current_price
                    self.last_signal_time = current_time

                    if price_diff > 0:
                        logger.info(f"BULLISH Signal: SPY +${price_diff:.2f} in {time_diff:.1f}s")
                        return OptionType.CALL
                    else:
                        logger.info(f"BEARISH Signal: SPY ${price_diff:.2f} in {time_diff:.1f}s")
                        return OptionType.PUT

        # Reset reference if window expired
        if time_diff >= self.config.time_window:
            self.last_signal_price = current_price
            self.last_signal_time = current_time

        return None

    async def select_contract(self, option_type: OptionType,
                               spy_price: float) -> Optional[OptionContract]:
        """
        Select the best contract based on delta, spread, and liquidity
        Enhanced with slippage-aware filtering
        """
        chain = await self.client.get_option_chain()

        # Filter by type
        candidates = [c for c in chain if c.option_type == option_type]

        # Target delta (puts have negative delta)
        target_delta = self.config.target_delta
        if option_type == OptionType.PUT:
            target_delta = -target_delta

        # Score contracts with enhanced slippage-aware filtering
        scored = []
        for c in candidates:
            # Basic validity
            if c.bid <= 0 or c.ask <= 0:
                continue

            # SLIPPAGE FILTER 1: Minimum premium (spread is less % impact)
            if c.mid_price < self.config.min_option_price:
                continue

            # SLIPPAGE FILTER 2: Tight spread requirement
            if c.spread_percent > self.config.max_bid_ask_spread:
                continue

            # SLIPPAGE FILTER 3: Minimum volume for liquidity
            if c.volume < self.config.min_volume:
                continue

            # SLIPPAGE FILTER 4: Minimum open interest
            if c.open_interest < self.config.min_open_interest:
                continue

            # Calculate scores (lower is better)
            delta_score = abs(abs(c.delta) - abs(target_delta))
            spread_score = c.spread_percent * 2  # Weight spread heavily

            # Bonus for higher volume (better fills)
            volume_bonus = -min(c.volume / 10000, 0.1)  # Up to -0.1 bonus

            # Combined score
            score = delta_score + spread_score + volume_bonus
            scored.append((score, c))

        if not scored:
            logger.warning(f"No suitable {option_type.value} contracts found "
                          f"(checked {len(candidates)} candidates)")
            return None

        # Return best contract
        scored.sort(key=lambda x: x[0])
        best = scored[0][1]

        # Calculate expected slippage cost
        expected_slippage = best.spread / 2  # Half spread on entry + exit
        slippage_pct = (expected_slippage * 2 / best.mid_price) * 100

        logger.info(f"Selected: {best.symbol} | Strike: ${best.strike} | "
                   f"Delta: {best.delta:.2f} | Bid/Ask: ${best.bid:.2f}/${best.ask:.2f} | "
                   f"Vol: {best.volume} | Est. slippage: {slippage_pct:.1f}%")

        return best

    async def execute_signal(self, signal: OptionType, spy_price: float):
        """Execute the trading signal with slippage-aware order management"""
        # Select contract
        contract = await self.select_contract(signal, spy_price)

        if not contract:
            return

        # Use aggressive limit for better fill probability
        if self.config.use_aggressive_limit:
            # For buying: start at ask + small offset to ensure fill
            limit_price = contract.ask + self.config.limit_offset_cents
        else:
            limit_price = contract.mid_price

        # Place order with retry logic
        result = await self._place_order_with_fill_check(
            contract, limit_price, OrderSide.BUY_TO_OPEN
        )

        if result and result.get("filled"):
            actual_fill = result.get("fill_price", limit_price)
            self.current_position = {
                "contract": contract,
                "entry_price": actual_fill,
                "entry_time": time.time(),
                "order_id": result["orderId"],
                "signal": signal
            }
            self.position_entry_price = actual_fill
            logger.info(f"Position opened: {signal.value} @ ${actual_fill:.2f} "
                       f"(limit was ${limit_price:.2f})")

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

            # Wait for fill with timeout
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

                await asyncio.sleep(0.1)  # Check every 100ms

            # Not filled - cancel and chase
            await self.client.cancel_order(order_id)

            if attempt < self.config.max_chase_attempts - 1:
                # Chase price more aggressively
                if side == OrderSide.BUY_TO_OPEN:
                    limit_price += self.config.chase_increment_cents
                else:
                    limit_price -= self.config.chase_increment_cents

                logger.info(f"Chasing: attempt {attempt + 2}, new limit ${limit_price:.2f}")

                # Refresh contract data for current bid/ask
                chain = await self.client.get_option_chain()
                updated = next((c for c in chain if c.symbol == contract.symbol), None)
                if updated:
                    contract = updated
                    # Don't chase beyond the ask (for buys)
                    if side == OrderSide.BUY_TO_OPEN and limit_price < contract.ask:
                        limit_price = contract.ask + self.config.limit_offset_cents

        logger.warning(f"Order not filled after {self.config.max_chase_attempts} attempts")
        return None

    async def manage_position(self, spy_price: float):
        """Manage open position - check for exit conditions"""
        if not self.current_position:
            return

        contract = self.current_position["contract"]
        entry_price = self.current_position["entry_price"]

        # Get current option price
        chain = await self.client.get_option_chain()
        current_contract = next(
            (c for c in chain if c.symbol == contract.symbol),
            None
        )

        if not current_contract:
            logger.warning("Could not find current contract price")
            return

        current_price = current_contract.mid_price
        pnl_percent = ((current_price - entry_price) / entry_price) * 100

        # Check exit conditions
        should_exit = False
        exit_reason = ""

        # Stop loss
        if pnl_percent <= -self.config.stop_loss_percent:
            should_exit = True
            exit_reason = f"Stop loss hit ({pnl_percent:.1f}%)"

        # Take profit
        elif pnl_percent >= self.config.take_profit_percent:
            should_exit = True
            exit_reason = f"Take profit hit ({pnl_percent:.1f}%)"

        # Time-based exit (close before 3:55 PM)
        current_time = datetime.now().strftime("%H:%M")
        if current_time >= "15:55":
            should_exit = True
            exit_reason = "End of day exit"

        if should_exit:
            await self._close_position(current_contract, exit_reason)

    async def _close_position(self, contract: OptionContract, reason: str):
        """Close the current position with slippage-aware exit"""
        # For exits, use bid - small offset to ensure fill (we're selling)
        if self.config.use_aggressive_limit:
            limit_price = contract.bid - self.config.limit_offset_cents
            # Don't go below a reasonable floor
            limit_price = max(limit_price, 0.01)
        else:
            limit_price = contract.mid_price

        result = await self._place_order_with_fill_check(
            contract, limit_price, OrderSide.SELL_TO_CLOSE
        )

        if result and result.get("filled"):
            entry = self.current_position["entry_price"]
            exit_price = result.get("fill_price", limit_price)
            pnl = (exit_price - entry) * 100  # Per contract ($100 multiplier)
            pnl_percent = ((exit_price - entry) / entry) * 100

            logger.info(f"Position closed: {reason} | Entry: ${entry:.2f} | "
                       f"Exit: ${exit_price:.2f} | P&L: ${pnl:.2f} ({pnl_percent:.1f}%)")
            self.current_position = None
        else:
            # Emergency: if we can't get filled, use market-equivalent (hit the bid)
            logger.warning(f"Fill failed, emergency exit at bid ${contract.bid:.2f}")
            await self.client.place_option_order(
                contract=contract,
                side=OrderSide.SELL_TO_CLOSE,
                quantity=1,
                limit_price=contract.bid - 0.05  # Very aggressive
            )
            self.current_position = None

    async def run(self):
        """Main trading loop"""
        logger.info("Starting 0DTE SPY Options Momentum Strategy...")
        logger.info(f"Config: ${self.config.min_price_movement} SPY move in "
                   f"{self.config.time_window}s triggers signal")
        logger.info(f"Slippage settings: TP={self.config.take_profit_percent}%, "
                   f"SL={self.config.stop_loss_percent}%, "
                   f"Min premium=${self.config.min_option_price}, "
                   f"Max spread={self.config.max_bid_ask_spread*100:.0f}%")

        while True:
            try:
                # Get SPY quote
                snapshot = await self.client.get_quote("SPY")

                if snapshot:
                    self.price_history.append(snapshot)

                    # Check for entry signals (only if no position)
                    if not self.current_position:
                        signal = self.detect_momentum_signal(snapshot)
                        if signal:
                            await self.execute_signal(signal, snapshot.price)

                    # Manage existing position
                    if self.current_position:
                        await self.manage_position(snapshot.price)

                # Polling interval (50ms for options)
                await asyncio.sleep(0.05)

            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                await asyncio.sleep(1)


async def main():
    """
    Main entry point - for direct execution.
    For full functionality, use schwab_0dte_main.py instead.
    """
    # Import config manager
    from schwab_config_manager import SchwabConfigManager

    config_mgr = SchwabConfigManager()

    # Load credentials
    credentials = config_mgr.load_credentials()
    if not credentials:
        credentials = config_mgr.load_credentials_from_keyring()

    if not credentials:
        print("No credentials found. Run: python schwab_0dte_main.py --setup")
        return

    # Load strategy config
    params, underlying, _ = config_mgr.load_strategy_config()

    # Build options config
    config = OptionsConfig(
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

    client = SchwabClient(config)

    try:
        await client.initialize(
            credentials.client_id,
            credentials.client_secret,
            credentials.refresh_token
        )

        strategy = ZeroDTEMomentumStrategy(client, config)
        await strategy.run()

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await client.close()


if __name__ == "__main__":
    print("="*60)
    print("  For full functionality, use: python schwab_0dte_main.py")
    print("  Run --setup first:           python schwab_0dte_main.py --setup")
    print("="*60 + "\n")

    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass

    asyncio.run(main())
