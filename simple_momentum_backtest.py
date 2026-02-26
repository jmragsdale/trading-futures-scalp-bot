#!/usr/bin/env python3
"""
Simple Momentum Scalp Backtest
Tests basic VWAP + breakout strategy without dependencies
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
import time

class SimpleMomentumBacktester:
    def __init__(self, start_date: str, end_date: str, initial_capital: float = 5000.0):
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.trades = []
        self.daily_pnl = []
        
    def get_momentum_candidates(self, trade_date: str) -> List[str]:
        """Get known momentum tickers for backtesting"""
        # Ross Cameron style momentum tickers - small/mid caps that gap frequently
        tickers = [
            'SOXL', 'NVDA', 'AMD', 'TSLA', 'SHOP', 'COIN', 'MARA', 'RIOT', 
            'PLTR', 'SOFI', 'RIVN', 'LCID', 'NIO', 'GME', 'AMC', 'SPCE',
            'HOOD', 'UPST', 'AFRM', 'CLOV', 'WISH', 'BBBY', 'PTON', 'ZM'
        ]
        
        # Simple filter - check for gaps on this date
        gap_candidates = []
        for ticker in tickers:
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(start=(pd.to_datetime(trade_date) - timedelta(days=5)).strftime('%Y-%m-%d'), 
                                   end=(pd.to_datetime(trade_date) + timedelta(days=1)).strftime('%Y-%m-%d'))
                
                if len(hist) >= 2:
                    prev_close = hist['Close'].iloc[-2]
                    current_open = hist['Open'].iloc[-1]
                    current_price = hist['Close'].iloc[-1]
                    
                    gap_pct = ((current_open - prev_close) / prev_close) * 100
                    
                    # Ross Cameron criteria: 4%+ gap, $2-$30 price range, decent volume
                    if (abs(gap_pct) >= 4.0 and 2.0 <= current_price <= 30.0 and 
                        hist['Volume'].iloc[-1] > 100000):
                        gap_candidates.append(ticker)
                        
            except Exception:
                continue
                
        return gap_candidates[:5]  # Top 5 per day
    
    def backtest_day(self, trade_date: str, tickers: List[str]) -> List[Dict]:
        """Backtest momentum strategy for one day"""
        day_trades = []
        
        for ticker in tickers:
            try:
                # Get intraday data
                stock = yf.Ticker(ticker)
                
                # Try 1m data first, fall back to 5m
                try:
                    data = stock.history(start=trade_date, 
                                       end=(pd.to_datetime(trade_date) + timedelta(days=1)).strftime('%Y-%m-%d'), 
                                       interval="1m", prepost=True)
                except:
                    data = stock.history(start=trade_date, 
                                       end=(pd.to_datetime(trade_date) + timedelta(days=1)).strftime('%Y-%m-%d'), 
                                       interval="5m", prepost=True)
                
                if data.empty:
                    continue
                
                # Focus on 9:30-11:30 AM ET (prime scalping window)
                market_start = pd.Timestamp(trade_date + ' 09:30:00', tz='America/New_York')
                market_end = pd.Timestamp(trade_date + ' 11:30:00', tz='America/New_York')
                
                # Convert timezone
                if data.index.tz is None:
                    data.index = data.index.tz_localize('UTC').tz_convert('America/New_York')
                else:
                    data.index = data.index.tz_convert('America/New_York')
                
                # Filter to trading window
                trading_data = data[(data.index >= market_start) & (data.index <= market_end)]
                
                if len(trading_data) < 5:
                    continue
                
                # Simple momentum entry: break of 15-minute high with volume
                trades = self.find_momentum_entries(trading_data, ticker, trade_date)
                day_trades.extend(trades)
                
            except Exception as e:
                print(f"Error processing {ticker}: {e}")
                continue
                
        return day_trades
    
    def find_momentum_entries(self, data: pd.DataFrame, ticker: str, trade_date: str) -> List[Dict]:
        """Find momentum breakout entries"""
        trades = []
        
        if len(data) < 15:
            return trades
        
        # Calculate rolling 15-period high (similar to pre-market high concept)
        data['rolling_high'] = data['High'].rolling(window=15).max()
        data['volume_avg'] = data['Volume'].rolling(window=10).mean()
        
        for i in range(15, len(data)):
            current = data.iloc[i]
            
            # Momentum breakout signal
            broke_high = current['High'] > data['rolling_high'].iloc[i-1] * 1.01  # 1% above rolling high
            volume_surge = current['Volume'] > data['volume_avg'].iloc[i] * 1.5     # 50% above avg volume
            
            if broke_high and volume_surge:
                trade = self.simulate_momentum_trade(data[i:], ticker, trade_date, current['Close'])
                if trade:
                    trades.append(trade)
                    break  # Only one entry per symbol per day
                    
        return trades
    
    def simulate_momentum_trade(self, future_data: pd.DataFrame, ticker: str, 
                              trade_date: str, entry_price: float) -> Optional[Dict]:
        """Simulate a momentum scalp trade"""
        
        # Position sizing (3% risk model like Ross Cameron)
        stop_loss = entry_price * 0.975  # 2.5% stop loss
        target_1 = entry_price * 1.05    # 5% target (typical scalp)
        target_2 = entry_price * 1.08    # 8% extended target
        
        risk_per_share = entry_price - stop_loss
        max_risk = self.capital * 0.03   # Risk 3% of account
        
        shares = int(max_risk / risk_per_share) if risk_per_share > 0 else 0
        
        if shares == 0:
            return None
        
        # Limit position size
        position_value = shares * entry_price
        if position_value > self.capital * 0.5:  # Max 50% position
            shares = int(self.capital * 0.5 / entry_price)
        
        if shares == 0:
            return None
        
        # Simulate trade execution
        entry_time = future_data.index[0]
        exit_price = None
        exit_time = None
        exit_reason = None
        
        for i in range(1, min(len(future_data), 60)):  # Max 60 periods (1-5 hours depending on interval)
            bar = future_data.iloc[i]
            
            # Check stop loss
            if bar['Low'] <= stop_loss:
                exit_price = stop_loss
                exit_time = future_data.index[i]
                exit_reason = 'STOP_LOSS'
                break
            
            # Check first target (take some profit)
            if bar['High'] >= target_1:
                exit_price = target_1
                exit_time = future_data.index[i]
                exit_reason = 'TARGET_HIT'
                break
                
            # Time-based exit (scalp rule - don't hold too long)
            if i > 30:  # Exit after 30 periods if no target hit
                exit_price = bar['Close']
                exit_time = future_data.index[i]
                exit_reason = 'TIME_EXIT'
                break
        
        # If no exit, close at end of window
        if exit_price is None:
            exit_price = future_data.iloc[-1]['Close']
            exit_time = future_data.index[-1]
            exit_reason = 'END_OF_WINDOW'
        
        # Calculate P&L
        pnl = (exit_price - entry_price) * shares
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        hold_minutes = int((exit_time - entry_time).total_seconds() / 60)
        
        # Update capital
        self.capital += pnl
        
        return {
            'date': trade_date,
            'ticker': ticker,
            'entry_time': str(entry_time.time()),
            'entry_price': round(entry_price, 3),
            'exit_time': str(exit_time.time()),
            'exit_price': round(exit_price, 3),
            'exit_reason': exit_reason,
            'shares': shares,
            'pnl': round(pnl, 2),
            'pnl_pct': round(pnl_pct, 2),
            'hold_min': hold_minutes,
            'capital_after': round(self.capital, 2)
        }
    
    def run_backtest(self) -> Dict:
        """Run full backtest"""
        print(f"🚀 Running momentum scalp backtest from {self.start_date} to {self.end_date}")
        
        current_date = pd.to_datetime(self.start_date)
        end_date = pd.to_datetime(self.end_date)
        
        while current_date <= end_date:
            # Skip weekends
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue
            
            date_str = current_date.strftime('%Y-%m-%d')
            print(f"Processing {date_str}...")
            
            # Find momentum candidates
            tickers = self.get_momentum_candidates(date_str)
            
            if not tickers:
                print(f"  No candidates found")
                current_date += timedelta(days=1)
                continue
            
            print(f"  Candidates: {', '.join(tickers)}")
            
            # Backtest this day
            day_trades = self.backtest_day(date_str, tickers)
            
            day_pnl = sum(t['pnl'] for t in day_trades)
            
            self.trades.extend(day_trades)
            self.daily_pnl.append({
                'date': date_str,
                'pnl': round(day_pnl, 2),
                'trades': len(day_trades),
                'capital': round(self.capital, 2)
            })
            
            print(f"  Day results: {len(day_trades)} trades, ${day_pnl:.2f} P&L")
            
            current_date += timedelta(days=1)
            time.sleep(1)  # Rate limiting
        
        return self.analyze_results()
    
    def analyze_results(self) -> Dict:
        """Analyze backtest results"""
        if not self.trades:
            return {'error': 'No trades executed'}
        
        winners = [t for t in self.trades if t['pnl'] > 0]
        losers = [t for t in self.trades if t['pnl'] <= 0]
        
        total_pnl = sum(t['pnl'] for t in self.trades)
        total_return = ((self.capital - self.initial_capital) / self.initial_capital) * 100
        
        avg_hold_time = np.mean([t['hold_min'] for t in self.trades])
        max_win = max(self.trades, key=lambda x: x['pnl'])
        max_loss = min(self.trades, key=lambda x: x['pnl'])
        
        return {
            'initial_capital': self.initial_capital,
            'final_capital': round(self.capital, 2),
            'total_pnl': round(total_pnl, 2),
            'total_return_pct': round(total_return, 2),
            'total_trades': len(self.trades),
            'win_rate_pct': round(len(winners) / len(self.trades) * 100, 1),
            'avg_win': round(sum(t['pnl'] for t in winners) / len(winners), 2) if winners else 0,
            'avg_loss': round(sum(t['pnl'] for t in losers) / len(losers), 2) if losers else 0,
            'avg_hold_time': round(avg_hold_time, 1),
            'best_trade': max_win,
            'worst_trade': max_loss,
            'total_winners': len(winners),
            'total_losers': len(losers),
            'trades_detail': self.trades[-10:],  # Last 10 trades
            'monthly_pnl': self.get_monthly_summary()
        }
    
    def get_monthly_summary(self) -> Dict:
        """Get monthly P&L breakdown"""
        monthly = {}
        for day in self.daily_pnl:
            month = day['date'][:7]  # YYYY-MM
            monthly[month] = monthly.get(month, 0) + day['pnl']
        return monthly

def main():
    # Test last 60 days
    end_date = date.today().strftime('%Y-%m-%d')
    start_date = (date.today() - timedelta(days=60)).strftime('%Y-%m-%d')
    
    backtester = SimpleMomentumBacktester(start_date, end_date, initial_capital=5000.0)
    results = backtester.run_backtest()
    
    if 'error' in results:
        print(f"❌ {results['error']}")
        return
    
    print(f"\n{'='*60}")
    print(f"📊 MOMENTUM SCALP BACKTEST RESULTS")
    print(f"{'='*60}")
    print(f"🏦 Initial Capital: ${results['initial_capital']:,}")
    print(f"💰 Final Capital: ${results['final_capital']:,}")
    print(f"📈 Total P&L: ${results['total_pnl']:,}")
    print(f"📊 Total Return: {results['total_return_pct']:.2f}%")
    print(f"🔢 Total Trades: {results['total_trades']}")
    print(f"🏆 Win Rate: {results['win_rate_pct']}% ({results['total_winners']}W / {results['total_losers']}L)")
    print(f"💵 Average Win: ${results['avg_win']}")
    print(f"💸 Average Loss: ${results['avg_loss']}")
    print(f"⏱️  Average Hold Time: {results['avg_hold_time']} minutes")
    print(f"\n🚀 Best Trade: {results['best_trade']['ticker']} ({results['best_trade']['date']}) - ${results['best_trade']['pnl']}")
    print(f"💀 Worst Trade: {results['worst_trade']['ticker']} ({results['worst_trade']['date']}) - ${results['worst_trade']['pnl']}")
    
    print(f"\n📅 Monthly P&L:")
    for month, pnl in results['monthly_pnl'].items():
        print(f"  {month}: ${pnl:.2f}")
    
    print(f"\n🔍 Last 10 Trades:")
    for trade in results['trades_detail']:
        print(f"  {trade['date']} {trade['ticker']}: ${trade['pnl']} ({trade['exit_reason']}) - {trade['hold_min']}min")

if __name__ == "__main__":
    main()