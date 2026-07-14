"""Optional market-data enrichment.

Tags a finance paper with the recent price of any well-known asset it mentions,
pulled from Yahoo Finance's public chart endpoint -- no API key, stdlib only, so
it adds no dependency.

ponytail: detection is a curated name->ticker allow-list, not free-text ticker
parsing. That keeps false positives near zero (an abstract full of words like
"IT", "US", "CEO" won't be misread as tickers) at the cost of missing niche
assets -- extend ASSET_MAP when a ticker you care about is missed. Cashtags
(``$AAPL``) are deliberately NOT parsed: in academic abstracts ``$...$`` is
LaTeX math, so ``$O(n)$`` / ``$R^2$`` would masquerade as tickers.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

# Lowercase asset name (as it appears in abstracts) -> Yahoo ticker symbol.
ASSET_MAP = {
    # indices
    "s&p 500": "^GSPC", "s&p500": "^GSPC", "sp500": "^GSPC", "s&p": "^GSPC",
    "nasdaq": "^IXIC", "dow jones": "^DJI", "russell 2000": "^RUT",
    "vix": "^VIX", "ftse 100": "^FTSE", "nikkei": "^N225", "euro stoxx": "^STOXX50E",
    # crypto
    "bitcoin": "BTC-USD", "ethereum": "ETH-USD", "solana": "SOL-USD",
    # commodities / rates
    "gold": "GC=F", "silver": "SI=F", "crude oil": "CL=F", "wti": "CL=F",
    "brent": "BZ=F", "natural gas": "NG=F",
    # mega-cap names commonly studied in finance papers
    "apple": "AAPL", "microsoft": "MSFT", "tesla": "TSLA", "amazon": "AMZN",
    "nvidia": "NVDA", "alphabet": "GOOGL", "meta platforms": "META",
    "jpmorgan": "JPM", "berkshire": "BRK-B",
}

_QUOTE_TTL = 600  # seconds; prices barely move over a digest's lifetime
_quote_cache: dict[str, tuple] = {}
_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}?range=5d&interval=1d"


def detect_tickers(text: str) -> list[str]:
    """Yahoo tickers for assets named in ``text`` (allow-list + cashtags)."""
    low = text.lower()
    return sorted({ticker for name, ticker in ASSET_MAP.items() if name in low})


def fetch_quote(ticker: str, *, timeout: float = 6.0) -> dict | None:
    """Latest price + daily change for ``ticker``, or None if unavailable.

    Fails soft: any network/parse error returns None so a flaky Yahoo never
    breaks the digest."""
    entry = _quote_cache.get(ticker)
    if entry and time.time() - entry[1] < _QUOTE_TTL:
        return entry[0]
    url = _CHART_URL.format(urllib.parse.quote(ticker))
    quote: dict | None = None
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            meta = json.loads(response.read())["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        if price is not None:
            quote = {
                "ticker": ticker,
                "price": round(price, 2),
                "currency": meta.get("currency", ""),
                "change_pct": round((price - prev) / prev * 100, 2)
                if prev else None,
            }
    except Exception:
        quote = None
    _quote_cache[ticker] = (quote, time.time())
    return quote


def enrich(text: str, *, limit: int = 3) -> list[dict]:
    """Quotes for up to ``limit`` assets mentioned in ``text``."""
    quotes = []
    for ticker in detect_tickers(text)[:limit]:
        quote = fetch_quote(ticker)
        if quote:
            quotes.append(quote)
    return quotes


if __name__ == "__main__":  # smoke check
    assert detect_tickers("A study of the S&P 500 and Bitcoin") == ["BTC-USD", "^GSPC"]
    assert detect_tickers("no assets here") == []
    # LaTeX math must not be read as tickers.
    assert detect_tickers("complexity is $O(n)$ with variance $R^2$") == []
    print("detect_tickers OK; sample quote:", fetch_quote("^GSPC"))
