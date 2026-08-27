"""Real assertions for AccountSafetyManager.

WHAT THIS REPLACED
------------------
The previous version of this file contained **zero assert statements**. It
constructed a safety manager, printed results with tick marks, and ended with
unconditional ``print()`` calls reading:

    ✅ Safety module is working correctly!
       ✅ Position size limits enforced
       ✅ Daily loss limits enforced

Those lines were output, not checks. Under pytest both functions would be
collected and would pass no matter what the safety layer returned -- including
if ``can_trade`` had returned True for every input. A file that reports the
safety layer is verified while verifying nothing is worse than no test at all,
because it stops anyone from writing the real one. The original is preserved
alongside this file as ``test_safety_integration.py.orig``.

Every test below fails if the guard it names stops working.

Pure stdlib plus pytest: no network, no broker, no credentials.
"""

from datetime import datetime, timedelta

import pytest

from schwab_account_safety import AccountInfo, AccountSafetyManager


# --------------------------------------------------------------------------
# Account builders
# --------------------------------------------------------------------------

def cash_account(cash=700.0, value=700.0):
    return AccountInfo(
        cash_available=cash,
        buying_power=cash,
        account_type="CASH",
        account_value=value,
    )


def margin_account(buying_power=3000.0, value=3000.0):
    return AccountInfo(
        cash_available=buying_power,
        buying_power=buying_power,
        account_type="MARGIN",
        account_value=value,
    )


@pytest.fixture
def mgr():
    # Explicit limits so these tests do not silently follow a changed default.
    return AccountSafetyManager(
        max_position_cost_percent=20.0,
        max_daily_loss_dollars=100.0,
        max_daily_trades=3,
        cash_account_buffer=50.0,
    )


# --------------------------------------------------------------------------
# Buying power
# --------------------------------------------------------------------------

def test_cash_account_blocks_unaffordable_contract(mgr):
    """$700 cash less a $50 buffer is $650 usable; a $7.00 option costs $700."""
    ok, reason = mgr.can_trade(cash_account(cash=700.0), option_cost=7.00)
    assert ok is False
    assert "Insufficient cash" in reason


def test_cash_account_respects_the_buffer(mgr):
    """$6.60 x 100 = $660 > $650 usable. Affordable only if the buffer is ignored."""
    ok, _ = mgr.can_trade(cash_account(cash=700.0), option_cost=6.60)
    assert ok is False, "cash buffer was not subtracted from available funds"


def test_margin_account_blocks_beyond_buying_power(mgr):
    acct = margin_account(buying_power=100.0, value=30000.0)
    ok, reason = mgr.can_trade(acct, option_cost=5.00)
    assert ok is False
    assert "Insufficient buying power" in reason


# --------------------------------------------------------------------------
# Position sizing
# --------------------------------------------------------------------------

def test_position_size_cap_blocks_oversized_trade(mgr):
    """20% of a $3000 account is $600; a $7.00 option costs $700."""
    acct = margin_account(buying_power=10000.0, value=3000.0)
    ok, reason = mgr.can_trade(acct, option_cost=7.00)
    assert ok is False
    assert "Position too large" in reason


def test_position_size_cap_allows_trade_inside_the_limit(mgr):
    """$5.00 x 100 = $500, inside the $600 cap and affordable."""
    acct = margin_account(buying_power=10000.0, value=3000.0)
    ok, reason = mgr.can_trade(acct, option_cost=5.00)
    assert ok is True, reason


# --------------------------------------------------------------------------
# Daily loss limit
# --------------------------------------------------------------------------

def test_daily_loss_limit_blocks_further_trades(mgr):
    acct = margin_account(buying_power=10000.0, value=30000.0)
    assert mgr.can_trade(acct, option_cost=1.00)[0] is True

    now = datetime.now()
    mgr.record_trade(entry_time=now, exit_time=now, pnl=-100.0)

    ok, reason = mgr.can_trade(acct, option_cost=1.00)
    assert ok is False
    assert "Daily loss limit" in reason


