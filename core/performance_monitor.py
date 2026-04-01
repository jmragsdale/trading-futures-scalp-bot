"""
Performance Monitoring and Risk Management Module
Real-time tracking of trading metrics and risk controls
"""

import time
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque
import asyncio
import logging

logger = logging.getLogger(__name__)

@dataclass
class TradeMetrics:
    """Metrics for a single trade"""
    entry_time: float
    exit_time: Optional[float] = None
    entry_price: float = 0.0
    exit_price: Optional[float] = None
    side: str = ""  # BUY or SELL
    quantity: int = 1
    pnl: Optional[float] = None
    pnl_ticks: Optional[float] = None
    max_favorable_excursion: float = 0.0  # MFE
    max_adverse_excursion: float = 0.0  # MAE
    latency_ms: float = 0.0
    slippage_ticks: float = 0.0

@dataclass
class PerformanceStats:
    """Aggregated performance statistics"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    total_commission: float = 0.0
    
    def calculate_derived_metrics(self):
        """Calculate derived performance metrics"""
        if self.total_trades > 0:
            self.win_rate = self.winning_trades / self.total_trades * 100
            
        if self.gross_loss < 0:
            self.profit_factor = abs(self.gross_profit / self.gross_loss)
            
        if self.winning_trades > 0:
            self.avg_win = self.gross_profit / self.winning_trades
            
        if self.losing_trades > 0:
            self.avg_loss = self.gross_loss / self.losing_trades

class RiskManager:
    """
    Real-time risk management and position monitoring
    Implements multiple risk controls and circuit breakers
    """
    
    def __init__(self, 
                 max_daily_loss: float = 500.0,
                 max_position_size: int = 10,
                 max_trades_per_day: int = 50,
                 max_consecutive_losses: int = 5,
                 risk_per_trade_pct: float = 2.0):
        
        # Risk limits
        self.max_daily_loss = max_daily_loss
        self.max_position_size = max_position_size
        self.max_trades_per_day = max_trades_per_day
        self.max_consecutive_losses = max_consecutive_losses
        self.risk_per_trade_pct = risk_per_trade_pct
        
        # Current state
        self.daily_pnl = 0.0
        self.trades_today = 0
        self.consecutive_losses = 0
        self.is_trading_allowed = True
        self.risk_violations = []
        
        # Position tracking
        self.open_positions: Dict[str, TradeMetrics] = {}
        self.closed_trades: List[TradeMetrics] = []
        
        # Performance tracking
        self.equity_curve = deque(maxlen=10000)
        self.peak_equity = 0.0
        self.current_drawdown = 0.0
        
    def check_pre_trade_risk(self, account_balance: float, 
                            position_size: int) -> Tuple[bool, str]:
        """
        Pre-trade risk checks
        Returns (allowed, reason)
        """
        
        # Check if trading is globally allowed
        if not self.is_trading_allowed:
            return False, "Trading suspended due to risk limits"
        
        # Check daily loss limit
        if self.daily_pnl <= -self.max_daily_loss:
            self.is_trading_allowed = False
            return False, f"Daily loss limit reached: ${self.daily_pnl:.2f}"
        
        # Check position size
        if position_size > self.max_position_size:
            return False, f"Position size {position_size} exceeds limit {self.max_position_size}"
        
        # Check daily trade count
        if self.trades_today >= self.max_trades_per_day:
            return False, f"Daily trade limit reached: {self.trades_today}"
        
        # Check consecutive losses
        if self.consecutive_losses >= self.max_consecutive_losses:
            self.is_trading_allowed = False
            return False, f"Consecutive loss limit reached: {self.consecutive_losses}"
        
        # Check risk per trade
        max_risk = account_balance * (self.risk_per_trade_pct / 100)
        # Additional validation can be added here
        
        return True, "Risk checks passed"
    
    def update_trade_metrics(self, trade_id: str, 
                           current_price: float, 
                           tick_size: float):
        """Update metrics for open position"""
        
        if trade_id not in self.open_positions:
            return
        
        trade = self.open_positions[trade_id]
        
        # Calculate current P&L
        if trade.side == "BUY":
            price_diff = current_price - trade.entry_price
        else:  # SELL
            price_diff = trade.entry_price - current_price
        
        pnl_ticks = price_diff / tick_size
        
        # Update MFE/MAE
        if pnl_ticks > trade.max_favorable_excursion:
            trade.max_favorable_excursion = pnl_ticks
        if pnl_ticks < -trade.max_adverse_excursion:
            trade.max_adverse_excursion = abs(pnl_ticks)
    
    def close_trade(self, trade_id: str, 
                   exit_price: float, 
                   tick_value: float,
                   commission: float = 2.0) -> TradeMetrics:
        """Close a trade and calculate final metrics"""
        
        if trade_id not in self.open_positions:
            logger.warning(f"Trade {trade_id} not found in open positions")
            return None
        
        trade = self.open_positions.pop(trade_id)
        trade.exit_time = time.time()
        trade.exit_price = exit_price
        
        # Calculate P&L
        if trade.side == "BUY":
            pnl_ticks = (exit_price - trade.entry_price) / tick_value
        else:  # SELL
            pnl_ticks = (trade.entry_price - exit_price) / tick_value
        
        trade.pnl_ticks = pnl_ticks
        trade.pnl = (pnl_ticks * tick_value * trade.quantity) - commission
        
        # Update daily P&L
        self.daily_pnl += trade.pnl
        
        # Update consecutive losses
        if trade.pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        # Add to closed trades
        self.closed_trades.append(trade)
        self.trades_today += 1
        
        # Update equity curve
        self.equity_curve.append(self.daily_pnl)
        
        logger.info(f"Trade closed: {trade.side} P&L: ${trade.pnl:.2f} "
                   f"({trade.pnl_ticks:.1f} ticks)")
        
        return trade
    
    def calculate_position_size(self, account_balance: float,
                              stop_loss_ticks: int,
                              tick_value: float) -> int:
        """Calculate optimal position size based on risk"""
        
        # Maximum risk per trade
        max_risk = account_balance * (self.risk_per_trade_pct / 100)
        
        # Risk per contract
        risk_per_contract = stop_loss_ticks * tick_value
        
        # Calculate contracts
        contracts = int(max_risk / risk_per_contract)
        
        # Apply limits
        contracts = min(contracts, self.max_position_size)
        contracts = max(contracts, 1)  # Minimum 1 contract
        
        return contracts
    
    def reset_daily_metrics(self):
        """Reset daily metrics (call at start of trading day)"""
        self.daily_pnl = 0.0
        self.trades_today = 0
        self.consecutive_losses = 0
        self.is_trading_allowed = True
        logger.info("Daily risk metrics reset")

class PerformanceMonitor:
    """
    Real-time performance monitoring and analysis
    Tracks execution quality and strategy performance
    """
    
    def __init__(self, commission_per_side: float = 1.0):
        self.commission_per_side = commission_per_side
        self.risk_manager = RiskManager()
        self.stats = PerformanceStats()
        
        # Latency tracking
        self.latency_samples = deque(maxlen=1000)
        self.order_timestamps: Dict[str, float] = {}
        
        # Real-time metrics
        self.tick_count = 0
        self.last_tick_time = time.time()
        self.ticks_per_second = 0.0
        
    def record_order_sent(self, order_id: str):
        """Record when order was sent"""
        self.order_timestamps[order_id] = time.perf_counter()
    
    def record_order_filled(self, order_id: str) -> float:
        """Record order fill and calculate latency"""
        if order_id in self.order_timestamps:
            latency_ms = (time.perf_counter() - self.order_timestamps[order_id]) * 1000
            self.latency_samples.append(latency_ms)
            del self.order_timestamps[order_id]
            
            # Update stats
            if self.latency_samples:
                self.stats.avg_latency_ms = np.mean(self.latency_samples)
                self.stats.max_latency_ms = np.max(self.latency_samples)
            
            return latency_ms
        return 0.0
    
    def update_tick_rate(self):
        """Update tick processing rate"""
        self.tick_count += 1
        current_time = time.time()
        
        if current_time - self.last_tick_time >= 1.0:
            self.ticks_per_second = self.tick_count / (current_time - self.last_tick_time)
            self.tick_count = 0
            self.last_tick_time = current_time
    
    def calculate_sharpe_ratio(self, returns: List[float], 
                              risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio"""
        if not returns or len(returns) < 2:
            return 0.0
        
        returns_array = np.array(returns)
        excess_returns = returns_array - (risk_free_rate / 252)  # Daily risk-free rate
        
        if np.std(excess_returns) == 0:
            return 0.0
        
        return np.sqrt(252) * np.mean(excess_returns) / np.std(excess_returns)
    
    def calculate_sortino_ratio(self, returns: List[float],
                               target_return: float = 0.0) -> float:
        """Calculate Sortino ratio (downside deviation)"""
        if not returns or len(returns) < 2:
            return 0.0
        
        returns_array = np.array(returns)
        downside_returns = returns_array[returns_array < target_return]
        
        if len(downside_returns) == 0:
            return 0.0
        
        downside_deviation = np.std(downside_returns)
        if downside_deviation == 0:
            return 0.0
        
        return np.sqrt(252) * (np.mean(returns_array) - target_return) / downside_deviation
    
    def calculate_max_drawdown(self) -> Tuple[float, float]:
        """Calculate maximum drawdown"""
        if not self.risk_manager.equity_curve:
            return 0.0, 0.0
        
        equity = np.array(self.risk_manager.equity_curve)
        cumulative = np.cumsum(equity)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = cumulative - running_max
        
        max_dd = np.min(drawdown)
        max_dd_pct = (max_dd / running_max[np.argmin(drawdown)]) * 100 if running_max[np.argmin(drawdown)] != 0 else 0
        
        return max_dd, max_dd_pct
    
    def generate_performance_report(self) -> Dict:
        """Generate comprehensive performance report"""
        
        # Calculate statistics from closed trades
        if self.risk_manager.closed_trades:
            trades_df = pd.DataFrame([
                {
                    'pnl': t.pnl,
                    'pnl_ticks': t.pnl_ticks,
                    'mfe': t.max_favorable_excursion,
                    'mae': t.max_adverse_excursion,
                    'duration': (t.exit_time - t.entry_time) if t.exit_time else 0,
                    'side': t.side
                }
                for t in self.risk_manager.closed_trades
            ])
            
            # Update performance stats
            self.stats.total_trades = len(trades_df)
            self.stats.winning_trades = len(trades_df[trades_df['pnl'] > 0])
            self.stats.losing_trades = len(trades_df[trades_df['pnl'] < 0])
            
            if self.stats.winning_trades > 0:
                self.stats.gross_profit = trades_df[trades_df['pnl'] > 0]['pnl'].sum()
                self.stats.avg_win = self.stats.gross_profit / self.stats.winning_trades
            
            if self.stats.losing_trades > 0:
                self.stats.gross_loss = trades_df[trades_df['pnl'] < 0]['pnl'].sum()
                self.stats.avg_loss = self.stats.gross_loss / self.stats.losing_trades
            
            self.stats.net_profit = self.stats.gross_profit + self.stats.gross_loss
            self.stats.total_commission = self.stats.total_trades * self.commission_per_side * 2
            
            # Calculate derived metrics
            self.stats.calculate_derived_metrics()
            
            # Calculate Sharpe and Sortino ratios
            if len(trades_df) > 1:
                returns = trades_df['pnl'].values
                self.stats.sharpe_ratio = self.calculate_sharpe_ratio(returns.tolist())
                self.stats.sortino_ratio = self.calculate_sortino_ratio(returns.tolist())
            
            # Calculate max drawdown
            self.stats.max_drawdown, self.stats.max_drawdown_pct = self.calculate_max_drawdown()
        
        # Create report
        report = {
            'timestamp': datetime.now().isoformat(),
            'performance': {
                'total_trades': self.stats.total_trades,
                'win_rate': f"{self.stats.win_rate:.1f}%",
                'profit_factor': f"{self.stats.profit_factor:.2f}",
                'net_profit': f"${self.stats.net_profit:.2f}",
                'avg_win': f"${self.stats.avg_win:.2f}",
                'avg_loss': f"${self.stats.avg_loss:.2f}",
                'max_drawdown': f"${self.stats.max_drawdown:.2f}",
                'max_drawdown_pct': f"{self.stats.max_drawdown_pct:.1f}%",
                'sharpe_ratio': f"{self.stats.sharpe_ratio:.2f}",
                'sortino_ratio': f"{self.stats.sortino_ratio:.2f}"
            },
            'execution': {
                'avg_latency_ms': f"{self.stats.avg_latency_ms:.1f}",
                'max_latency_ms': f"{self.stats.max_latency_ms:.1f}",
                'ticks_per_second': f"{self.ticks_per_second:.0f}",
                'total_commission': f"${self.stats.total_commission:.2f}"
            },
            'risk': {
                'daily_pnl': f"${self.risk_manager.daily_pnl:.2f}",
                'trades_today': self.risk_manager.trades_today,
                'consecutive_losses': self.risk_manager.consecutive_losses,
                'open_positions': len(self.risk_manager.open_positions),
                'trading_allowed': self.risk_manager.is_trading_allowed
            }
        }
        
        return report
    
    def print_live_dashboard(self):
        """Print live performance dashboard"""
        report = self.generate_performance_report()
        
        print("\n" + "="*60)
        print("           TRADING PERFORMANCE DASHBOARD")
        print("="*60)
        
        print("\n📊 PERFORMANCE METRICS:")
        for key, value in report['performance'].items():
            print(f"   {key.replace('_', ' ').title()}: {value}")
        
        print("\n⚡ EXECUTION QUALITY:")
        for key, value in report['execution'].items():
            print(f"   {key.replace('_', ' ').title()}: {value}")
        
        print("\n⚠️  RISK STATUS:")
        for key, value in report['risk'].items():
            status = "✅" if key == 'trading_allowed' and value else "🔴" if key == 'trading_allowed' else "  "
            print(f" {status} {key.replace('_', ' ').title()}: {value}")
        
        print("\n" + "="*60)
        
async def performance_monitoring_loop(monitor: PerformanceMonitor, interval_seconds: int = 10):
    """Async loop for periodic performance monitoring"""
    while True:
        try:
            monitor.print_live_dashboard()
            await asyncio.sleep(interval_seconds)
        except Exception as e:
            logger.error(f"Error in performance monitoring: {e}")
            await asyncio.sleep(interval_seconds)

if __name__ == "__main__":
    # Example usage
    monitor = PerformanceMonitor()
    risk_mgr = monitor.risk_manager
    
    # Simulate some trades
    risk_mgr.open_positions["trade1"] = TradeMetrics(
        entry_time=time.time(),
        entry_price=5000.0,
        side="BUY"
    )
    
    # Simulate price updates
    risk_mgr.update_trade_metrics("trade1", 5002.0, 0.25)
    
    # Close trade
    risk_mgr.close_trade("trade1", 5003.0, 0.25)
    
    # Print report
    monitor.print_live_dashboard()
