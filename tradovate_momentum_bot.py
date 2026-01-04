#!/usr/bin/env python3
"""
High-Performance Momentum Trading Bot for Tradovate Micro Futures
Adapted from Cash-profit_1_1.mq4 strategy

Key Features:
- Ultra-low latency execution using asyncio and websockets
- Real-time price monitoring with sub-second reaction times
- Momentum-based entry signals (rapid price movements)
- Risk management with stop loss, take profit, and trailing stops
- Optimized for micro futures (MES, MNQ, MYM, M2K)
"""

import asyncio
import aiohttp
import json
import time
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import deque
import websockets
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class OrderSide(Enum):
    BUY = "Buy"
    SELL = "Sell"

class OrderType(Enum):
    MARKET = "Market"
    LIMIT = "Limit"
    STOP = "Stop"
    STOP_LIMIT = "StopLimit"

@dataclass
class TradingConfig:
    """Configuration parameters for the trading strategy"""
    # Strategy parameters (from MQL4)
    time_window: int = 14  # seconds (cSeconds)
    min_price_movement: int = 7  # points/ticks (MinPriceShot)
    max_positions: int = 1  # (MaxOrdersCount)
    risk_percent: float = 120.0  # (RiskPercent)
    take_profit: int = 22  # points/ticks (TakeProfit)
    stop_loss: int = 10  # points/ticks (StopLoss)
    trailing_stop: int = 5  # points/ticks (TrailingStop)
    slippage: int = 3  # ticks (Slippage)
    
    # Micro futures specific
    symbol: str = "MESZ24"  # E-mini S&P 500 Micro Dec 2024
    tick_size: float = 0.25  # MES tick size
    tick_value: float = 1.25  # MES tick value ($1.25 per tick)
    contract_multiplier: int = 5  # Micro = 1/10 of E-mini
    
    # Tradovate API
    api_url: str = "https://api.tradovate.com/v1"
    ws_url: str = "wss://md.tradovate.com/v1/websocket"
    demo_mode: bool = True  # Use demo environment initially

@dataclass
class PriceSnapshot:
    """Stores a price point with timestamp"""
    timestamp: float
    price: float
    bid: float
    ask: float
    volume: int = 0

