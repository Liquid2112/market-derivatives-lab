"""Polymarket adapter: fetch + normalize into the shared schema.

Read-only. Uses two public Polymarket services:

* Gamma API (``https://gamma-api.polymarket.com``) for market discovery and
  metadata. A Gamma market carries parallel ``outcomes`` / ``outcomePrices``
  arrays (JSON-encoded strings) and a ``clobTokenIds`` array that links each
  outcome to its CLOB order-book token.
* CLOB API (``https://clob.polymarket.com``) for the live order book of a
  single outcome token (``GET /book?token_id=...``).

The normalizers (``normalize_market``, ``normalize_order_book``) are pure
functions over already-parsed JSON so they can be unit-tested against saved
fixtures with no network access. Only GET requests are ever issued; this
module never places or signs an order.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from .schema import Market, OrderBook, PriceLevel, Provider, clamp_probability

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

_DEFAULT_TIMEOUT = 20.0


def _loads_maybe(value: Any) -> Any:
    """Gamma encodes list fields as JSON strings; decode those defensively.

    ``outcomes``, ``outcomePrices`` and ``clobTokenIds`` arrive as strings like
    ``'["Yes", "No"]'``. Already-decoded lists are returned unchanged.
    """
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


def _first_yes_index(outcomes: list[str]) -> int:
    """Index of the YES outcome, falling back to 0 for a non-labelled market."""
    for i, name in enumerate(outcomes):
        if str(name).strip().lower() == "yes":
            return i
    return 0


def normalize_order_book(
    raw: dict, *, timestamp: Optional[int] = None
) -> OrderBook:
    """Normalize a CLOB ``/book`` payload into an :class:`OrderBook`.

    The CLOB returns ``bids`` and ``asks`` as lists of ``{"price","size"}``
    objects with string values, for the YES outcome token. We sort bids
    best-first (descending price) and asks best-first (ascending price), since
    the raw order is not guaranteed.
    """
    bids = [
        PriceLevel(price=float(lvl["price"]), size=float(lvl["size"]))
        for lvl in raw.get("bids", [])
    ]
    asks = [
        PriceLevel(price=float(lvl["price"]), size=float(lvl["size"]))
        for lvl in raw.get("asks", [])
    ]
    bids.sort(key=lambda lvl: lvl.price, reverse=True)
    asks.sort(key=lambda lvl: lvl.price)

    ts = timestamp
    if ts is None and raw.get("timestamp") is not None:
        try:
            ts = int(raw["timestamp"])
        except (ValueError, TypeError):
            ts = None

    return OrderBook(bids=bids, asks=asks, timestamp=ts)


def normalize_market(
    raw: dict, *, order_book: Optional[OrderBook] = None
) -> Market:
    """Normalize a Gamma market object into a :class:`Market`.

    ``yes_price`` / ``no_price`` come from the parallel ``outcomes`` /
    ``outcomePrices`` arrays, selecting the YES outcome. When an order book is
    supplied (fetched separately from the CLOB) it is attached.
    """
    outcomes = _loads_maybe(raw.get("outcomes")) or []
    prices = _loads_maybe(raw.get("outcomePrices")) or []

    yes_price: Optional[float] = None
    no_price: Optional[float] = None
    if outcomes and len(prices) == len(outcomes):
        yes_i = _first_yes_index([str(o) for o in outcomes])
        no_i = 1 - yes_i if len(prices) == 2 else None
        try:
            yes_price = clamp_probability(float(prices[yes_i]))
        except (ValueError, TypeError, IndexError):
            yes_price = None
        if no_i is not None:
            try:
                no_price = clamp_probability(float(prices[no_i]))
            except (ValueError, TypeError, IndexError):
                no_price = None

    status = None
    if raw.get("closed") is True:
        status = "closed"
    elif raw.get("active") is True:
        status = "open"

    slug = raw.get("slug")
    url = f"https://polymarket.com/market/{slug}" if slug else None

    volume = None
    if raw.get("volumeNum") is not None:
        try:
            volume = float(raw["volumeNum"])
        except (ValueError, TypeError):
            volume = None

    return Market(
        provider=Provider.POLYMARKET,
        id=str(raw.get("id")),
        title=str(raw.get("question") or raw.get("title") or ""),
        yes_price=yes_price,
        no_price=no_price,
        order_book=order_book,
        status=status,
        close_time=raw.get("endDate"),
        volume=volume,
        url=url,
        raw=raw,
    )


def _yes_token_id(raw: dict) -> Optional[str]:
    """CLOB token id for the YES outcome of a Gamma market, if present."""
    outcomes = _loads_maybe(raw.get("outcomes")) or []
    token_ids = _loads_maybe(raw.get("clobTokenIds")) or []
    if not token_ids:
        return None
    yes_i = _first_yes_index([str(o) for o in outcomes]) if outcomes else 0
    if yes_i < len(token_ids):
        return str(token_ids[yes_i])
    return str(token_ids[0])


class PolymarketClient:
    """Read-only HTTP client for Polymarket Gamma + CLOB.

    Example:
        >>> client = PolymarketClient()
        >>> markets = client.list_markets(limit=5)   # doctest: +SKIP
        >>> book = client.get_order_book(markets[0].id)   # doctest: +SKIP
    """

    def __init__(
        self,
        gamma_base: str = GAMMA_BASE,
        clob_base: str = CLOB_BASE,
        timeout: float = _DEFAULT_TIMEOUT,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.gamma_base = gamma_base.rstrip("/")
        self.clob_base = clob_base.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "PolymarketClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def list_markets(
        self,
        *,
        limit: int = 20,
        search: Optional[str] = None,
        closed: Optional[bool] = False,
    ) -> list[Market]:
        """List or search open markets (metadata only, no order book).

        ``search`` filters by free text when supplied. ``closed=False`` (the
        default) restricts to markets that are still open.
        """
        params: dict[str, Any] = {"limit": limit}
        if closed is not None:
            params["closed"] = str(closed).lower()
        if search:
            params["_query"] = search
        resp = self._client.get(f"{self.gamma_base}/markets", params=params)
        resp.raise_for_status()
        data = resp.json()
        rows = data if isinstance(data, list) else data.get("data", [])
        return [normalize_market(row) for row in rows]

    def get_market(self, market_id: str) -> Market:
        """Fetch a single market's metadata by Gamma id (no order book)."""
        resp = self._client.get(f"{self.gamma_base}/markets/{market_id}")
        resp.raise_for_status()
        return normalize_market(resp.json())

    def get_order_book(self, market_id: str) -> OrderBook:
        """Fetch the live YES-outcome order book for a market id.

        Looks up the market's YES CLOB token, then reads ``/book`` from the
        CLOB. Raises ``ValueError`` if the market exposes no CLOB token.
        """
        resp = self._client.get(f"{self.gamma_base}/markets/{market_id}")
        resp.raise_for_status()
        token_id = _yes_token_id(resp.json())
        if not token_id:
            raise ValueError(f"market {market_id} has no CLOB token id")
        book_resp = self._client.get(
            f"{self.clob_base}/book", params={"token_id": token_id}
        )
        book_resp.raise_for_status()
        return normalize_order_book(book_resp.json())
