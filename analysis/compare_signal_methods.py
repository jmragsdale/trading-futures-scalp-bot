#!/usr/bin/env python3
"""
Comparison tool to understand dollar-based vs percentage-based signals

Shows why percentage-based is better for multi-ticker trading
"""

def compare_signals():
    """Compare how signals work across different price levels"""

    stocks = [
        ("AMD", 120.00),
        ("AAPL", 185.00),
        ("MSFT", 420.00),
        ("SPY", 580.00),
        ("NVDA", 725.00),
        ("GOOGL", 165.00),
        ("AMZN", 185.00),
        ("META", 580.00),
        ("TSLA", 245.00)
    ]

    print("\n" + "="*90)
    print("DOLLAR-BASED SIGNALS (SPY Bot Method)")
    print("="*90)
    print("\nFixed threshold: $0.20 move")
    print(f"\n{'Stock':<8} {'Price':<10} {'$0.20 Move':<15} {'As %':<10} {'Relative Sensitivity'}")
    print("-"*90)

    spy_pct = (0.20 / 580.00) * 100

    for symbol, price in sorted(stocks, key=lambda x: x[1]):
        pct_move = (0.20 / price) * 100
        relative = pct_move / spy_pct
        sensitivity = "🔴 Less sensitive" if relative < 0.8 else "🟢 More sensitive" if relative > 1.2 else "⚪ Similar"
        print(f"{symbol:<8} ${price:<9.2f} $0.20 = {pct_move:.3f}%   {pct_move:.3f}%    {relative:.2f}x SPY  {sensitivity}")

    print("\n⚠️  PROBLEM: Same dollar move means different things at different price levels")
    print("   - Low-priced stocks (AMD $120) are 2.8x MORE sensitive than NVDA ($725)")
    print("   - Signals favor cheaper stocks, which may not be the best opportunities")

    print("\n\n" + "="*90)
    print("PERCENTAGE-BASED SIGNALS (Volatile Stocks Bot Method)")
    print("="*90)
    print("\nFixed threshold: 0.40% move")
    print(f"\n{'Stock':<8} {'Price':<10} {'0.40% Move':<15} {'As $':<10} {'Relative Sensitivity'}")
    print("-"*90)

    for symbol, price in sorted(stocks, key=lambda x: x[1]):
        dollar_move = price * 0.0040
        print(f"{symbol:<8} ${price:<9.2f} 0.40% = ${dollar_move:<7.2f}  ${dollar_move:<9.2f} 1.00x  ✅ Normalized")

    print("\n✅ ADVANTAGE: Same percentage move at any price level")
    print("   - All stocks treated equally regardless of price")
    print("   - Captures relative momentum, not absolute dollar changes")
    print("   - Best stock selected by volatility, not price level")

    print("\n\n" + "="*90)
    print("REAL-WORLD EXAMPLE: Market Rally")
    print("="*90)

    print("\nScenario: Tech sector rallies, all stocks move together")
    print("\nWith DOLLAR-based ($0.20 threshold):")
    moves = [
        ("AMD", 120.00, 0.25, (0.25/120)*100),
        ("NVDA", 725.00, 1.50, (1.50/725)*100),
    ]

    for symbol, price, dollar_move, pct in moves:
        signal = "✅ SIGNAL!" if dollar_move >= 0.20 else "❌ No signal"
        print(f"  {symbol}: ${price:.2f} moves ${dollar_move:.2f} ({pct:.2f}%) → {signal}")

    print("\n  Result: AMD triggers (only moved 0.21%) but NVDA doesn't (moved 0.21% too)")
    print("  This is WRONG - they had the same relative momentum!")

    print("\n\nWith PERCENTAGE-based (0.40% threshold):")
    for symbol, price, dollar_move, pct in moves:
        signal = "❌ No signal" if pct < 0.40 else "✅ SIGNAL!"
        print(f"  {symbol}: ${price:.2f} moves ${dollar_move:.2f} ({pct:.2f}%) → {signal}")

    print("\n  Result: Neither triggers because 0.21% < 0.40% threshold")
    print("  This is CORRECT - both had weak momentum relative to their volatility")

    print("\n\n" + "="*90)
    print("CONCLUSION")
    print("="*90)
    print("\n✅ Use PERCENTAGE-BASED for:")
    print("   - Trading multiple stocks at different price levels")
    print("   - Normalizing signals across all tickers")
    print("   - Fair comparison of momentum strength")
    print("   - Dynamic ticker selection")

    print("\n✅ Use DOLLAR-BASED for:")
    print("   - Trading a SINGLE ticker (SPY)")
    print("   - When absolute price moves matter more than relative")
    print("   - Simpler mental model (\"SPY moved 50 cents\")")

    print("\n" + "="*90)
    print()


def show_signal_frequency():
    """Estimate signal frequency for different thresholds"""

    print("\n" + "="*70)
    print("ESTIMATED SIGNAL FREQUENCY")
    print("="*70)

    configs = [
        # (threshold_pct, time_window, expected_signals_per_day)
        (0.25, 20, "15-30 (very frequent)"),
        (0.30, 20, "10-20 (frequent)"),
        (0.40, 20, "5-10 (moderate)"),
        (0.50, 20, "3-7 (conservative)"),
        (0.60, 15, "1-3 (rare, high quality)"),
    ]

    print(f"\n{'Threshold':<12} {'Window':<10} {'Est. Signals/Day':<25} {'Risk Level'}")
    print("-"*70)

    for threshold, window, signals in configs:
        if "very frequent" in signals or "frequent" in signals:
            risk = "🔴 High (overtrading)"
        elif "moderate" in signals:
            risk = "🟡 Moderate (balanced)"
        else:
            risk = "🟢 Low (selective)"

        print(f"{threshold}%{'':<9} {window}s{'':<7} {signals:<25} {risk}")

    print("\n💡 RECOMMENDATION:")
    print("   Start with 0.40% / 20s for moderate signal frequency")
    print("   Adjust based on results:")
    print("   - Too many false signals → increase threshold to 0.50%")
    print("   - Too few opportunities → decrease to 0.30%")
    print("\n" + "="*70)
    print()


if __name__ == "__main__":
    compare_signals()
    show_signal_frequency()
