#!/usr/bin/env python3
"""
Account Safety Module for Schwab Trading Bots
Prevents margin calls, PDT violations, and oversized positions
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class AccountInfo:
    """Account balance and position information"""
    cash_available: float
    buying_power: float
    account_type: str  # "CASH" or "MARGIN"
    account_value: float
    positions_value: float = 0.0


class AccountSafetyManager:
    """
    Prevents dangerous trading scenarios:
    - Buying options you can't afford
    - Pattern Day Trader (PDT) violations
    - Exceeding daily loss limits
    - Position sizing beyond safe limits
    """

    def __init__(self,
                 max_position_cost_percent: float = 20.0,  # Max 20% of account per trade
                 max_daily_loss_dollars: float = 100.0,    # Stop if lose $100 in a day
                 max_daily_trades: int = 3,                # For PDT safety
                 cash_account_buffer: float = 50.0):       # Keep $50 cash buffer

        self.max_position_cost_percent = max_position_cost_percent
        self.max_daily_loss_dollars = max_daily_loss_dollars
        self.max_daily_trades = max_daily_trades
        self.cash_account_buffer = cash_account_buffer

        # Track today's activity
        self.daily_trades = 0
        self.daily_pnl = 0.0
        self.last_reset_date = datetime.now().date()

        # Track recent day trades (for PDT)
        self.day_trades: deque = deque(maxlen=100)  # Last 100 trades

    def reset_daily_counters(self):
        """Reset counters at start of new day"""
        today = datetime.now().date()
        if today != self.last_reset_date:
            logger.info(f"New trading day - resetting counters. Previous P&L: ${self.daily_pnl:.2f}")
            self.daily_trades = 0
            self.daily_pnl = 0.0
            self.last_reset_date = today

    def can_trade(self, account_info: AccountInfo, option_cost: float) -> Tuple[bool, str]:
        """
        Comprehensive safety check before placing a trade

        Returns:
            (can_trade: bool, reason: str)
        """
        self.reset_daily_counters()

        # Check 1: Account balance
        can_afford, reason = self._check_buying_power(account_info, option_cost)
        if not can_afford:
            return False, reason

        # Check 2: Position sizing
        too_large, reason = self._check_position_size(account_info, option_cost)
        if too_large:
            return False, reason

        # Check 3: Daily loss limit
        hit_loss_limit, reason = self._check_daily_loss_limit()
        if hit_loss_limit:
            return False, reason

        # Check 4: Pattern Day Trader protection
        pdt_violation, reason = self._check_pdt_limit(account_info)
        if pdt_violation:
            return False, reason

        return True, "All safety checks passed"

    def _check_buying_power(self, account_info: AccountInfo, option_cost: float) -> Tuple[bool, str]:
        """Check if account has enough cash to buy the option"""

        # For CASH accounts: need actual cash available
        if account_info.account_type == "CASH":
            required = option_cost * 100  # Options are per contract ($2.50 option = $250)
            available = account_info.cash_available - self.cash_account_buffer

            if required > available:
                return False, (f"Insufficient cash: need ${required:.2f}, "
                             f"have ${account_info.cash_available:.2f} "
                             f"(keeping ${self.cash_account_buffer} buffer)")

        # For MARGIN accounts: use buying power (but we're buying options, not using margin)
        else:
            required = option_cost * 100
            if required > account_info.buying_power:
                return False, (f"Insufficient buying power: need ${required:.2f}, "
                             f"have ${account_info.buying_power:.2f}")

        return True, "Sufficient funds"

    def _check_position_size(self, account_info: AccountInfo, option_cost: float) -> Tuple[bool, str]:
        """Ensure position isn't too large relative to account size"""

        position_cost = option_cost * 100  # $2.50 option = $250
        max_allowed = account_info.account_value * (self.max_position_cost_percent / 100)

        if position_cost > max_allowed:
            return True, (f"Position too large: ${position_cost:.2f} exceeds "
                         f"{self.max_position_cost_percent}% of account "
                         f"(${max_allowed:.2f} max)")

        return False, "Position size OK"

    def _check_daily_loss_limit(self) -> Tuple[bool, str]:
        """Check if daily loss limit has been hit"""

        if self.daily_pnl <= -self.max_daily_loss_dollars:
            return True, (f"Daily loss limit hit: ${self.daily_pnl:.2f} "
                         f"(limit: ${self.max_daily_loss_dollars})")

        return False, "Daily loss OK"

    def _check_pdt_limit(self, account_info: AccountInfo) -> Tuple[bool, str]:
        """
        Pattern Day Trader protection

        PDT Rule: If account < $25k, limited to 3 day trades per 5 trading days
        """

        # PDT only applies to margin accounts under $25k
        if account_info.account_type == "MARGIN" and account_info.account_value < 25000:
            # Count day trades in last 5 trading days
            five_days_ago = datetime.now() - timedelta(days=5)
            recent_day_trades = [dt for dt in self.day_trades if dt > five_days_ago]

            if len(recent_day_trades) >= 3:
                return True, (f"PDT limit reached: {len(recent_day_trades)} day trades "
                            f"in last 5 days (limit: 3). Wait {(recent_day_trades[0] - five_days_ago).days} days.")

        # For CASH accounts: warn about trade frequency
        if account_info.account_type == "CASH":
            if self.daily_trades >= self.max_daily_trades:
                return True, (f"Cash account trade limit: {self.daily_trades} trades today "
                            f"(limit: {self.max_daily_trades}). Cash may not be settled.")

        return False, "PDT check OK"

    def record_trade(self, entry_time: datetime, exit_time: datetime, pnl: float):
        """
        Record a completed trade for tracking

        Args:
            entry_time: When position was opened
            exit_time: When position was closed
            pnl: Profit/loss in dollars
        """
        self.reset_daily_counters()

        self.daily_trades += 1
        self.daily_pnl += pnl

        # If entry and exit on same day = day trade
        if entry_time.date() == exit_time.date():
            self.day_trades.append(exit_time)
            logger.info(f"Day trade recorded. Total in last 5 days: {len(self.day_trades)}")

        logger.info(f"Trade recorded: P&L ${pnl:.2f} | Daily total: ${self.daily_pnl:.2f} | Trades today: {self.daily_trades}")

    def get_max_contracts_allowed(self, account_info: AccountInfo, option_cost: float) -> int:
        """
        Calculate maximum number of contracts that can be safely traded

        Args:
            account_info: Current account state
            option_cost: Cost per option contract (e.g., $2.50)

        Returns:
            Maximum number of contracts (0 if can't afford any)
        """
        # Cost per contract
        cost_per_contract = option_cost * 100  # $2.50 = $250

        # Available funds
        if account_info.account_type == "CASH":
            available = account_info.cash_available - self.cash_account_buffer
        else:
            available = account_info.buying_power

        # Max based on funds
        max_by_funds = int(available / cost_per_contract)

        # Max based on position sizing rule
        max_position_value = account_info.account_value * (self.max_position_cost_percent / 100)
        max_by_sizing = int(max_position_value / cost_per_contract)

        # Return the smaller
        max_allowed = min(max_by_funds, max_by_sizing)

        logger.debug(f"Max contracts: by_funds={max_by_funds}, by_sizing={max_by_sizing}, allowed={max_allowed}")

        return max(0, max_allowed)

    def get_safety_status(self) -> dict:
        """Get current safety manager status"""
        return {
            "daily_trades": self.daily_trades,
            "daily_pnl": self.daily_pnl,
            "day_trades_last_5_days": len(self.day_trades),
            "max_daily_trades": self.max_daily_trades,
            "max_daily_loss": self.max_daily_loss_dollars,
            "date": self.last_reset_date.isoformat()
        }