def test_daily_loss_limit_not_tripped_by_smaller_loss(mgr):
    acct = margin_account(buying_power=10000.0, value=30000.0)
    now = datetime.now()
    mgr.record_trade(entry_time=now, exit_time=now, pnl=-99.0)
    assert mgr.can_trade(acct, option_cost=1.00)[0] is True


def test_record_trade_accumulates_pnl_and_count(mgr):
    now = datetime.now()
    mgr.record_trade(entry_time=now, exit_time=now, pnl=-40.0)
    mgr.record_trade(entry_time=now, exit_time=now, pnl=-40.0)
    assert mgr.daily_pnl == pytest.approx(-80.0)
    assert mgr.daily_trades == 2


# --------------------------------------------------------------------------
# PDT / trade-frequency limits
# --------------------------------------------------------------------------

def test_cash_account_daily_trade_cap(mgr):
    acct = cash_account(cash=10000.0, value=10000.0)
    now = datetime.now()
    for _ in range(3):
        mgr.record_trade(entry_time=now, exit_time=now, pnl=1.0)

    ok, reason = mgr.can_trade(acct, option_cost=1.00)
    assert ok is False
    assert "trade limit" in reason


def test_pdt_blocks_fourth_day_trade_on_small_margin_account(mgr):
    """PDT applies to margin accounts under $25k: 3 day trades per 5 days."""
    acct = margin_account(buying_power=10000.0, value=10000.0)
    now = datetime.now()
    for _ in range(3):
        mgr.record_trade(entry_time=now, exit_time=now, pnl=1.0)

    ok, reason = mgr.can_trade(acct, option_cost=1.00)
    assert ok is False
    assert "PDT limit" in reason


def test_pdt_does_not_apply_above_25k(mgr):
    acct = margin_account(buying_power=100000.0, value=30000.0)
    now = datetime.now()
    for _ in range(5):
        mgr.record_trade(entry_time=now, exit_time=now, pnl=1.0)

    assert mgr.can_trade(acct, option_cost=1.00)[0] is True


def test_overnight_trade_is_not_counted_as_a_day_trade(mgr):
    now = datetime.now()
    mgr.record_trade(entry_time=now - timedelta(days=1), exit_time=now, pnl=1.0)
    assert len(mgr.day_trades) == 0


# --------------------------------------------------------------------------
# Contract sizing
# --------------------------------------------------------------------------

def test_max_contracts_is_limited_by_the_sizing_rule(mgr):
    """$3000 account: funds allow 20 contracts at $1.00, sizing caps it at 6."""
    acct = margin_account(buying_power=2000.0, value=3000.0)
    assert mgr.get_max_contracts_allowed(acct, option_cost=1.00) == 6


def test_max_contracts_is_never_negative(mgr):
    acct = cash_account(cash=10.0, value=10.0)
    assert mgr.get_max_contracts_allowed(acct, option_cost=5.00) == 0


# --------------------------------------------------------------------------
# Guard the inverted-return trap
# --------------------------------------------------------------------------

def test_helper_return_conventions_are_inverted_and_can_trade_handles_it(mgr):
    """Pins down a real trap in this module.

    ``_check_buying_power`` returns True meaning *OK*. The other three
    (``_check_position_size``, ``_check_daily_loss_limit``,
    ``_check_pdt_limit``) return True meaning *BLOCKED* -- the opposite.

    ``can_trade`` reads each one correctly today, so there is no live bug. But
    any new caller using these helpers directly will get it backwards, and
    "tidying" one helper to match the others would silently invert a guard.
    This test fails if either convention moves without the other.
    """
    rich = margin_account(buying_power=100000.0, value=100000.0)

    # True means OK
    assert mgr._check_buying_power(rich, 1.00)[0] is True
    poor = margin_account(buying_power=1.0, value=100000.0)
    assert mgr._check_buying_power(poor, 5.00)[0] is False

    # True means BLOCKED
    assert mgr._check_position_size(rich, 1.00)[0] is False
    tiny = margin_account(buying_power=100000.0, value=100.0)
    assert mgr._check_position_size(tiny, 5.00)[0] is True
    assert mgr._check_daily_loss_limit()[0] is False
    assert mgr._check_pdt_limit(rich)[0] is False
