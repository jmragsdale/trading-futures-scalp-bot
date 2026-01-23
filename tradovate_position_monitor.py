#!/usr/bin/env python3
"""
Tradovate Position Monitor Bot

Monitors manually-entered positions and auto-manages:
- Stop loss based on EMA(20) + tick offset
- Breakeven trigger at 3R profit
- Take profit at 2.5R

Listens for TradingView webhook alerts for:
- Stop out signals
- Breakeven triggers
- Timeout exits

Usage:
    python tradovate_position_monitor.py --setup    # First-time setup
    python tradovate_position_monitor.py            # Run monitor
    python tradovate_position_monitor.py --demo     # Demo mode
"""

import asyncio
import aiohttp
from aiohttp import web
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque
from enum import Enum
import websockets

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class AlertType(Enum):
    """TradingView alert types"""
    STOP_OUT = "stop_out"
    BREAKEVEN = "breakeven"
    TIMEOUT = "timeout"
    TAKE_PROFIT = "take_profit"


class PositionSide(Enum):
    """Position direction"""
    LONG = "long"
    SHORT = "short"


@dataclass
class MonitorConfig:
    """Configuration for position monitoring"""
    # EMA settings
    ema_length: int = 20
    stop_offset_ticks: int = 4  # Ticks beyond EMA for stop

    # R-based targets
    breakeven_r: float = 3.0    # Move stop to BE at 3R
    take_profit_r: float = 2.5  # Take profit at 2.5R

    # Contract specs (MES defaults)
    symbol: str = "MES"
    tick_size: float = 0.25
    tick_value: float = 1.25

    # Webhook server
    webhook_port: int = 5000
    webhook_path: str = "/webhook"

    # Tradovate API
    api_url: str = "https://api.tradovate.com/v1"
    demo_api_url: str = "https://demo.tradovateapi.com/v1"
    ws_url: str = "wss://md.tradovate.com/v1/websocket"
    demo_ws_url: str = "wss://md-demo.tradovate.com/v1/websocket"
    demo_mode: bool = True

    # Monitoring
    poll_interval_ms: int = 100  # Position check frequency
    ema_update_interval_ms: int = 1000  # EMA recalc frequency

    @property
    def active_api_url(self) -> str:
        return self.demo_api_url if self.demo_mode else self.api_url

    @property
    def active_ws_url(self) -> str:
        return self.demo_ws_url if self.demo_mode else self.ws_url


@dataclass
class TrackedPosition:
    """A position being monitored"""
    position_id: int
    contract_id: int
    symbol: str
    side: PositionSide
    quantity: int
    entry_price: float
    entry_time: datetime
    initial_stop: float  # Original stop loss price
    current_stop: float  # Current stop price
    initial_risk: float  # Entry - initial stop (in price)
    stop_order_id: Optional[int] = None
    breakeven_triggered: bool = False
    last_ema: Optional[float] = None

    @property
    def risk_ticks(self) -> float:
        """Risk in ticks"""
        return abs(self.entry_price - self.initial_stop) / 0.25  # Assuming tick_size 0.25

    def calculate_r_multiple(self, current_price: float) -> float:
        """Calculate current R-multiple (profit/initial risk)"""
        if self.initial_risk == 0:
            return 0

        if self.side == PositionSide.LONG:
            profit = current_price - self.entry_price
        else:
            profit = self.entry_price - current_price

        return profit / abs(self.initial_risk)

    def calculate_target_price(self, r_multiple: float) -> float:
        """Calculate price at given R-multiple"""
        target_move = abs(self.initial_risk) * r_multiple

        if self.side == PositionSide.LONG:
            return self.entry_price + target_move
        else:
            return self.entry_price - target_move


class EMACalculator:
    """Calculates Exponential Moving Average from price data"""

    def __init__(self, period: int = 20):
        self.period = period
        self.prices: deque = deque(maxlen=period * 2)
        self.current_ema: Optional[float] = None
        self.multiplier = 2 / (period + 1)

    def update(self, price: float) -> Optional[float]:
        """Update EMA with new price"""
        self.prices.append(price)

        if len(self.prices) < self.period:
            return None

        if self.current_ema is None:
            # Initialize with SMA
            self.current_ema = sum(list(self.prices)[-self.period:]) / self.period
        else:
            # EMA formula: EMA = (Price * multiplier) + (Previous EMA * (1 - multiplier))
            self.current_ema = (price * self.multiplier) + (self.current_ema * (1 - self.multiplier))

        return self.current_ema

    def get_ema(self) -> Optional[float]:
        """Get current EMA value"""
        return self.current_ema


