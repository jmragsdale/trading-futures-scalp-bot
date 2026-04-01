#!/usr/bin/env python3
"""
Tradovate Bot Runner - Handles credentials and launches the momentum bot
"""

import os
import sys
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def main():
    """Main entry point"""
    
    print("🚀 Tradovate Momentum Bot - Starting...")
    print("=" * 60)
    
    # Get credentials from environment
    username = os.getenv('TRADOVATE_DEMO_USERNAME')
    password = os.getenv('TRADOVATE_DEMO_PASSWORD')
    app_id = os.getenv('TRADOVATE_DEMO_APP_ID')
    app_version = os.getenv('TRADOVATE_DEMO_APP_VERSION')
    device_id = os.getenv('TRADOVATE_DEMO_DEVICE_ID')
    cid = os.getenv('TRADOVATE_DEMO_CID')
    sec = os.getenv('TRADOVATE_DEMO_SEC')
    api_url = os.getenv('TRADOVATE_DEMO_API_URL', 'https://demo.tradovateapi.com/v1')
    ws_url = os.getenv('TRADOVATE_DEMO_WS_URL', 'wss://demo.tradovateapi.com/v1/websocket')
    
    # Get symbol from command line (default: MES)
    symbol = sys.argv[1] if len(sys.argv) > 1 else "MES"
    
    print(f"Account: DEMO4600924")
    print(f"Balance: $49,870.78")
    print(f"Symbol: {symbol}")
    print(f"API URL: {api_url}")
    print("=" * 60)
    print()
    
    # Import the bot (after we've loaded environment)
    try:
        from tradovate_momentum_bot import TradingConfig, TradovateClient, MomentumTradingStrategy
        
        # Create config
        config = TradingConfig(
            symbol=symbol,
            api_url=api_url,
            ws_url=ws_url,
            demo_mode=True,
            # Strategy params (optimized for MES)
            time_window=14,
            min_price_movement=7,
            take_profit=25,
            stop_loss=12,
            trailing_stop=6,
            max_positions=1
        )
        
        print(f"✅ Strategy configured:")
        print(f"  - Time window: {config.time_window} seconds")
        print(f"  - Min move: {config.min_price_movement} ticks")
        print(f"  - Take profit: {config.take_profit} ticks (${config.take_profit * config.tick_value:.2f})")
        print(f"  - Stop loss: {config.stop_loss} ticks (${config.stop_loss * config.tick_value:.2f})")
        print(f"  - Max positions: {config.max_positions}")
        print()
        
        # Create client
        client = TradovateClient(config)
        
        # Connect to Tradovate
        print("🔌 Connecting to Tradovate...")
        await client.connect(
            username=username,
            password=password,
            app_id=app_id,
            app_version=app_version
        )
        
        print("✅ Connected successfully!")
        print()
        
        # Create and run strategy
        print("📊 Starting momentum strategy...")
        print("Press Ctrl+C to stop")
        print("=" * 60)
        print()
        
        strategy = MomentumTradingStrategy(client, config)
        await strategy.run()
        
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping bot...")
        print("=" * 60)
        print("✅ Bot stopped successfully")
    except ImportError as e:
        print(f"❌ Error importing bot: {e}")
        print("\nThe bot file might be missing or have syntax errors.")
        print("Check: tradovate_momentum_bot.py")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
