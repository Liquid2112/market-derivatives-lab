"""market-derivatives-lab data layer.

Read-only fetch + normalization of prediction markets from Polymarket and
Kalshi into one shared schema. See :mod:`mdlab.schema` for the contract.
"""

from .schema import (
    Market,
    OrderBook,
    PriceLevel,
    Provider,
    clamp_probability,
)

__all__ = [
    "Market",
    "OrderBook",
    "PriceLevel",
    "Provider",
    "clamp_probability",
    "__version__",
]

__version__ = "0.1.0"