class TradovatePositionClient:
    """Tradovate API client for position management"""

    def __init__(self, config: MonitorConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.access_token: Optional[str] = None
        self.account_id: Optional[int] = None
        self.contract_id: Optional[int] = None

    async def connect(self, username: str, password: str, app_id: str, app_version: str):
        """Connect to Tradovate API"""
        self.session = aiohttp.ClientSession()

        auth_url = f"{self.config.active_api_url}/auth/accesstokenrequest"
        auth_data = {
            "name": username,
            "password": password,
            "appId": app_id,
            "appVersion": app_version
        }

        async with self.session.post(auth_url, json=auth_data) as resp:
            if resp.status == 200:
                data = await resp.json()
                self.access_token = data.get("accessToken")
                self.account_id = data.get("accountId")
                logger.info(f"Connected to Tradovate ({'DEMO' if self.config.demo_mode else 'LIVE'})")
                logger.info(f"Account ID: {self.account_id}")
            else:
                raise Exception(f"Auth failed: {await resp.text()}")

        # Cache contract ID
        self.contract_id = await self.get_contract_id(self.config.symbol)
        logger.info(f"Monitoring {self.config.symbol} (contract ID: {self.contract_id})")

        # Connect WebSocket for market data
        await self.connect_websocket()

    async def connect_websocket(self):
        """Connect to market data WebSocket"""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        self.ws = await websockets.connect(
            self.config.active_ws_url,
            extra_headers=headers
        )

        # Subscribe to market data
        subscribe_msg = {
            "op": "subscribe",
            "args": {
                "symbols": [self.config.symbol],
                "fields": ["last", "bid", "ask"]
            }
        }
        await self.ws.send(json.dumps(subscribe_msg))
        logger.info(f"Subscribed to {self.config.symbol} market data")

    async def get_market_price(self) -> Optional[float]:
        """Get current market price from WebSocket"""
        try:
            message = await asyncio.wait_for(self.ws.recv(), timeout=0.1)
            data = json.loads(message)
            if "data" in data:
                return data["data"].get("last")
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.error(f"Market data error: {e}")
        return None

    async def get_contract_id(self, symbol: str) -> int:
        """Get contract ID for symbol"""
        url = f"{self.config.active_api_url}/contract/find"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"name": symbol}

        async with self.session.get(url, params=params, headers=headers) as resp:
            if resp.status == 200:
                contracts = await resp.json()
                if contracts:
                    return contracts[0]["id"]
        return 0

    async def get_positions(self) -> List[Dict]:
        """Get all open positions"""
        url = f"{self.config.active_api_url}/position/list"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"accountId": self.account_id}

        async with self.session.get(url, params=params, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
        return []

    async def get_orders(self) -> List[Dict]:
        """Get all open orders"""
        url = f"{self.config.active_api_url}/order/list"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"accountId": self.account_id}

        async with self.session.get(url, params=params, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
        return []

    async def modify_stop_order(self, order_id: int, new_stop_price: float) -> bool:
        """Modify an existing stop order"""
        url = f"{self.config.active_api_url}/order/modifyorder"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        data = {
            "orderId": order_id,
            "stopPrice": new_stop_price
        }

        async with self.session.post(url, json=data, headers=headers) as resp:
            if resp.status == 200:
                logger.info(f"Stop modified to {new_stop_price:.2f}")
                return True
            else:
                logger.error(f"Failed to modify stop: {await resp.text()}")
        return False

    async def place_stop_order(self, side: str, quantity: int, stop_price: float) -> Optional[int]:
        """Place a stop order"""
        url = f"{self.config.active_api_url}/order/placeorder"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        data = {
            "accountId": self.account_id,
            "contractId": self.contract_id,
            "action": side,
            "orderQty": quantity,
            "orderType": "Stop",
            "stopPrice": stop_price,
            "isAutomated": True
        }

        async with self.session.post(url, json=data, headers=headers) as resp:
            if resp.status == 200:
                order = await resp.json()
                order_id = order.get("orderId")
                logger.info(f"Stop order placed: {side} {quantity} @ {stop_price:.2f}")
                return order_id
        return None

    async def place_market_order(self, side: str, quantity: int) -> Optional[int]:
        """Place a market order (for closing positions)"""
        url = f"{self.config.active_api_url}/order/placeorder"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        data = {
            "accountId": self.account_id,
            "contractId": self.contract_id,
            "action": side,
            "orderQty": quantity,
            "orderType": "Market",
            "isAutomated": True
        }

        async with self.session.post(url, json=data, headers=headers) as resp:
            if resp.status == 200:
                order = await resp.json()
                logger.info(f"Market order placed: {side} {quantity}")
                return order.get("orderId")
        return None

    async def cancel_order(self, order_id: int) -> bool:
        """Cancel an order"""
        url = f"{self.config.active_api_url}/order/cancelorder"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        async with self.session.post(url, json={"orderId": order_id}, headers=headers) as resp:
            return resp.status == 200

    async def close(self):
        """Clean up connections"""
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()


class PositionMonitor:
    """
    Monitors open positions and manages stops based on:
    - EMA(20) + offset for stop loss
    - R-based breakeven and take profit
    """

    def __init__(self, client: TradovatePositionClient, config: MonitorConfig):
        self.client = client
        self.config = config
        self.tracked_positions: Dict[int, TrackedPosition] = {}
        self.ema_calculator = EMACalculator(config.ema_length)
        self.running = False
        self.last_price: Optional[float] = None
        self.pending_alerts: asyncio.Queue = asyncio.Queue()

    async def process_alert(self, alert_type: AlertType, data: Dict):
        """Process incoming TradingView alert"""
        logger.info(f"Processing alert: {alert_type.value} - {data}")

        if alert_type == AlertType.STOP_OUT:
            await self._handle_stop_out(data)
        elif alert_type == AlertType.BREAKEVEN:
            await self._handle_breakeven_trigger(data)
        elif alert_type == AlertType.TIMEOUT:
            await self._handle_timeout(data)
        elif alert_type == AlertType.TAKE_PROFIT:
            await self._handle_take_profit(data)

    async def _handle_stop_out(self, data: Dict):
        """Handle stop out alert - close position immediately"""
        logger.warning("STOP OUT alert received - closing position")
        for pos_id, pos in list(self.tracked_positions.items()):
            close_side = "Sell" if pos.side == PositionSide.LONG else "Buy"
            await self.client.place_market_order(close_side, pos.quantity)
            del self.tracked_positions[pos_id]

    async def _handle_breakeven_trigger(self, data: Dict):
        """Handle breakeven trigger from TradingView"""
        logger.info("Breakeven trigger received from TradingView")
        for pos_id, pos in self.tracked_positions.items():
            if not pos.breakeven_triggered:
                await self._move_to_breakeven(pos)

    async def _handle_timeout(self, data: Dict):
        """Handle timeout alert - close position at market"""
        logger.warning("TIMEOUT alert - closing position at market")
        for pos_id, pos in list(self.tracked_positions.items()):
            close_side = "Sell" if pos.side == PositionSide.LONG else "Buy"
            await self.client.place_market_order(close_side, pos.quantity)
            del self.tracked_positions[pos_id]

    async def _handle_take_profit(self, data: Dict):
        """Handle take profit alert"""
        logger.info("TAKE PROFIT alert - closing position")
        for pos_id, pos in list(self.tracked_positions.items()):
            close_side = "Sell" if pos.side == PositionSide.LONG else "Buy"
            await self.client.place_market_order(close_side, pos.quantity)
            del self.tracked_positions[pos_id]

    async def _move_to_breakeven(self, position: TrackedPosition):
        """Move stop loss to breakeven"""
        if position.stop_order_id:
            # Add small buffer (1 tick) to ensure profit
            buffer = self.config.tick_size
            if position.side == PositionSide.LONG:
                be_price = position.entry_price + buffer
            else:
                be_price = position.entry_price - buffer

            success = await self.client.modify_stop_order(position.stop_order_id, be_price)
            if success:
                position.breakeven_triggered = True
                position.current_stop = be_price
                logger.info(f"Moved to breakeven @ {be_price:.2f}")

    def calculate_ema_stop(self, ema: float, side: PositionSide) -> float:
        """Calculate stop price based on EMA + offset"""
        offset = self.config.stop_offset_ticks * self.config.tick_size

        if side == PositionSide.LONG:
            # For long, stop is below EMA
            return ema - offset
        else:
            # For short, stop is above EMA
            return ema + offset

    async def scan_for_new_positions(self):
        """Detect manually-entered positions to start tracking"""
        positions = await self.client.get_positions()

        for pos in positions:
            pos_id = pos.get("id")
            if pos_id not in self.tracked_positions:
                # New position detected
                net_pos = pos.get("netPos", 0)
                if net_pos == 0:
                    continue

                avg_price = pos.get("netPrice", 0)
                side = PositionSide.LONG if net_pos > 0 else PositionSide.SHORT

                # Calculate initial stop using current EMA
                ema = self.ema_calculator.get_ema()
                if ema:
                    initial_stop = self.calculate_ema_stop(ema, side)
                else:
                    # Fallback: use 10 tick stop
                    fallback_ticks = 10
                    if side == PositionSide.LONG:
                        initial_stop = avg_price - (fallback_ticks * self.config.tick_size)
                    else:
                        initial_stop = avg_price + (fallback_ticks * self.config.tick_size)

                # Calculate initial risk
                initial_risk = abs(avg_price - initial_stop)

                tracked = TrackedPosition(
                    position_id=pos_id,
                    contract_id=pos.get("contractId"),
                    symbol=self.config.symbol,
                    side=side,
                    quantity=abs(net_pos),
                    entry_price=avg_price,
                    entry_time=datetime.now(),
                    initial_stop=initial_stop,
                    current_stop=initial_stop,
                    initial_risk=initial_risk,
                    last_ema=ema
                )

                # Place stop order
                stop_side = "Sell" if side == PositionSide.LONG else "Buy"
                stop_order_id = await self.client.place_stop_order(
                    stop_side, abs(net_pos), initial_stop
                )
                tracked.stop_order_id = stop_order_id

                self.tracked_positions[pos_id] = tracked

                logger.info(f"Now tracking: {side.value.upper()} {abs(net_pos)} @ {avg_price:.2f}")
                logger.info(f"Initial stop: {initial_stop:.2f} | Risk: {initial_risk:.2f} ({initial_risk/self.config.tick_size:.0f} ticks)")
                logger.info(f"BE target: {tracked.calculate_target_price(self.config.breakeven_r):.2f} ({self.config.breakeven_r}R)")
                logger.info(f"TP target: {tracked.calculate_target_price(self.config.take_profit_r):.2f} ({self.config.take_profit_r}R)")

    async def update_stops(self, current_price: float):
        """Update stop losses based on EMA and R-targets"""
        ema = self.ema_calculator.get_ema()
        if not ema:
            return

        for pos_id, pos in list(self.tracked_positions.items()):
            # Calculate current R-multiple
            r_mult = pos.calculate_r_multiple(current_price)

            # Check for breakeven trigger (3R)
            if not pos.breakeven_triggered and r_mult >= self.config.breakeven_r:
                logger.info(f"R-multiple reached {r_mult:.1f}R - triggering breakeven")
                await self._move_to_breakeven(pos)

            # Check for take profit (2.5R)
            if r_mult >= self.config.take_profit_r:
                logger.info(f"Take profit target reached ({r_mult:.1f}R) - closing position")
                close_side = "Sell" if pos.side == PositionSide.LONG else "Buy"
                await self.client.place_market_order(close_side, pos.quantity)
                del self.tracked_positions[pos_id]
                continue

            # Update EMA-based stop (only if not at breakeven and stop would improve)
            if not pos.breakeven_triggered:
                new_stop = self.calculate_ema_stop(ema, pos.side)

                # Only trail stop in favorable direction
                should_update = False
                if pos.side == PositionSide.LONG:
                    # For long, only raise stop
                    if new_stop > pos.current_stop:
                        should_update = True
                else:
                    # For short, only lower stop
                    if new_stop < pos.current_stop:
                        should_update = True

                if should_update and pos.stop_order_id:
                    success = await self.client.modify_stop_order(pos.stop_order_id, new_stop)
                    if success:
                        pos.current_stop = new_stop
                        pos.last_ema = ema

    async def check_position_closed(self):
        """Remove positions that are no longer open"""
        current_positions = await self.client.get_positions()
        current_ids = {p.get("id") for p in current_positions if p.get("netPos", 0) != 0}

        closed = []
        for pos_id in self.tracked_positions:
            if pos_id not in current_ids:
                closed.append(pos_id)

        for pos_id in closed:
            pos = self.tracked_positions[pos_id]
            logger.info(f"Position closed: {pos.side.value} {pos.quantity} @ {pos.entry_price:.2f}")
            del self.tracked_positions[pos_id]

    async def run(self):
        """Main monitoring loop"""
        self.running = True
        logger.info("Position monitor started")
        logger.info(f"Config: EMA({self.config.ema_length}) + {self.config.stop_offset_ticks} tick offset")
        logger.info(f"BE @ {self.config.breakeven_r}R | TP @ {self.config.take_profit_r}R")

        last_ema_update = 0
        last_position_scan = 0

        while self.running:
            try:
                current_time = time.time() * 1000  # ms

                # Get market price
                price = await self.client.get_market_price()
                if price:
                    self.last_price = price

                    # Update EMA periodically
                    if current_time - last_ema_update >= self.config.ema_update_interval_ms:
                        self.ema_calculator.update(price)
                        last_ema_update = current_time

                # Scan for new positions every second
                if current_time - last_position_scan >= 1000:
                    await self.scan_for_new_positions()
                    await self.check_position_closed()
                    last_position_scan = current_time

                # Update stops if we have positions and price
                if self.tracked_positions and self.last_price:
                    await self.update_stops(self.last_price)

                # Process any pending alerts
                try:
                    alert = self.pending_alerts.get_nowait()
                    await self.process_alert(alert["type"], alert["data"])
                except asyncio.QueueEmpty:
                    pass

                await asyncio.sleep(self.config.poll_interval_ms / 1000)

            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(1)

    def stop(self):
        """Stop the monitor"""
        self.running = False


class WebhookServer:
    """HTTP server to receive TradingView webhook alerts"""

    def __init__(self, monitor: PositionMonitor, config: MonitorConfig):
        self.monitor = monitor
        self.config = config
        self.app = web.Application()
        self.app.router.add_post(config.webhook_path, self.handle_webhook)
        self.app.router.add_get("/health", self.health_check)
        self.runner: Optional[web.AppRunner] = None

    async def handle_webhook(self, request: web.Request) -> web.Response:
        """Handle incoming TradingView webhook"""
        try:
            data = await request.json()
            logger.info(f"Webhook received: {data}")

            # Parse alert type from payload
            alert_type_str = data.get("alert_type", "").lower()

            alert_type = None
            if "stop" in alert_type_str:
                alert_type = AlertType.STOP_OUT
            elif "breakeven" in alert_type_str or "be" in alert_type_str:
                alert_type = AlertType.BREAKEVEN
            elif "timeout" in alert_type_str or "time" in alert_type_str:
                alert_type = AlertType.TIMEOUT
            elif "profit" in alert_type_str or "tp" in alert_type_str:
                alert_type = AlertType.TAKE_PROFIT

            if alert_type:
                await self.monitor.pending_alerts.put({
                    "type": alert_type,
                    "data": data
                })
                return web.json_response({"status": "ok", "alert": alert_type.value})

            return web.json_response({"status": "ignored", "reason": "unknown alert type"})

        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=400)

    async def health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint"""
        return web.json_response({
            "status": "healthy",
            "positions": len(self.monitor.tracked_positions),
            "last_price": self.monitor.last_price,
            "ema": self.monitor.ema_calculator.get_ema()
        })

    async def start(self):
        """Start the webhook server"""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", self.config.webhook_port)
        await site.start()
        logger.info(f"Webhook server listening on port {self.config.webhook_port}")
        logger.info(f"Endpoint: POST http://localhost:{self.config.webhook_port}{self.config.webhook_path}")

    async def stop(self):
        """Stop the webhook server"""
        if self.runner:
            await self.runner.cleanup()


class PositionMonitorApp:
    """Main application for position monitoring"""

    def __init__(self, config: MonitorConfig):
        self.config = config
        self.client: Optional[TradovatePositionClient] = None
        self.monitor: Optional[PositionMonitor] = None
        self.webhook_server: Optional[WebhookServer] = None
        self.running = False

    async def initialize(self, username: str, password: str,
                         app_id: str, app_version: str) -> bool:
        """Initialize the application"""
        try:
            self.client = TradovatePositionClient(self.config)
            await self.client.connect(username, password, app_id, app_version)

            self.monitor = PositionMonitor(self.client, self.config)
            self.webhook_server = WebhookServer(self.monitor, self.config)

            return True
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False

    async def run(self):
        """Run the position monitor"""
        self.running = True

        # Start webhook server
        await self.webhook_server.start()

        # Print status
        print("\n" + "=" * 60)
        print("  TRADOVATE POSITION MONITOR")
        print("=" * 60)
        print(f"\n  Mode: {'DEMO' if self.config.demo_mode else 'LIVE'}")
        print(f"  Symbol: {self.config.symbol}")
        print(f"  EMA Period: {self.config.ema_length}")
        print(f"  Stop Offset: {self.config.stop_offset_ticks} ticks")
        print(f"  Breakeven: {self.config.breakeven_r}R")
        print(f"  Take Profit: {self.config.take_profit_r}R")
        print(f"\n  Webhook: http://localhost:{self.config.webhook_port}{self.config.webhook_path}")
        print("\n  Waiting for positions...")
        print("=" * 60 + "\n")

        # Run monitor
        try:
            await self.monitor.run()
        except asyncio.CancelledError:
            pass

    async def shutdown(self):
        """Shutdown the application"""
        logger.info("Shutting down...")
        self.running = False

        if self.monitor:
            self.monitor.stop()

        if self.webhook_server:
            await self.webhook_server.stop()

        if self.client:
            await self.client.close()

        logger.info("Shutdown complete")


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Tradovate Position Monitor")
    parser.add_argument("--demo", action="store_true", default=True,
                        help="Use demo environment (default)")
    parser.add_argument("--live", action="store_true",
                        help="Use live environment")
    parser.add_argument("--symbol", type=str, default="MES",
                        help="Contract symbol (default: MES)")
    parser.add_argument("--ema", type=int, default=20,
                        help="EMA period (default: 20)")
    parser.add_argument("--stop-offset", type=int, default=4,
                        help="Stop offset in ticks (default: 4)")
    parser.add_argument("--be-r", type=float, default=3.0,
                        help="Breakeven R-multiple (default: 3.0)")
    parser.add_argument("--tp-r", type=float, default=2.5,
                        help="Take profit R-multiple (default: 2.5)")
    parser.add_argument("--port", type=int, default=5000,
                        help="Webhook port (default: 5000)")
    parser.add_argument("--setup", action="store_true",
                        help="Run interactive setup")

    args = parser.parse_args()

    if args.setup:
        from config_manager import setup_credentials_interactive
        setup_credentials_interactive()
        return

    # Load credentials
    from config_manager import ConfigManager
    config_mgr = ConfigManager()
    credentials = config_mgr.load_credentials()

    if not credentials:
        print("No credentials found. Run with --setup first.")
        return

    # Build config
    config = MonitorConfig(
        symbol=args.symbol,
        ema_length=args.ema,
        stop_offset_ticks=args.stop_offset,
        breakeven_r=args.be_r,
        take_profit_r=args.tp_r,
        webhook_port=args.port,
        demo_mode=not args.live
    )

    # Live trading confirmation
    if args.live:
        print("\n" + "=" * 60)
        print("  WARNING: LIVE TRADING MODE")
        print("=" * 60)
        print("\n  This will manage REAL positions with REAL money.")
        confirm = input("\n  Type 'LIVE' to continue: ")
        if confirm != "LIVE":
            print("  Cancelled.")
            return

    # Run app
    app = PositionMonitorApp(config)

    if not await app.initialize(
        credentials.username,
        credentials.password,
        credentials.app_id,
        credentials.app_version
    ):
        return

    try:
        await app.run()
    except KeyboardInterrupt:
        pass
    finally:
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
