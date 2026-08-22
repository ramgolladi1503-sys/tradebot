"""TradeBot Execution Platform kernel contracts.

M1 is deliberately pure: no filesystem, network, broker, GitHub, process, or durable-state mutation.
"""

from .kernel import *  # noqa: F401,F403
