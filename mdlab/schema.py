"""Shared, provider-neutral data schema for prediction markets.

This module is the integration contract that the rest of the tool is built on.
Both the Polymarket and the Kalshi adapters normalize their raw API responses
into these types, so downstream code (pricing models, the web API, the UI)
only ever sees :class:`Market`, :class:`OrderBook` and :class:`PriceLevel`,
never a provider-specific payload.

Design rules for this schema:

* Prices are probabilities in the closed interval ``[0.0, 1.0]`` (a YES price
  of ``0.62`` means the market implies a 62% chance of the YES outcome). This
  matches Polymarket's native 0..1 pricing and is the natural unit for the
  implied-probability and option models built on top of this layer.
* An :class:`OrderBook` is always expressed from the point of view of the YES
  outcome: ``bids`` are resting buy orders for YES, ``asks`` are resting sell
  orders for YES, each sorted best-price-first (bids descending, asks
  ascending).
* All monetary/size values are plain ``float``. Providers return them as
  strings or integer cents; the adapters are responsible for the conversion.

Everything here is a frozen, typed dataclass. There is no I/O and no network
access in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Provider(str, Enum):
    """Supported market-data providers."""

    POLYMARKET = "polymarket"
    KALSHI = "kalshi"


@dataclass(frozen=True)
class PriceLevel:
    """A single resting level in an order book.

    Attributes:
        price: Probability price in ``[0.0, 1.0]``.
        size:  Quantity of contracts/shares resting at ``price`` (>= 0).
    """

    price: float
    size: float


@dataclass(frozen=True)
class OrderBook:
    """A YES-outcome order book, best price first.

    ``bids`` are sorted by descending price (best bid first); ``asks`` are
    sorted by ascending price (best ask first). Either side may be empty,
    which is a normal state for a market that has no resting liquidity.

    Attributes:
        bids:      Resting buy orders for the YES outcome.
        asks:      Resting sell orders for the YES outcome.
        timestamp: Provider-reported book timestamp in epoch milliseconds,
                   or ``None`` if the provider did not supply one.
    """

    bids: list[PriceLevel] = field(default_factory=list)
    asks: list[PriceLevel] = field(default_factory=list)
    timestamp: Optional[int] = None

    @property
    def best_bid(self) -> Optional[float]:
        """Highest YES bid price, or ``None`` when there are no bids."""
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        """Lowest YES ask price, or ``None`` when there are no asks."""
        return self.asks[0].price if self.asks else None

    @property
    def mid_price(self) -> Optional[float]:
        """Midpoint of best bid and best ask, or ``None`` if a side is empty."""
        if self.bids and self.asks:
            return (self.bids[0].price + self.asks[0].price) / 2.0
        return None


@dataclass(frozen=True)
class Market:
    """A single normalized prediction market.

    This is the unit every downstream consumer works with. ``yes_price`` and
    ``no_price`` are the headline probabilities (typically the provider's last
    trade or midpoint), while ``order_book`` carries the full depth when it has
    been fetched.

    Attributes:
        provider:    Which provider this market came from.
        id:          Provider-native stable identifier (Polymarket market id,
                     Kalshi ticker). Unique within a provider.
        title:       Human-readable market question.
        yes_price:   Implied probability of YES in ``[0.0, 1.0]``.
        no_price:    Implied probability of NO in ``[0.0, 1.0]`` (normally
                     ``~= 1 - yes_price``).
        order_book:  Full YES-outcome order book, or ``None`` when only
                     metadata was fetched.
        status:      Provider-reported lifecycle status (e.g. ``"open"``,
                     ``"closed"``), lower-cased, or ``None`` if unknown.
        close_time:  ISO-8601 close/expiration time string, or ``None``.
        volume:      Reported traded volume, or ``None`` if unavailable.
        url:         Canonical web URL for the market, or ``None``.
        raw:         The untouched provider payload, for debugging and for
                     fields this schema does not model. Never relied on by
                     downstream consumers.
    """

    provider: Provider
    id: str
    title: str
    yes_price: Optional[float]
    no_price: Optional[float]
    order_book: Optional[OrderBook] = None
    status: Optional[str] = None
    close_time: Optional[str] = None
    volume: Optional[float] = None
    url: Optional[str] = None
    raw: Optional[dict] = None


def clamp_probability(value: Optional[float]) -> Optional[float]:
    """Clamp a price into the ``[0.0, 1.0]`` probability interval.

    Returns ``None`` unchanged so callers can distinguish "no price" from a
    real ``0.0``. Values slightly outside the range (floating-point noise from
    a provider) are pulled back to the nearest bound.
    """
    if value is None:
        return None
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value
