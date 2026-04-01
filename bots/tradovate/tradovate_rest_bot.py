#!/usr/bin/env python3
"""
Tradovate Momentum Bot - REST API Version
Simplified version using only REST endpoints (no WebSocket)
"""

import requests
import time
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from collections import deque

# Load environment
load_dotenv()

class TradovateRestBot:
    """Tradovate trading bot using REST API only"""
    
    def __init__(self):
        # Load credentials
        self.username = os.getenv('TRADOVATE_DEMO_USERNAME')
        self.password = os.getenv('TRADOVATE_DEMO_PASSWORD')
        self.app_id = os.getenv('TRADOVATE_DEMO_APP_ID')
        self.app_version = os.getenv('TRADOVATE_DEMO_APP_VERSION')
        self.device_id = os.getenv('TRADOVATE_DEMO_DEVICE_ID')
        self.cid = os.getenv('TRADOVATE_DEMO_CID')
        self.sec = os.getenv('TRADOVATE_DEMO_SEC')
        self.api_url = os.getenv('TRADOVATE_DEMO_API_URL', 'https://demo.tradovateapi.com/v1')
        
        # Authentication
        self.access_token = None
        self.account_id = None
        self.contract_id = None
        
        # Strategy parameters
        self.symbol = "MES"
        self.time_window = 14  # seconds
        self.min_price_movement = 7  # ticks
        self.take_profit_ticks = 25
        self.stop_loss_ticks = 12
        self.tick_size = 0.25
        self.tick_value = 1.25
        
        # State
        self.price_history = deque(maxlen=100)
        self.position = None
        self.active_order = None
        
        print(f"✅ Bot initialized")
        print(f"Symbol: {self.symbol}")
        print(f"Time window: {self.time_window}s")
        print(f"Min move: {self.min_price_movement} ticks")
        print(f"TP: {self.take_profit_ticks} ticks (${self.take_profit_ticks * self.tick_value:.2f})")
        print(f"SL: {self.stop_loss_ticks} ticks (${self.stop_loss_ticks * self.tick_value:.2f})")
    
    def authenticate(self):
        """Get access token"""
        print("\n🔐 Authenticating...")
        
        auth_payload = {
            "name": self.username,
            "password": self.password,
            "appId": self.app_id,
            "appVersion": self.app_version,
            "deviceId": self.device_id,
            "cid": self.cid,
            "sec": self.sec
        }
        
        response = requests.post(
            f"{self.api_url}/auth/accesstokenrequest",
            json=auth_payload,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            self.access_token = data['accessToken']
            print(f"✅ Authenticated (User ID: {data['userId']})")
            return True
        else:
            print(f"❌ Auth failed: {response.text}")
            return False
    
    def get_account(self):
        """Get account details"""
        response = requests.get(
            f"{self.api_url}/account/list",
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=10
        )
        
        if response.status_code == 200:
            accounts = response.json()
            if accounts:
                self.account_id = accounts[0]['id']
                print(f"✅ Account ID: {self.account_id}")
                return True
        
        print(f"❌ Failed to get account")
        return False
    
    def get_contract_id(self):
        """Get contract ID for symbol"""
        response = requests.get(
            f"{self.api_url}/contract/find",
            headers={"Authorization": f"Bearer {self.access_token}"},
            params={"name": self.symbol},
            timeout=10
        )
        
        if response.status_code == 200:
            contracts = response.json()
            if contracts:
                # Get the front month contract
                active_contracts = [c for c in contracts if not c.get('expirationDate')]
                if active_contracts:
                    self.contract_id = active_contracts[0]['id']
                elif contracts:
                    self.contract_id = contracts[0]['id']
                
                print(f"✅ Contract ID: {self.contract_id} ({self.symbol})")
                return True
        
        print(f"⚠️  Using symbol name directly: {self.symbol}")
        return True
    
    def get_quote(self):
        """Get current market quote"""
        try:
            response = requests.get(
                f"{self.api_url}/md/getChart",
                headers={"Authorization": f"Bearer {self.access_token}"},
                params={
                    "symbol": self.symbol,
                    "chartDescription": {
                        "underlyingType": "MinuteBar",
                        "elementSize": 1,
                        "elementSizeUnit": "UnderlyingUnits"
                    },
                    "timeRange": {
                        "asMuchAsElements": 1
                    }
                },
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if 'bars' in data and data['bars']:
                    bar = data['bars'][-1]
                    return {
                        'price': bar['close'],
                        'timestamp': time.time()
                    }
        except Exception as e:
            print(f"Quote error: {e}")
        
        return None
    
    def check_position(self):
        """Check current position"""
        try:
            response = requests.get(
                f"{self.api_url}/position/list",
                headers={"Authorization": f"Bearer {self.access_token}"},
                params={"accountId": self.account_id},
                timeout=5
            )
            
            if response.status_code == 200:
                positions = response.json()
                for pos in positions:
                    if pos.get('contractId') == self.contract_id:
                        return pos
        except Exception as e:
            print(f"Position check error: {e}")
        
        return None
    
    def place_order(self, action, quantity=1):
        """Place market order"""
        print(f"\n📤 Placing {action} order for {quantity} {self.symbol}")
        
        order_payload = {
            "accountId": self.account_id,
            "action": action,  # "Buy" or "Sell"
            "symbol": self.symbol,
            "orderQty": quantity,
            "orderType": "Market",
            "isAutomated": True
        }
        
        try:
            response = requests.post(
                f"{self.api_url}/order/placeorder",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json=order_payload,
                timeout=10
            )
            
            if response.status_code == 200:
                order = response.json()
                print(f"✅ Order placed: {order.get('orderId')}")
                return order
            else:
                print(f"❌ Order failed: {response.text}")
        except Exception as e:
            print(f"❌ Order error: {e}")
        
        return None
    
    def check_momentum_signal(self):
        """Check for momentum entry signal"""
        if len(self.price_history) < 2:
            return None
        
        # Get prices in time window
        current_time = time.time()
        window_prices = [
            p for p in self.price_history 
            if current_time - p['timestamp'] <= self.time_window
        ]
        
        if len(window_prices) < 2:
            return None
        
        # Calculate price movement
        start_price = window_prices[0]['price']
        end_price = window_prices[-1]['price']
        price_change_ticks = abs(end_price - start_price) / self.tick_size
        
        # Check for momentum
        if price_change_ticks >= self.min_price_movement:
            direction = "Buy" if end_price > start_price else "Sell"
            print(f"\n🚀 MOMENTUM SIGNAL!")
            print(f"Direction: {direction}")
            print(f"Move: {price_change_ticks:.1f} ticks in {self.time_window}s")
            return direction
        
        return None
    
    def run(self):
        """Main trading loop"""
        print("\n" + "=" * 60)
        print("🚀 Starting Tradovate Momentum Bot")
        print("=" * 60)
        
        # Authenticate
        if not self.authenticate():
            return
        
        # Get account
        if not self.get_account():
            return
        
        # Get contract
        self.get_contract_id()
        
        print("\n📊 Bot is now running...")
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        try:
            while True:
                # Get current quote
                quote = self.get_quote()
                if quote:
                    self.price_history.append(quote)
                    print(f"Price: {quote['price']:.2f} | History: {len(self.price_history)} bars")
                
                # Check current position
                self.position = self.check_position()
                
                if self.position:
                    # We have a position - manage it
                    qty = self.position.get('netPos', 0)
                    pnl = self.position.get('netPrice', 0)
                    print(f"Position: {qty} contracts | P/L: ${pnl:.2f}")
                    
                    # Simple exit: close if position exists (add TP/SL logic here)
                    # For now, just monitor
                else:
                    # No position - check for entry
                    signal = self.check_momentum_signal()
                    if signal:
                        # Place order
                        order = self.place_order(signal, quantity=1)
                        if order:
                            self.active_order = order
                
                # Sleep before next poll
                time.sleep(1)  # Poll every 1 second
        
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping bot...")
            print("=" * 60)
            print("✅ Bot stopped")

if __name__ == "__main__":
    bot = TradovateRestBot()
    bot.run()
