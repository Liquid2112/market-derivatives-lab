# market-derivatives-lab

A **read-only** analytics tool for prediction markets. It pulls any market from
**Polymarket** and **Kalshi**, reads live prices and order flow, and (in later
layers) models synthetic options and derivatives on top of them: payoff curves,
break-even, implied probability, and option Greeks.

There is no trading and no order placement anywhere in this project. It only
fetches, models, and visualizes. Every network call is a `GET`.

This repository currently contains the **data layer**: the part that fetches
markets and order books from both providers and normalizes them into one shared
schema. The pricing/derivative models and the web UI are built on top of this
layer.

## What's here

```
mdlab/
  schema.py       shared, typed data contract (Market, OrderBook, PriceLevel)
  polymarket.py   Gamma + CLOB adapter: fetch + normalize
  kalshi.py       public market-data adapter: fetch + normalize
fixtures/         real captured API responses used by the tests
tests/            unit tests over the fixtures (no network)
SCHEMA.md         the shared schema, documented, with an example
```

## The shared schema

Both providers normalize into one set of types so downstream code never sees a
provider-specific payload. A `Market` carries `provider`, `id`, `title`,
`yes_price`, `no_price` (probabilities in `[0.0, 1.0]`), and an `order_book` of
bid/ask `PriceLevel`s. The order book is always expressed from the YES
outcome's point of view. Full details and an example are in
[SCHEMA.md](SCHEMA.md).

## Providers

- **Polymarket** — market discovery and metadata from the Gamma API
  (`https://gamma-api.polymarket.com`); live order books from the CLOB API
  (`https://clob.polymarket.com/book`). Read-only GET only.
- **Kalshi** — public trade-api v2 market data
  (`https://api.elections.kalshi.com/trade-api/v2`). The default path is
  unauthenticated; an optional API key can be supplied to `KalshiClient` for
  authenticated access, but no credentials are needed for public reads.

## Usage

```python
from mdlab.polymarket import PolymarketClient
from mdlab.kalshi import KalshiClient

with PolymarketClient() as pm:
    markets = pm.list_markets(limit=5)          # discovery / search
    market = pm.get_market(markets[0].id)       # single market metadata
    book = pm.get_order_book(markets[0].id)     # live order book

with KalshiClient() as k:                        # optional: KalshiClient(api_key=...)
    markets = k.list_markets(limit=5, search="fed")
    book = k.get_order_book(markets[0].id)
```

Both clients return the same `Market` / `OrderBook` types, so a consumer can
treat Polymarket and Kalshi identically.

## Install

```bash
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

## Tests

The normalizers are unit-tested against saved real API responses in
`fixtures/`. Tests never hit the network.

```bash
python -m pytest -q
```

CI (GitHub Actions) installs dependencies and runs the suite on every push and
pull request.

## License

MIT.
