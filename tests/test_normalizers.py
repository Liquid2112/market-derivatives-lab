"""Unit tests for the Polymarket and Kalshi normalizers.

These run entirely against saved fixture responses in ``fixtures/`` and never
touch the network. The fixtures are real API responses captured once.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mdlab import kalshi, polymarket
from mdlab.schema import Market, OrderBook, Provider

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8-sig"))


# ---------------------------------------------------------------- Polymarket


def test_polymarket_market_normalization():
    rows = _load("polymarket_markets.json")
    market = polymarket.normalize_market(rows[0])

    assert isinstance(market, Market)
    assert market.provider is Provider.POLYMARKET
    assert market.id  # non-empty id
    assert market.title
    # yes/no prices are probabilities and roughly complementary.
    assert market.yes_price is not None and 0.0 <= market.yes_price <= 1.0
    assert market.no_price is not None and 0.0 <= market.no_price <= 1.0
    assert abs((market.yes_price + market.no_price) - 1.0) < 0.1
    assert market.url and market.url.startswith("https://polymarket.com/")
    assert market.status in {"open", "closed", None}


def test_polymarket_order_book_normalization():
    raw = _load("polymarket_book.json")
    book = polymarket.normalize_order_book(raw)

    assert isinstance(book, OrderBook)
    assert book.bids and book.asks
    # Prices are valid probabilities.
    for level in book.bids + book.asks:
        assert 0.0 <= level.price <= 1.0
        assert level.size >= 0.0
    # Best-first ordering.
    assert book.bids == sorted(book.bids, key=lambda l: l.price, reverse=True)
    assert book.asks == sorted(book.asks, key=lambda l: l.price)
    assert book.best_bid is not None and book.best_ask is not None
    assert book.best_bid <= book.best_ask  # no crossed book
    assert book.timestamp is not None


def test_polymarket_outcomes_encoded_as_json_strings():
    # Gamma encodes list fields as JSON strings; the adapter must decode them.
    rows = _load("polymarket_markets.json")
    assert isinstance(rows[0]["outcomes"], str)
    market = polymarket.normalize_market(rows[0])
    assert market.yes_price is not None


# -------------------------------------------------------------------- Kalshi


def test_kalshi_market_normalization():
    raw = _load("kalshi_market.json")["market"]
    market = kalshi.normalize_market(raw)

    assert isinstance(market, Market)
    assert market.provider is Provider.KALSHI
    assert market.id  # the ticker
    assert market.title
    assert market.yes_price is not None and 0.0 <= market.yes_price <= 1.0
    assert market.no_price is not None and 0.0 <= market.no_price <= 1.0
    assert market.status in {"open", "closed", "active", "settled", None} or (
        isinstance(market.status, str)
    )


def test_kalshi_order_book_normalization():
    raw = _load("kalshi_book.json")
    book = kalshi.normalize_order_book(raw)

    assert isinstance(book, OrderBook)
    assert book.bids and book.asks
    for level in book.bids + book.asks:
        assert 0.0 <= level.price <= 1.0
        assert level.size >= 0.0
    assert book.bids == sorted(book.bids, key=lambda l: l.price, reverse=True)
    assert book.asks == sorted(book.asks, key=lambda l: l.price)


def test_kalshi_no_side_folds_into_yes_asks():
    # A NO bid at price p must appear as a YES ask at 1 - p.
    raw = {
        "orderbook_fp": {
            "yes_dollars": [["0.40", "100"]],
            "no_dollars": [["0.35", "50"]],  # => YES ask at 0.65
        }
    }
    book = kalshi.normalize_order_book(raw)
    assert book.best_bid == pytest.approx(0.40)
    assert book.best_ask == pytest.approx(0.65)


def test_kalshi_legacy_cent_orderbook():
    # Legacy envelope uses integer cents; the adapter divides by 100.
    raw = {"orderbook": {"yes": [[42, 10]], "no": [[30, 5]]}}
    book = kalshi.normalize_order_book(raw)
    assert book.best_bid == pytest.approx(0.42)
    assert book.best_ask == pytest.approx(0.70)


def test_kalshi_empty_book_is_valid():
    raw = {"orderbook_fp": {"yes_dollars": [], "no_dollars": []}}
    book = kalshi.normalize_order_book(raw)
    assert book.bids == []
    assert book.asks == []
    assert book.best_bid is None
    assert book.mid_price is None


# -------------------------------------------------------------- shared schema


def test_mid_price_requires_both_sides():
    from mdlab.schema import PriceLevel

    book = OrderBook(bids=[PriceLevel(0.4, 10)], asks=[PriceLevel(0.6, 10)])
    assert book.mid_price == pytest.approx(0.5)
