"""Pytest path setup.

The March 2026 reorganisation moved modules into ``core/`` and ``bots/*/`` but
left every import flat (``from schwab_account_safety import ...``). There is no
package, no ``__init__.py`` and no installed distribution, so under pytest's
default ``prepend`` import mode only ``tests/`` lands on ``sys.path`` and every
test module fails at collection with ``ModuleNotFoundError``.

This file puts the source directories back on ``sys.path`` for test runs only.
It does NOT fix the bots' own runtime imports -- running a bot directly still
fails the same way. That is a separate, larger repair.
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

for _rel in (
    "core",
    "bots/momentum_scalp",
    "bots/schwab_0dte",
    "bots/tradovate",
):
    _path = os.path.join(ROOT, _rel)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)