class TradovateClient:
    """High-performance Tradovate API client with WebSocket support"""
    
    def __init__(self, config: TradingConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.access_token: Optional[str] = None
        self.account_id: Optional[int] = None
        self.positions: Dict = {}
        self.orders: Dict = {}
        self.market_data_queue = asyncio.Queue(maxsize=1000)
        
    async def connect(self, username: str, password: str, app_id: str, app_version: str):
        """Initialize connection to Tradovate"""
        self.session = aiohttp.ClientSession()
        
        # Get access token
        auth_url = f"{self.config.api_url}/auth/accesstokenrequest"
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
                logger.info(f"Connected to Tradovate. Account ID: {self.account_id}")
            else:
                raise Exception(f"Authentication failed: {await resp.text()}")
        
        # Connect to WebSocket for real-time data
        await self.connect_websocket()
        
    async def connect_websocket(self):
        """Establish WebSocket connection for market data"""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        self.ws = await websockets.connect(self.config.ws_url, extra_headers=headers)
        
        # Subscribe to market data
        subscribe_msg = {
            "op": "subscribe",
            "args": {
                "symbols": [self.config.symbol],
                "fields": ["last", "bid", "ask", "volume"]
            }
        }
        await self.ws.send(json.dumps(subscribe_msg))
        logger.info(f"Subscribed to market data for {self.config.symbol}")
        
    async def get_market_data(self) -> Optional[PriceSnapshot]:
        """Get real-time market data from WebSocket"""
        try:
            message = await asyncio.wait_for(self.ws.recv(), timeout=0.1)
            data = json.loads(message)
            
            if "data" in data:
                market_data = data["data"]
                return PriceSnapshot(
                    timestamp=time.time(),
                    price=market_data.get("last", 0),
                    bid=market_data.get("bid", 0),
                    ask=market_data.get("ask", 0),
                    volume=market_data.get("volume", 0)
                )
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.error(f"Error getting market data: {e}")
            return None
    
    async def place_order(self, side: OrderSide, quantity: int = 1, 
                         order_type: OrderType = OrderType.MARKET,
                         limit_price: Optional[float] = None,
                         stop_price: Optional[float] = None) -> Dict:
        """Place an order with ultra-low latency"""
        order_data = {
            "accountId": self.account_id,
            "contractId": await self.get_contract_id(self.config.symbol),
            "action": side.value,
            "orderQty": quantity,
            "orderType": order_type.value,
            "isAutomated": True
        }
        
        if limit_price:
            order_data["price"] = limit_price
        if stop_price:
            order_data["stopPrice"] = stop_price
            
        url = f"{self.config.api_url}/order/placeorder"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        start_time = time.perf_counter()
        async with self.session.post(url, json=order_data, headers=headers) as resp:
            latency = (time.perf_counter() - start_time) * 1000
            
            if resp.status == 200:
                order = await resp.json()
                logger.info(f"Order placed in {latency:.2f}ms: {order}")
                return order
            else:
                logger.error(f"Order failed: {await resp.text()}")
                return {}
    
    async def get_contract_id(self, symbol: str) -> int:
        """Get contract ID for symbol"""
        url = f"{self.config.api_url}/contract/find"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"name": symbol}
        
        async with self.session.get(url, params=params, headers=headers) as resp:
            if resp.status == 200:
                contracts = await resp.json()
                if contracts:
                    return contracts[0]["id"]
        return 0
    
    async def modify_order(self, order_id: int, stop_price: Optional[float] = None,
                          limit_price: Optional[float] = None) -> bool:
        """Modify existing order (for trailing stops)"""
        url = f"{self.config.api_url}/order/modifyorder"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        mod_data = {"orderId": order_id}
        if stop_price:
            mod_data["stopPrice"] = stop_price
        if limit_price:
            mod_data["price"] = limit_price
            
        async with self.session.post(url, json=mod_data, headers=headers) as resp:
            if resp.status == 200:
                logger.info(f"Order {order_id} modified successfully")
                return True
            return False
    
    async def get_positions(self) -> List[Dict]:
        """Get current positions"""
        url = f"{self.config.api_url}/position/list"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"accountId": self.account_id}
        
        async with self.session.get(url, params=params, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
        return []
    
    async def close(self):
        """Clean up connections"""
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()

class MomentumTradingStrategy:
    """
    High-performance momentum trading strategy
    Optimized for micro futures with sub-second execution
    """
    
    def __init__(self, client: TradovateClient, config: TradingConfig):
        self.client = client
        self.config = config
        self.price_history = deque(maxlen=1000)  # Rolling window of prices
        self.last_signal_time = 0
        self.last_signal_price = 0
        self.position_count = 0
        self.current_position = None
        self.trailing_stop_price = None
        
    def calculate_position_size(self, account_balance: float) -> int:
        """Calculate position size based on risk management"""
        risk_amount = account_balance * (self.config.risk_percent / 100.0)
        max_loss_per_contract = self.config.stop_loss * self.config.tick_value
        contracts = int(risk_amount / max_loss_per_contract / 1000.0)
        return max(1, contracts)
    
    def detect_momentum_signal(self, current: PriceSnapshot) -> Optional[OrderSide]:
        """
        Detect momentum trading signal based on rapid price movement
        Returns BUY, SELL, or None
        """
        current_time = current.timestamp
        current_price = current.price
        
        # Check if we have a reference point
        if self.last_signal_price == 0:
            self.last_signal_price = current_price
            self.last_signal_time = current_time
            return None
        
        # Calculate time and price differences
        time_diff = current_time - self.last_signal_time
        price_diff_ticks = (current_price - self.last_signal_price) / self.config.tick_size
        
        # Check if within time window
        if time_diff <= self.config.time_window:
            # Check for significant price movement
            if abs(price_diff_ticks) >= self.config.min_price_movement:
                # Check position limits
                if self.position_count < self.config.max_positions:
                    # Update reference point
                    self.last_signal_price = current_price
                    self.last_signal_time = current_time
                    
                    # Return signal based on direction
                    if price_diff_ticks > 0:
                        logger.info(f"BUY Signal: {abs(price_diff_ticks):.0f} ticks UP in {time_diff:.1f}s")
                        return OrderSide.BUY
                    else:
                        logger.info(f"SELL Signal: {abs(price_diff_ticks):.0f} ticks DOWN in {time_diff:.1f}s")
                        return OrderSide.SELL
        
        # Update reference point if time window expired
        if time_diff >= self.config.time_window:
            self.last_signal_price = current_price
            self.last_signal_time = current_time
            
        return None
    
    async def execute_signal(self, signal: OrderSide, current_price: float):
        """Execute trading signal with proper risk management"""
        
        # Calculate order parameters
        if signal == OrderSide.BUY:
            stop_loss_price = current_price - (self.config.stop_loss * self.config.tick_size)
            take_profit_price = current_price + (self.config.take_profit * self.config.tick_size)
        else:  # SELL
            stop_loss_price = current_price + (self.config.stop_loss * self.config.tick_size)
            take_profit_price = current_price - (self.config.take_profit * self.config.tick_size)
        
        # Place market order with attached stop loss and take profit
        order = await self.client.place_order(
            side=signal,
            quantity=1,  # Start with 1 micro contract
            order_type=OrderType.MARKET
        )
        
        if order:
            self.position_count += 1
            self.current_position = {
                "order_id": order.get("orderId"),
                "side": signal,
                "entry_price": current_price,
                "stop_loss": stop_loss_price,
                "take_profit": take_profit_price,
                "timestamp": time.time()
            }
            
            # Place stop loss order
            await self.client.place_order(
                side=OrderSide.SELL if signal == OrderSide.BUY else OrderSide.BUY,
                quantity=1,
                order_type=OrderType.STOP,
                stop_price=stop_loss_price
            )
            
            # Place take profit order
            await self.client.place_order(
                side=OrderSide.SELL if signal == OrderSide.BUY else OrderSide.BUY,
                quantity=1,
                order_type=OrderType.LIMIT,
                limit_price=take_profit_price
            )
            
            self.trailing_stop_price = stop_loss_price
            logger.info(f"Position opened: {signal.value} at {current_price:.2f}")
    
    async def manage_trailing_stop(self, current_price: float):
        """Update trailing stop for open positions"""
        if not self.current_position:
            return
            
        position = self.current_position
        trailing_distance = self.config.trailing_stop * self.config.tick_size
        
        if position["side"] == OrderSide.BUY:
            # For long position
            new_stop = current_price - trailing_distance
            if new_stop > self.trailing_stop_price and new_stop > position["entry_price"]:
                # Move stop up
                success = await self.client.modify_order(
                    position["order_id"],
                    stop_price=new_stop
                )
                if success:
                    self.trailing_stop_price = new_stop
                    logger.info(f"Trailing stop updated to {new_stop:.2f}")
                    
        else:  # SELL position
            # For short position
            new_stop = current_price + trailing_distance
            if new_stop < self.trailing_stop_price and new_stop < position["entry_price"]:
                # Move stop down
                success = await self.client.modify_order(
                    position["order_id"],
                    stop_price=new_stop
                )
                if success:
                    self.trailing_stop_price = new_stop
                    logger.info(f"Trailing stop updated to {new_stop:.2f}")
    
    async def run(self):
        """Main trading loop with high-frequency monitoring"""
        logger.info("Starting momentum trading strategy...")
        
        while True:
            try:
                # Get real-time market data
                snapshot = await self.client.get_market_data()
                
                if snapshot:
                    # Store price history
                    self.price_history.append(snapshot)
                    
                    # Check for trading signals
                    signal = self.detect_momentum_signal(snapshot)
                    
                    if signal:
                        await self.execute_signal(signal, snapshot.price)
                    
                    # Manage trailing stops
                    if self.current_position:
                        await self.manage_trailing_stop(snapshot.price)
                    
                    # Check positions
                    positions = await self.client.get_positions()
                    self.position_count = len(positions)
                    
                    # Update position status
                    if self.position_count == 0:
                        self.current_position = None
                        self.trailing_stop_price = None
                
                # Ultra-low latency loop (10ms)
                await asyncio.sleep(0.01)
                
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                await asyncio.sleep(1)

async def main():
    """Main entry point"""
    
    # Configuration
    config = TradingConfig(
        symbol="MESZ24",  # E-mini S&P 500 Micro
        time_window=14,
        min_price_movement=7,
        take_profit=22,
        stop_loss=10,
        trailing_stop=5
    )
    
    # Initialize client
    client = TradovateClient(config)
    
    # Connect to Tradovate (you'll need to provide credentials)
    # Note: Store these securely, never hardcode in production!
    username = "YOUR_USERNAME"
    password = "YOUR_PASSWORD"
    app_id = "YOUR_APP_ID"
    app_version = "1.0"
    
    try:
        await client.connect(username, password, app_id, app_version)
        
        # Initialize and run strategy
        strategy = MomentumTradingStrategy(client, config)
        await strategy.run()
        
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
