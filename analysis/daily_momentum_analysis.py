#!/usr/bin/env python3
"""
Daily Momentum Analysis - Quick Performance Estimate
Uses daily data only to estimate momentum scalp performance
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date

def analyze_momentum_performance():
    # Ross Cameron style momentum tickers
    tickers = ['NVDA', 'AMD', 'TSLA', 'COIN', 'MARA', 'RIOT', 'PLTR', 'SOFI', 'GME', 'AMC']
    
    # Look at last 3 months of data
    end_date = date.today()
    start_date = end_date - timedelta(days=90)
    
    print(f"📊 MOMENTUM SCALP ANALYSIS ({start_date} to {end_date})")
    print("="*60)
    
    total_opportunities = 0
    successful_trades = 0
    total_pnl = 0
    trade_details = []
    
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date.strftime('%Y-%m-%d'), 
                                end=end_date.strftime('%Y-%m-%d'))
            
            if hist.empty:
                continue
            
            print(f"\n🔍 Analyzing {ticker}...")
            
            # Find gap days (4%+ gaps)
            hist['prev_close'] = hist['Close'].shift(1)
            hist['gap_pct'] = ((hist['Open'] - hist['prev_close']) / hist['prev_close'] * 100)
            
            # Filter for momentum opportunities
            momentum_days = hist[
                (abs(hist['gap_pct']) >= 4.0) &  # 4% gap minimum
                (hist['Volume'] > hist['Volume'].rolling(10).mean() * 1.5)  # Volume surge
            ]
            
            for date_idx, row in momentum_days.iterrows():
                gap_pct = row['gap_pct']
                open_price = row['Open']
                high_price = row['High']
                low_price = row['Low']
                close_price = row['Close']
                
                # Skip if price is outside Ross Cameron range ($2-$30)
                if not (2.0 <= open_price <= 30.0):
                    continue
                
                total_opportunities += 1
                
                # Simulate momentum scalp trade
                # Entry: Assume we got in at open + 1% (breakout entry)
                entry_price = open_price * 1.01
                
                # Stop: 2.5% below entry (Ross Cameron style tight stop)
                stop_price = entry_price * 0.975
                
                # Target: 5% above entry (conservative scalp target)
                target_price = entry_price * 1.05
                
                # Check if trade would have worked
                hit_stop = low_price <= stop_price
                hit_target = high_price >= target_price
                
                if hit_stop and hit_target:
                    # Both hit - depends on order, assume 50/50 chance
                    if np.random.random() > 0.5:
                        exit_price = target_price
                        successful = True
                    else:
                        exit_price = stop_price
                        successful = False
                elif hit_target:
                    exit_price = target_price
                    successful = True
                elif hit_stop:
                    exit_price = stop_price
                    successful = False
                else:
                    # Neither hit - close at market close
                    exit_price = close_price
                    successful = exit_price > entry_price
                
                # Calculate P&L (assume $150 risk per trade = 3% of $5K account)
                risk_per_share = entry_price - stop_price
                shares = int(150 / risk_per_share) if risk_per_share > 0 else 0
                
                if shares > 0:
                    pnl = (exit_price - entry_price) * shares
                    total_pnl += pnl
                    
                    if successful:
                        successful_trades += 1
                    
                    trade_details.append({
                        'date': date_idx.strftime('%Y-%m-%d'),
                        'ticker': ticker,
                        'gap_pct': round(gap_pct, 1),
                        'entry': round(entry_price, 2),
                        'exit': round(exit_price, 2),
                        'shares': shares,
                        'pnl': round(pnl, 2),
                        'successful': successful
                    })
                    
            print(f"  Found {len(momentum_days)} gap days for {ticker}")
            
        except Exception as e:
            print(f"  Error analyzing {ticker}: {e}")
            continue
    
    # Results summary
    print(f"\n{'='*60}")
    print(f"📈 MOMENTUM SCALP PERFORMANCE ESTIMATE")
    print(f"{'='*60}")
    print(f"🎯 Total Opportunities: {total_opportunities}")
    print(f"🏆 Successful Trades: {successful_trades}")
    print(f"📊 Success Rate: {(successful_trades/total_opportunities*100):.1f}%" if total_opportunities > 0 else "N/A")
    print(f"💰 Estimated Total P&L: ${total_pnl:.2f}")
    print(f"📈 Estimated Return: {(total_pnl/5000*100):.2f}% (on $5K account)")
    
    if trade_details:
        avg_win = np.mean([t['pnl'] for t in trade_details if t['successful']])
        avg_loss = np.mean([t['pnl'] for t in trade_details if not t['successful']])
        
        print(f"💵 Average Win: ${avg_win:.2f}")
        print(f"💸 Average Loss: ${avg_loss:.2f}")
        
        # Show best and worst trades
        best_trade = max(trade_details, key=lambda x: x['pnl'])
        worst_trade = min(trade_details, key=lambda x: x['pnl'])
        
        print(f"\n🚀 Best Trade: {best_trade['ticker']} ({best_trade['date']}) - ${best_trade['pnl']}")
        print(f"💀 Worst Trade: {worst_trade['ticker']} ({worst_trade['date']}) - ${worst_trade['pnl']}")
        
        # Monthly breakdown
        monthly_pnl = {}
        for trade in trade_details:
            month = trade['date'][:7]
            monthly_pnl[month] = monthly_pnl.get(month, 0) + trade['pnl']
        
        print(f"\n📅 Monthly P&L Estimate:")
        for month in sorted(monthly_pnl.keys()):
            print(f"  {month}: ${monthly_pnl[month]:.2f}")
        
        print(f"\n🔍 Recent Trades (Last 10):")
        for trade in trade_details[-10:]:
            status = "✅" if trade['successful'] else "❌"
            print(f"  {trade['date']} {trade['ticker']} {status}: ${trade['pnl']} (gap: {trade['gap_pct']}%)")

def analyze_specific_tickers():
    """Analyze specific tickers that are commonly used in momentum scalping"""
    print(f"\n{'='*60}")
    print(f"🎯 TICKER-SPECIFIC ANALYSIS")
    print(f"{'='*60}")
    
    # Focus on most active momentum names
    focus_tickers = ['TSLA', 'NVDA', 'AMD', 'COIN', 'MARA']
    
    end_date = date.today()
    start_date = end_date - timedelta(days=30)  # Last month
    
    for ticker in focus_tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date.strftime('%Y-%m-%d'), 
                                end=end_date.strftime('%Y-%m-%d'))
            
            if hist.empty:
                continue
            
            # Calculate daily volatility and gap frequency
            hist['daily_range'] = ((hist['High'] - hist['Low']) / hist['Open'] * 100)
            hist['gap_pct'] = ((hist['Open'] - hist['Close'].shift(1)) / hist['Close'].shift(1) * 100)
            
            avg_daily_range = hist['daily_range'].mean()
            gap_days = len(hist[abs(hist['gap_pct']) >= 4])
            
            print(f"📈 {ticker}:")
            print(f"  Average daily range: {avg_daily_range:.1f}%")
            print(f"  Gap days (4%+): {gap_days}/{len(hist)} ({gap_days/len(hist)*100:.0f}%)")
            print(f"  Current price: ${hist['Close'].iloc[-1]:.2f}")
            
        except Exception as e:
            print(f"Error analyzing {ticker}: {e}")

if __name__ == "__main__":
    analyze_momentum_performance()
    analyze_specific_tickers()