# Example usage
if __name__ == "__main__":
    # Simulate a $700 cash account
    safety = AccountSafetyManager(
        max_position_cost_percent=25.0,  # Max 25% of account ($175)
        max_daily_loss_dollars=100.0,    # Stop at -$100/day
        max_daily_trades=2,              # Only 2 trades/day for cash account
        cash_account_buffer=50.0         # Keep $50 buffer
    )

    account = AccountInfo(
        cash_available=700.0,
        buying_power=700.0,
        account_type="CASH",
        account_value=700.0
    )

    # Try to buy a $2.50 option ($250 cost)
    option_cost = 2.50

    print("="*60)
    print(f"Account: ${account.cash_available} cash ({account.account_type})")
    print(f"Option cost: ${option_cost} (${option_cost * 100} total)")
    print("="*60)

    can_trade, reason = safety.can_trade(account, option_cost)
    print(f"\nCan trade? {can_trade}")
    print(f"Reason: {reason}")

    if can_trade:
        max_contracts = safety.get_max_contracts_allowed(account, option_cost)
        print(f"\nMax contracts allowed: {max_contracts}")
        print(f"Total cost: ${max_contracts * option_cost * 100:.2f}")

    # Simulate some trades
    print("\n" + "="*60)
    print("Simulating trades...")
    print("="*60)

    # Trade 1: Win $45
    safety.record_trade(
        entry_time=datetime.now(),
        exit_time=datetime.now(),
        pnl=45.0
    )

    # Trade 2: Loss $35
    safety.record_trade(
        entry_time=datetime.now(),
        exit_time=datetime.now(),
        pnl=-35.0
    )

    # Try trade 3
    can_trade, reason = safety.can_trade(account, option_cost)
    print(f"\nAfter 2 trades, can trade? {can_trade}")
    print(f"Reason: {reason}")

    print("\n" + "="*60)
    print("Safety Status:")
    print("="*60)
    status = safety.get_safety_status()
    for key, value in status.items():
        print(f"  {key}: {value}")
