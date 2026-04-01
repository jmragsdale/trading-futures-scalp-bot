#!/usr/bin/env python3
"""
Momentum Scalp Bot Backtester
Tests Ross Cameron style VWAP + breakout strategy on historical small-cap data
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
import asyncio
import time

# Import scanner logic to find historical candidates
from momentum_scanner import MomentumScanner, ScannerConfig, GapCandidate

class MomentumScalpBacktester:
    def __init__(self, start_date: str, end_date: str, initial_capital: float = 5000.0):
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.trades = []
        self.max_risk_per_trade = 0.03  # 3% risk per trade
        self.max_daily_loss = 0.05      # 5% daily loss limit
        
    def calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """Calculate VWAP from OHLCV data"""
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        vwap = (typical_price * df['Volume']).cumsum() / df['Volume'].cumsum()
        return vwap
    
    def detect_vwap_reclaim(self, df: pd.DataFrame, vwap: pd.Series) -> List[int]:
        """Detect VWAP pullback and reclaim signals"""
        signals = []
        
        for i in range(10, len(df)):  # Need some history
            current_price = df.iloc[i]['Close']
            prev_prices = df.iloc[i-5:i]['Close']
            current_vwap = vwap.iloc[i]
            
            # Check if we pulled back to VWAP and are now reclaiming
            pulled_back = any(price <= current_vwap * 1.01 for price in prev_prices[-3:])
            reclaiming = current_price > current_vwap * 1.005  # 0.5% above VWAP
            volume_surge = df.iloc[i]['Volume'] > df.iloc[i-5:i]['Volume'].mean() * 1.5
            
            if pulled_back and reclaiming and volume_surge:
                signals.append(i)
                
        return signals
    
    def detect_premarket_breakout(self, df: pd.DataFrame, pm_high: float) -> List[int]:
        """Detect pre-market high breakout signals"""
        signals = []
        
        for i in range(len(df)):
            if df.iloc[i]['High'] > pm_high * 1.01:  # 1% above PM high
                volume_ok = df.iloc[i]['Volume'] > df.iloc[max(0,i-5):i]['Volume'].mean() * 1.2
                if volume_ok:
                    signals.append(i)
                    break  # Only first breakout
                    
        return signals
    
    def simulate_day_trading(self, symbol: str, trade_date: str, pm_gap_pct: float) -> List[Dict]:
        """Simulate intraday trading for one symbol/day"""
        try:
            # Get intraday data (1-minute)
            ticker = yf.Ticker(symbol)
            
            # Try to get 1m data (limited history) or fall back to 5m
            try:
                data = ticker.history(start=trade_date, end=(pd.to_datetime(trade_date) + timedelta(days=1)).strftime('%Y-%m-%d'), 
                                    interval="1m", prepost=True)
            except:
                data = ticker.history(start=trade_date, end=(pd.to_datetime(trade_date) + timedelta(days=1)).strftime('%Y-%m-%d'), 
                                    interval="5m", prepost=True)
            
            if data.empty:
                return []
            
            # Filter to market hours (9:30-11:30 for scalping)
            market_start = pd.Timestamp(trade_date + ' 09:30:00', tz='America/New_York')
            market_cutoff = pd.Timestamp(trade_date + ' 11:30:00', tz='America/New_York')
            
            # Convert to timezone-aware
            data.index = pd.to_datetime(data.index)
            if data.index.tz is None:
                data.index = data.index.tz_localize('America/New_York')
            else:
                data.index = data.index.tz_convert('America/New_York')
            
            market_data = data[(data.index >= market_start) & (data.index <= market_cutoff)]
            
            if market_data.empty:
                return []
            
            # Calculate VWAP
            vwap = self.calculate_vwap(market_data)
            
            # Estimate pre-market high (use first few minutes as proxy)
            pm_high = market_data['High'].iloc[:10].max()
            
            # Detect signals
            vwap_signals = self.detect_vwap_reclaim(market_data, vwap)
            breakout_signals = self.detect_premarket_breakout(market_data, pm_high)
            
            all_signals = sorted(set(vwap_signals + breakout_signals))
            
            trades = []
            for signal_idx in all_signals[:2]:  # Max 2 entries per stock per day
                trade = self.simulate_trade(market_data, signal_idx, vwap, symbol, trade_date, pm_gap_pct)
                if trade:
                    trades.append(trade)
                    
            return trades
            
        except Exception as e:
            print(f"Error simulating {symbol} on {trade_date}: {e}")
            return []
    
    def simulate_trade(self, data: pd.DataFrame, entry_idx: int, vwap: pd.Series, 
                      symbol: str, trade_date: str, pm_gap_pct: float) -> Optional[Dict]:
        """Simulate a single scalp trade"""
        
        entry_bar = data.iloc[entry_idx]
        entry_price = entry_bar['Close']
        entry_time = data.index[entry_idx]
        
        # Position sizing based on 3% account risk
        stop_loss = entry_price * 0.97  # 3% stop loss
        risk_per_share = entry_price - stop_loss
        max_risk_dollars = self.capital * self.max_risk_per_trade
        
        shares = int(max_risk_dollars / risk_per_share) if risk_per_share > 0 else 0
        if shares == 0:
            return None
            
        # Limit position size to available capital
        position_value = shares * entry_price
        if position_value > self.capital * 0.5:  # Max 50% position
            shares = int(self.capital * 0.5 / entry_price)
            
        if shares == 0:
            return None
        
        # Set profit target (5-10% for scalps)
        target_1 = entry_price * 1.05  # 5% target
        target_2 = entry_price * 1.10  # 10% target
        
        # Simulate trade execution from entry forward
        exit_price = None
        exit_time = None
        exit_reason = None
        
        for i in range(entry_idx + 1, len(data)):
            bar = data.iloc[i]
            current_time = data.index[i]
            
            # Check stop loss
            if bar['Low'] <= stop_loss:
                exit_price = stop_loss
                exit_time = current_time
                exit_reason = 'STOP_LOSS'
                break
                
            # Check target 1 (take partial)
            if bar['High'] >= target_1:
                exit_price = target_1
                exit_time = current_time  
                exit_reason = 'TARGET_1'
                break
                
            # Trail stop if profitable
            if bar['Close'] > entry_price * 1.02:  # 2% profit
                new_stop = max(stop_loss, bar['Close'] * 0.99)  # Trail 1% below current
                if bar['Low'] <= new_stop:
                    exit_price = new_stop
                    exit_time = current_time
                    exit_reason = 'TRAILING_STOP'
                    break
        
        # If no exit triggered, close at cutoff (11:30 AM)
        if exit_price is None:
            exit_price = data.iloc[-1]['Close']
            exit_time = data.index[-1]
            exit_reason = 'TIME_STOP'
        
        # Calculate P&L
        pnl = (exit_price - entry_price) * shares
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        
        return {
            'date': trade_date,
            'symbol': symbol,
            'pm_gap_pct': pm_gap_pct,
            'entry_time': str(entry_time),
            'entry_price': round(entry_price, 3),
            'exit_time': str(exit_time),
            'exit_price': round(exit_price, 3),
            'exit_reason': exit_reason,
            'shares': shares,
            'pnl': round(pnl, 2),
            'pnl_pct': round(pnl_pct, 2),
            'hold_time_min': int((exit_time - entry_time).total_seconds() / 60)
        }
    
    def find_historical_candidates(self, trade_date: str) -> List[Dict]:
        """Find momentum candidates for a specific date using simplified logic"""
        # Since we can't easily run the full scanner historically, 
        # we'll use a simplified approach with known momentum tickers
        
        momentum_tickers = [
            'SOXL', 'TQQQ', 'SPXL', 'NVDA', 'AMD', 'TSLA', 'NFLX', 'SHOP',
            'COIN', 'MARA', 'RIOT', 'PLTR', 'SOFI', 'RIVN', 'LCID', 'NIO',
            'GME', 'AMC', 'CLOV', 'WISH', 'SPCE', 'HOOD', 'UPST', 'AFRM'
        ]
        
        candidates = []
        for symbol in momentum_tickers:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=(pd.to_datetime(trade_date) - timedelta(days=5)).strftime('%Y-%m-%d'), 
                                    end=(pd.to_datetime(trade_date) + timedelta(days=1)).strftime('%Y-%m-%d'))
                
                if len(hist) < 2:
                    continue
                    
                # Get previous close and current open
                prev_close = hist['Close'].iloc[-2]
                current_open = hist['Open'].iloc[-1]
                current_price = hist['Close'].iloc[-1]
                
                # Check gap criteria
                gap_pct = ((current_open - prev_close) / prev_close) * 100
                
                if (abs(gap_pct) >= 4.0 and 2.0 <= current_price <= 30.0 and 
                    hist['Volume'].iloc[-1] > hist['Volume'].iloc[-5:-1].mean() * 1.5):
                    candidates.append({
                        'symbol': symbol,
                        'gap_pct': gap_pct,
                        'price': current_price,
                        'volume': hist['Volume'].iloc[-1]
                    })
                    
            except Exception as e:
                continue
                
        # Sort by gap magnitude and return top candidates
        candidates.sort(key=lambda x: abs(x['gap_pct']), reverse=True)
        return candidates[:5]  # Top 5 candidates per day
    
    def run_backtest(self) -> Dict:
        """Run the full backtest over the date range"""
        print(f"Running momentum scalp backtest from {self.start_date} to {self.end_date}")
        
        current_date = pd.to_datetime(self.start_date)
        end_date = pd.to_datetime(self.end_date)
        
        total_trades = []
        daily_pnl = []
        
        while current_date <= end_date:
            # Skip weekends
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue
                
            date_str = current_date.strftime('%Y-%m-%d')
            print(f"Processing {date_str}...")
            
            # Find candidates for this day
            candidates = self.find_historical_candidates(date_str)
            
            if not candidates:
                current_date += timedelta(days=1)
                continue
            
            print(f"  Found {len(candidates)} candidates")
            
            day_trades = []
            day_pnl = 0
            
            # Simulate trading each candidate
            for candidate in candidates:
                symbol = candidate['symbol']
                gap_pct = candidate['gap_pct']
                
                trades = self.simulate_day_trading(symbol, date_str, gap_pct)
                day_trades.extend(trades)
                
                for trade in trades:
                    day_pnl += trade['pnl']
                    self.capital += trade['pnl']
                
                # Rate limit
                time.sleep(0.5)
            
            total_trades.extend(day_trades)
            daily_pnl.append({
                'date': date_str,
                'pnl': round(day_pnl, 2),
                'trades': len(day_trades),
                'capital': round(self.capital, 2)
            })
            
            print(f"  Day P&L: ${day_pnl:.2f}, Trades: {len(day_trades)}")
            
            # Check daily loss limit
            if day_pnl < -self.capital * self.max_daily_loss:
                print(f"  Daily loss limit hit: ${day_pnl:.2f}")
            
            current_date += timedelta(days=1)
        
        return self.analyze_results(total_trades, daily_pnl)
    
    def analyze_results(self, trades: List[Dict], daily_pnl: List[Dict]) -> Dict:
        """Analyze backtest results"""
        if not trades:
            return {}
        
        winning_trades = [t for t in trades if t['pnl'] > 0]
        losing_trades = [t for t in trades if t['pnl'] <= 0]
        
        total_pnl = sum(t['pnl'] for t in trades)
        total_return = ((self.capital - self.initial_capital) / self.initial_capital) * 100
        
        avg_hold_time = np.mean([t['hold_time_min'] for t in trades])
        
        return {
            'initial_capital': self.initial_capital,
            'final_capital': round(self.capital, 2),
            'total_pnl': round(total_pnl, 2),
            'total_return_pct': round(total_return, 2),
            'total_trades': len(trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate_pct': round(len(winning_trades) / len(trades) * 100, 1),
            'avg_win': round(sum(t['pnl'] for t in winning_trades) / len(winning_trades), 2) if winning_trades else 0,
            'avg_loss': round(sum(t['pnl'] for t in losing_trades) / len(losing_trades), 2) if losing_trades else 0,
            'avg_hold_time_min': round(avg_hold_time, 1),
            'best_trade': max(trades, key=lambda x: x['pnl']),
            'worst_trade': min(trades, key=lambda x: x['pnl']),
            'trades': trades,
            'daily_pnl': daily_pnl
        }

def main():
    # Test recent period
    end_date = date.today().strftime('%Y-%m-%d')
    start_date = (date.today() - timedelta(days=60)).strftime('%Y-%m-%d')
    
    print("🚀 MOMENTUM SCALP BOT BACKTEST")
    print("=" * 50)
    
    backtester = MomentumScalpBacktester(start_date, end_date, initial_capital=5000.0)
    results = backtester.run_backtest()
    
    if not results:
        print("No results generated")
        return
    
    print(f"\n📊 RESULTS SUMMARY")
    print(f"Initial Capital: ${results['initial_capital']:,}")
    print(f"Final Capital: ${results['final_capital']:,}")
    print(f"Total P&L: ${results['total_pnl']:,}")
    print(f"Total Return: {results['total_return_pct']}%")
    print(f"Total Trades: {results['total_trades']}")
    print(f"Win Rate: {results['win_rate_pct']}%")
    print(f"Average Win: ${results['avg_win']}")
    print(f"Average Loss: ${results['avg_loss']}")
    print(f"Average Hold Time: {results['avg_hold_time_min']} minutes")
    
    print(f"\n🏆 Best Trade: {results['best_trade']['symbol']} ({results['best_trade']['date']}) - ${results['best_trade']['pnl']}")
    print(f"💀 Worst Trade: {results['worst_trade']['symbol']} ({results['worst_trade']['date']}) - ${results['worst_trade']['pnl']}")

if __name__ == "__main__":
    main()