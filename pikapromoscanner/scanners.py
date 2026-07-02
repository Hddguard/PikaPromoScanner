from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlencode

import aiohttp
from bs4 import BeautifulSoup

from .database import Product


class ScanError(RuntimeError):
    """Raised when a product cannot be scanned safely."""


@dataclass(slots=True)
class PriceResult:
    name: str
    price: float
    currency: str
    url: str
    payload: dict[str, Any]


CURRENCY_SYMBOLS = {
    "£": "GBP",
    "$": "USD",
    "€": "EUR",
    "¥": "JPY",
}

PRICE_RE = re.compile(
    r"(?P<symbol>[£$€¥])\s?(?P<price>\d{1,4}(?:[,.]\d{3})*(?:[,.]\d{2})?|\d{1,4})"
)


async def scan_product(product: Product, *, timeout_seconds: int = 25) -> PriceResult:
    source = product.source.lower().strip()

    if source == "app_store":
        return await scan_app_store(product, timeout_seconds=timeout_seconds)

    if source == "generic":
        return await scan_generic(product, timeout_seconds=timeout_seconds)

    raise ScanError(f"Unknown source '{product.source}'. Supported sources: generic, app_store")


async def _fetch_text(url: str, *, timeout_seconds: int = 25) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; PikaPromoScanner/0.1; "
            "+https://example.local/pikapromoscanner)"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        async with session.get(url) as response:
            if response.status >= 400:
                raise ScanError(f"HTTP {response.status} while fetching product page")
            return await response.text(errors="replace")


async def _fetch_json(url: str, *, timeout_seconds: int = 25) -> dict[str, Any]:
    headers = {
        "User-Agent": "PikaPromoScanner/0.1",
        "Accept": "application/json,text/plain,*/*",
    }
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        async with session.get(url) as response:
            if response.status >= 400:
                raise ScanError(f"HTTP {response.status} while fetching JSON API")
            return await response.json(content_type=None)


async def scan_app_store(product: Product, *, timeout_seconds: int = 25) -> PriceResult:
    """
    Scan Apple App Store / iTunes catalog entries.

    metadata_json supports either:
      {"country": "GB", "track_id": 425073498}
    or:
      {"country": "GB", "term": "Procreate"}
    """

    country = str(product.metadata.get("country", "GB")).upper()
    track_id = product.metadata.get("track_id")
    term = product.metadata.get("term") or product.name

    if track_id:
        query = urlencode({"id": str(track_id), "country": country})
        endpoint = f"https://itunes.apple.com/lookup?{query}"
    else:
        query = urlencode(
            {"term": term, "country": country, "media": "software", "entity": "software", "limit": 1}
        )
        endpoint = f"https://itunes.apple.com/search?{query}"

    data = await _fetch_json(endpoint, timeout_seconds=timeout_seconds)
    results = data.get("results") or []
    if not results:
        raise ScanError(f"No App Store result found for {product.name!r} in {country}")

    item = results[0]
    price = item.get("price")
    if price is None:
        # Some free/subscription listings may not expose a direct app purchase price.
        price = 0.0

    try:
        numeric_price = float(price)
    except (TypeError, ValueError) as exc:
        raise ScanError(f"App Store price was not numeric: {price!r}") from exc

    return PriceResult(
        name=item.get("trackName") or product.name,
        price=numeric_price,
        currency=item.get("currency") or product.currency,
        url=item.get("trackViewUrl") or product.url,
        payload={
            "source": "app_store",
            "endpoint": endpoint,
            "track_id": item.get("trackId"),
            "bundle_id": item.get("bundleId"),
            "formatted_price": item.get("formattedPrice"),
            "version": item.get("version"),
        },
    )


