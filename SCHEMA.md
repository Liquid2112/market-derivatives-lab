# Shared market schema

Both providers normalize into the types in [`mdlab/schema.py`](mdlab/schema.py).
This is the contract the rest of the tool is built on: pricing models, the web
API, and the UI only ever see these types, never a provider-specific payload.

## Types

### `Market`

| Field        | Type                 | Notes |
|--------------|----------------------|-------|
| `provider`   | `Provider` enum      | `"polymarket"` or `"kalshi"` |
| `id`         | `str`                | Provider-native id. Polymarket market id, Kalshi ticker. Unique within a provider. |
| `title`      | `str`                | Human-readable market question. |
| `yes_price`  | `float` \| `None`    | Implied probability of YES in `[0.0, 1.0]`. |
| `no_price`   | `float` \| `None`    | Implied probability of NO in `[0.0, 1.0]` (normally `~= 1 - yes_price`). |
| `order_book` | `OrderBook` \| `None`| Full YES-outcome book, or `None` when only metadata was fetched. |
| `status`     | `str` \| `None`      | Lower-cased lifecycle status, e.g. `"open"`, `"closed"`. |
| `close_time` | `str` \| `None`      | ISO-8601 close/expiration time. |
| `volume`     | `float` \| `None`    | Reported traded volume. |
| `url`        | `str` \| `None`      | Canonical web URL for the market. |
| `raw`        | `dict` \| `None`     | Untouched provider payload, for debugging only. Downstream code must not depend on it. |

### `OrderBook`

Always expressed from the YES outcome's point of view.

| Field       | Type               | Notes |
|-------------|--------------------|-------|
| `bids`      | `list[PriceLevel]` | Resting YES buy orders, sorted by **descending** price (best bid first). |
| `asks`      | `list[PriceLevel]` | Resting YES sell orders, sorted by **ascending** price (best ask first). |
| `timestamp` | `int` \| `None`    | Provider book timestamp in epoch **milliseconds**. |

Derived read-only properties: `best_bid`, `best_ask`, `mid_price` (all return
`None` when the relevant side is empty).

### `PriceLevel`

| Field   | Type    | Notes |
|---------|---------|-------|
| `price` | `float` | Probability price in `[0.0, 1.0]`. |
| `size`  | `float` | Contracts/shares resting at `price` (>= 0). |

## Conventions

- **Prices are probabilities in `[0.0, 1.0]`.** A YES price of `0.62` means a
  62% implied chance. This matches Polymarket's native pricing and is the unit
  the derivative models consume.
- **The order book is YES-only.** Kalshi returns a two-sided book where both
  sides are bids (YES bids and NO bids). The Kalshi adapter folds NO bids into
  YES asks at `1 - price`, so every `OrderBook` reads the same way regardless
  of provider.
- **Empty sides are valid.** A market with no resting liquidity yields empty
  `bids`/`asks` and `None` from the derived properties.
- Monetary and size values are plain `float`; providers deliver them as strings
  or integer cents and the adapters convert.

## Example

A real `Market` (Polymarket), produced by the normalizers from the captured
fixtures (`order_book` depth trimmed to three levels per side for readability):

```json
{
  "provider": "polymarket",
  "id": "7111962",
  "title": "Ryan Kalkbrenner: Points O/U 4.5",
  "yes_price": 0.49,
  "no_price": 0.51,
  "order_book": {
    "bids": [
      { "price": 0.47, "size": 490.0 },
      { "price": 0.46, "size": 7.0 },
      { "price": 0.45, "size": 319.0 }
    ],
    "asks": [
      { "price": 0.51, "size": 244.0 },
      { "price": 0.52, "size": 1504.0 },
      { "price": 0.53, "size": 1073.44 }
    ],
    "timestamp": 1794973665871
  },
  "status": "open",
  "close_time": "2026-11-18T04:00:00Z",
  "volume": 9999.95233,
  "url": "https://polymarket.com/market/nba-cha-lal-2026-11-17-points-ryan-kalkbrenner-4pt5"
}
```
