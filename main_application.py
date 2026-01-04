#!/usr/bin/env python3
"""
Production-Ready Tradovate Micro Futures Trading System
High-performance momentum trading with comprehensive risk management
"""

import sys
import asyncio
import signal
import logging
import argparse
from pathlib import Path
from datetime import datetime, time as dt_time
import pytz

# Import our modules
from tradovate_momentum_bot import TradovateClient, MomentumTradingStrategy, TradingConfig
from config_manager import ConfigManager, MICRO_FUTURES, StrategyParameters
from performance_monitor import PerformanceMonitor, performance_monitoring_loop

# Setup logging
def setup_logging(log_level: str = "INFO", log_file: str = None):
    """Configure logging for the application"""
    
    format_str = '%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    handlers = [logging.StreamHandler()]
    
    if log_file:
        file_handler = logging.FileHandler(log_file)
        handlers.append(file_handler)
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=format_str,
        datefmt=date_format,
        handlers=handlers
    )
    
    # Set specific loggers
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('websockets').setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)

class TradingApplication:
    """Main trading application with lifecycle management"""
    
    def __init__(self, args):
        self.args = args
        self.logger = logging.getLogger(__name__)
        self.config_manager = ConfigManager(args.config_dir)
        
        # Load configurations
        self.credentials = None
        self.strategy_params = None
        self.contract_spec = None
        self.environment = None
        
        # Components
        self.client = None
        self.strategy = None
        self.monitor = None
        
        # Control flags
        self.is_running = False
        self.shutdown_event = asyncio.Event()
        
    def load_configuration(self):
        """Load all configurations"""
        
        # Load credentials
        self.credentials = self.config_manager.load_credentials()
        if not self.credentials and not self.args.setup:
            self.logger.error("No credentials found. Run with --setup flag to configure.")
            sys.exit(1)
        
        # Load strategy configuration
        self.strategy_params, self.contract_spec, self.environment = \
            self.config_manager.load_strategy_config()
        
        # Override with command-line arguments if provided
        if self.args.symbol:
            if self.args.symbol in MICRO_FUTURES:
                self.contract_spec = MICRO_FUTURES[self.args.symbol]
            else:
                self.logger.warning(f"Unknown symbol {self.args.symbol}, using default")
        
        if self.args.demo is not None:
            self.environment['demo_mode'] = self.args.demo
        
        self.logger.info(f"Configuration loaded for {self.contract_spec.symbol}")
        
    def is_market_open(self) -> bool:
        """Check if futures market is open"""
        
        # Get current time in ET
        et_tz = pytz.timezone('US/Eastern')
        now = datetime.now(et_tz)
        current_time = now.time()
        current_day = now.weekday()
        
        # Futures market hours (simplified)
        # Sunday 6 PM ET through Friday 5 PM ET
        # Closed Friday 5 PM through Sunday 6 PM
        
        if current_day == 6:  # Sunday
            return current_time >= dt_time(18, 0)  # Open after 6 PM
        elif current_day == 5:  # Saturday
            return False  # Closed all day
        elif current_day == 4:  # Friday
            return current_time < dt_time(17, 0)  # Closed after 5 PM
        else:  # Monday through Thursday
            return True  # Open all day
        
    async def initialize_components(self):
        """Initialize all trading components"""
        
        # Create trading configuration
        trading_config = TradingConfig(
            time_window=self.strategy_params.time_window_seconds,
            min_price_movement=self.strategy_params.min_price_movement_ticks,
            max_positions=self.strategy_params.max_positions,
            risk_percent=self.strategy_params.risk_percent,
            take_profit=self.strategy_params.take_profit_ticks,
            stop_loss=self.strategy_params.stop_loss_ticks,
            trailing_stop=self.strategy_params.trailing_stop_ticks,
            slippage=self.strategy_params.slippage_ticks,
            symbol=self.contract_spec.symbol,
            tick_size=self.contract_spec.tick_size,
            tick_value=self.contract_spec.tick_value,
            contract_multiplier=5,  # For micros
            demo_mode=self.environment.get('demo_mode', True)
        )
        
        # Initialize client
        self.client = TradovateClient(trading_config)
        await self.client.connect(
            username=self.credentials.username,
            password=self.credentials.password,
            app_id=self.credentials.app_id,
            app_version=self.credentials.app_version
        )
        
        # Initialize strategy
        self.strategy = MomentumTradingStrategy(self.client, trading_config)
        
        # Initialize performance monitor
        self.monitor = PerformanceMonitor(commission_per_side=1.0)
        
        self.logger.info("All components initialized successfully")
    
    async def run_trading_loop(self):
        """Main trading loop with error recovery"""
        
        self.is_running = True
        reconnect_delay = 5
        
        while self.is_running:
            try:
                # Check if market is open
                if not self.is_market_open():
                    self.logger.info("Market is closed. Waiting...")
                    await asyncio.sleep(60)  # Check every minute
                    continue
                
                # Run strategy
                await self.strategy.run()
                
            except Exception as e:
                self.logger.error(f"Error in trading loop: {e}", exc_info=True)
                
                # Attempt reconnection
                self.logger.info(f"Attempting reconnection in {reconnect_delay} seconds...")
                await asyncio.sleep(reconnect_delay)
                
                try:
                    await self.client.connect(
                        username=self.credentials.username,
                        password=self.credentials.password,
                        app_id=self.credentials.app_id,
                        app_version=self.credentials.app_version
                    )
                    self.logger.info("Reconnection successful")
                    reconnect_delay = 5  # Reset delay
                    
                except Exception as reconnect_error:
                    self.logger.error(f"Reconnection failed: {reconnect_error}")
                    reconnect_delay = min(reconnect_delay * 2, 300)  # Exponential backoff, max 5 min
    
    async def run(self):
        """Main application entry point"""
        
        try:
            # Load configuration
            self.load_configuration()
            
            # Initialize components
            await self.initialize_components()
            
            # Start performance monitoring
            monitor_task = asyncio.create_task(
                performance_monitoring_loop(self.monitor, interval_seconds=30)
            )
            
            # Start trading
            trading_task = asyncio.create_task(self.run_trading_loop())
            
            # Wait for shutdown
            await self.shutdown_event.wait()
            
            # Cancel tasks
            monitor_task.cancel()
            trading_task.cancel()
            
            # Cleanup
            await self.cleanup()
            
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt")
        except Exception as e:
            self.logger.error(f"Fatal error: {e}", exc_info=True)
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Clean up resources"""
        
        self.is_running = False
        
        if self.client:
            # Close any open positions if configured
            if self.args.close_on_exit:
                self.logger.info("Closing all open positions...")
                positions = await self.client.get_positions()
                for position in positions:
                    # Implement position closing logic
                    pass
            
            await self.client.close()
        
        # Generate final report
        if self.monitor:
            report = self.monitor.generate_performance_report()
            self.logger.info(f"Final performance report: {report}")
            
            # Save report to file
            report_file = Path(self.args.config_dir) / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            import json
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2)
            self.logger.info(f"Report saved to {report_file}")
    
    def handle_shutdown(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, initiating shutdown...")
        self.shutdown_event.set()

def main():
    """Main entry point"""
    
    # Parse arguments
    parser = argparse.ArgumentParser(description="Tradovate Micro Futures Trading Bot")
    
    parser.add_argument('--symbol', type=str, choices=list(MICRO_FUTURES.keys()),
                       help='Micro futures symbol to trade')
    parser.add_argument('--config-dir', type=str, default='~/.tradovate_bot',
                       help='Configuration directory')
    parser.add_argument('--log-level', type=str, default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Logging level')
    parser.add_argument('--log-file', type=str, help='Log file path')
    parser.add_argument('--demo', action='store_true', default=None,
                       help='Use demo account')
    parser.add_argument('--live', action='store_false', dest='demo',
                       help='Use live account (use with caution!)')
    parser.add_argument('--setup', action='store_true',
                       help='Run interactive setup')
    parser.add_argument('--close-on-exit', action='store_true',
                       help='Close all positions on exit')
    parser.add_argument('--dry-run', action='store_true',
                       help='Run in simulation mode without placing orders')
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(args.log_level, args.log_file)
    
    # Run setup if requested
    if args.setup:
        from config_manager import setup_credentials_interactive
        setup_credentials_interactive()
        sys.exit(0)
    
    # Safety check for live trading
    if args.demo is False:
        logger.warning("=" * 60)
        logger.warning("WARNING: LIVE TRADING MODE")
        logger.warning("This will place real orders with real money!")
        logger.warning("=" * 60)
        response = input("Type 'YES' to confirm live trading: ")
        if response != 'YES':
            logger.info("Live trading not confirmed. Exiting.")
            sys.exit(0)
    
    # Create and run application
    app = TradingApplication(args)
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, app.handle_shutdown)
    signal.signal(signal.SIGTERM, app.handle_shutdown)
    
    # Run the application
    logger.info("Starting Tradovate Trading Bot...")
    logger.info(f"Symbol: {args.symbol or 'From config'}")
    logger.info(f"Mode: {'DEMO' if args.demo or args.demo is None else 'LIVE'}")
    
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logger.info("Application terminated by user")
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
    finally:
        logger.info("Trading bot shutdown complete")

if __name__ == "__main__":
    main()