async def scan_generic(product: Product, *, timeout_seconds: int = 25) -> PriceResult:
    html = await _fetch_text(product.url, timeout_seconds=timeout_seconds)
    soup = BeautifulSoup(html, "lxml")

    candidates: list[tuple[float, str | None, str, dict[str, Any]]] = []

    if product.css_selector:
        selected = soup.select_one(product.css_selector)
        if selected:
            parsed = parse_price_text(selected.get_text(" ", strip=True), product.currency)
            if parsed:
                price, currency = parsed
                candidates.append((price, currency, "css_selector", {"selector": product.css_selector}))
        else:
            raise ScanError(f"CSS selector did not match anything: {product.css_selector}")

    candidates.extend(_prices_from_meta_tags(soup, product.currency))
    candidates.extend(_prices_from_json_ld(soup, product.currency))

    if not candidates:
        # Last resort: check compact visible text, but only use fairly obvious currency-prefixed prices.
        visible_text = soup.get_text(" ", strip=True)
        parsed = parse_price_text(visible_text[:20000], product.currency)
        if parsed:
            price, currency = parsed
            candidates.append((price, currency, "page_text_fallback", {}))

    if not candidates:
        raise ScanError(
            "Could not find a price. Add a CSS selector with /add_product or use /add_appstore_app."
        )

    # Usually the lowest detected sale price is the interesting one. This can be adjusted per site later.
    price, currency, method, details = sorted(candidates, key=lambda row: row[0])[0]

    return PriceResult(
        name=product.name,
        price=price,
        currency=currency or product.currency,
        url=product.url,
        payload={"source": "generic", "method": method, **details},
    )


def _prices_from_meta_tags(soup: BeautifulSoup, default_currency: str) -> list[tuple[float, str | None, str, dict[str, Any]]]:
    results: list[tuple[float, str | None, str, dict[str, Any]]] = []
    selectors = [
        "meta[property='product:price:amount']",
        "meta[property='og:price:amount']",
        "meta[itemprop='price']",
        "meta[name='price']",
    ]

    for selector in selectors:
        tag = soup.select_one(selector)
        if not tag:
            continue
        content = tag.get("content") or tag.get("value")
        parsed = parse_price_text(str(content), default_currency)
        if parsed:
            price, currency = parsed
            currency_tag = soup.select_one(
                "meta[property='product:price:currency'], meta[property='og:price:currency'], meta[itemprop='priceCurrency']"
            )
            detected_currency = (
                (currency_tag.get("content") or currency_tag.get("value")) if currency_tag else currency
            )
            results.append(
                (price, str(detected_currency or default_currency).upper(), "meta_tag", {"selector": selector})
            )
    return results


def _prices_from_json_ld(soup: BeautifulSoup, default_currency: str) -> list[tuple[float, str | None, str, dict[str, Any]]]:
    results: list[tuple[float, str | None, str, dict[str, Any]]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for node in _walk_json(data):
            if not isinstance(node, dict):
                continue
            if "price" in node or "lowPrice" in node:
                raw_price = node.get("price", node.get("lowPrice"))
                parsed = parse_price_text(str(raw_price), default_currency)
                if parsed:
                    price, currency = parsed
                    detected_currency = node.get("priceCurrency") or currency or default_currency
                    results.append(
                        (
                            price,
                            str(detected_currency).upper(),
                            "json_ld",
                            {"json_ld_type": node.get("@type")},
                        )
                    )
    return results


def _walk_json(data: Any) -> Iterable[Any]:
    yield data
    if isinstance(data, dict):
        for value in data.values():
            yield from _walk_json(value)
    elif isinstance(data, list):
        for item in data:
            yield from _walk_json(item)


def parse_price_text(text: str, default_currency: str = "GBP") -> tuple[float, str | None] | None:
    if not text:
        return None

    # First look for currency-prefixed prices because those are less ambiguous.
    matches = list(PRICE_RE.finditer(text))
    for match in matches:
        symbol = match.group("symbol")
        raw_price = match.group("price")
        price = _normalise_number(raw_price)
        if price is not None:
            return price, CURRENCY_SYMBOLS.get(symbol, default_currency.upper())

    # Then accept a plain numeric if the whole string is basically a price.
    compact = text.strip()
    if re.fullmatch(r"\d{1,4}(?:[,.]\d{2})?", compact):
        price = _normalise_number(compact)
        if price is not None:
            return price, default_currency.upper()

    return None


def _normalise_number(raw: str) -> float | None:
    value = raw.strip().replace(" ", "")

    # Convert common thousands/decimal combinations.
    if value.count(",") > 0 and value.count(".") > 0:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif value.count(",") == 1 and value.count(".") == 0:
        # Treat 12,99 as 12.99 but 1,299 as 1299.
        left, right = value.split(",")
        if len(right) == 2:
            value = f"{left}.{right}"
        else:
            value = left + right
    else:
        value = value.replace(",", "")

    try:
        return float(value)
    except ValueError:
        return None
