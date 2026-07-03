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
    "CN¥": "CNY",
    "CA$": "CAD",
    "A$": "AUD",
    "US$": "USD",
}

PRICE_RE = re.compile(
    r"(?P<symbol>US\$|CA\$|A\$|CN¥|[£$€¥])\s?(?P<price>\d{1,4}(?:[,.]\d{3})*(?:[,.]\d{2})?|\d{1,4})"
)


async def scan_product(product: Product, *, timeout_seconds: int = 25) -> PriceResult:
    source = product.source.lower().strip()

    if source == "app_store":
        return await scan_app_store(product, timeout_seconds=timeout_seconds)

    if source == "generic":
        return await scan_generic(product, timeout_seconds=timeout_seconds)

    if source == "capcut_vip":
        return await scan_capcut_vip(product, timeout_seconds=timeout_seconds)

    if source == "clipstudio_onetime":
        return await scan_clipstudio_onetime(product, timeout_seconds=timeout_seconds)

    if source == "adobe_page":
        return await scan_adobe_page(product, timeout_seconds=timeout_seconds)

    raise ScanError(
        f"Unknown source '{product.source}'. Supported sources: "
        "generic, app_store, capcut_vip, clipstudio_onetime, adobe_page"
    )


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


async def _post_json(
    url: str,
    *,
    json_body: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout_seconds: int = 25,
) -> dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    request_headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PikaPromoScanner/0.1)",
        "Accept": "application/json,text/plain,*/*",
        "Content-Type": "application/json",
    }
    if headers:
        request_headers.update(headers)

    async with aiohttp.ClientSession(headers=request_headers, timeout=timeout) as session:
        async with session.post(url, json=json_body) as response:
            text = await response.text(errors="replace")
            if response.status >= 400:
                raise ScanError(f"HTTP {response.status} while posting JSON API: {text[:300]}")
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                raise ScanError(f"API did not return JSON: {text[:300]}") from exc


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


async def scan_capcut_vip(product: Product, *, timeout_seconds: int = 25) -> PriceResult:
    endpoint = product.url or "https://commerce-api-sg.capcut.com/commerce/v1/subscription/cc_price_list"
    region = str(product.metadata.get("region", "GB")).upper()
    language = str(product.metadata.get("language", "en"))
    target_product_id = str(product.metadata.get("product_id", "capcut_pro_yearly_base"))

    headers = {
        "appid": "348188",
        "loc": region,
        "lan": language,
        "pf": "7",
        "appvr": "5.8.0",
        "tdid": "",
        "web_id": str(product.metadata.get("web_id", "7658086216906884624")),
        "sign-ver": "1",
        "app-sdk-version": "48.0.0",
    }

    body = {
        "aid": 348188,
        "scene": "vip",
        "region": region,
        "language": language,
    }

    raw = await _post_json(endpoint, json_body=body, headers=headers, timeout_seconds=timeout_seconds)

    if str(raw.get("ret")) != "0":
        raise ScanError(f"CapCut API error: {raw.get('errmsg') or raw}")

    data = raw.get("data")
    if not data and raw.get("response"):
        try:
            data = json.loads(raw["response"])
        except json.JSONDecodeError:
            data = None

    if not isinstance(data, dict):
        raise ScanError("CapCut API returned no usable data object")

    products = data.get("all_price_list") or []
    match = next((item for item in products if item.get("product_id") == target_product_id), None)
    if not match:
        available = ", ".join(str(item.get("product_id")) for item in products[:10])
        raise ScanError(f"CapCut product_id not found: {target_product_id}. Available: {available}")

    price_text = (
        (match.get("pipo_amount") or {}).get("amount")
        or match.get("price_tips")
        or (match.get("total_amount") / 100 if isinstance(match.get("total_amount"), (int, float)) else None)
    )

    try:
        price = float(price_text)
    except (TypeError, ValueError) as exc:
        raise ScanError(f"CapCut price was not numeric: {price_text!r}") from exc

    currency = str(match.get("currency_code") or product.currency or "USD").upper()

    return PriceResult(
        name=product.name,
        price=price,
        currency=currency,
        url="https://www.capcut.com/activities/subscribe/",
        payload={
            "source": "capcut_vip",
            "endpoint": endpoint,
            "region": region,
            "product_id": match.get("product_id"),
            "sku_id": match.get("sku_id"),
            "sku_plan_id": match.get("sku_plan_id"),
            "cycle_tips": match.get("cycle_tips"),
            "subscribe_cycle": match.get("subscribe_cycle"),
            "cycle_unit": match.get("cycle_unit"),
            "vip_price_tips": match.get("vip_price_tips"),
            "origin_price_tips": match.get("origin_price_tips"),
            "discount_percent": match.get("discount_percent"),
            "pipo_amount": match.get("pipo_amount"),
            "can_trial": match.get("can_trial"),
            "raw_item": match,
        },
    )


async def scan_clipstudio_onetime(product: Product, *, timeout_seconds: int = 25) -> PriceResult:
    url = product.url or "https://www.clipstudio.net/en/purchase/"
    html = await _fetch_text(url, timeout_seconds=timeout_seconds)

    edition = str(product.metadata.get("edition", "PRO")).upper()
    currency = str(product.metadata.get("currency", product.currency or "GBP")).upper()

    if edition not in {"PRO", "EX"}:
        raise ScanError("Clip Studio edition must be PRO or EX")

    data_name = "ProDATA_onetime" if edition == "PRO" else "ExDATA_onetime"

    sale_text_match = re.search(
        rf"{data_name}\s*=\s*\{{\s*'sale_save_text'\s*:\s*'([^']*)'",
        html,
        re.S,
    )
    sale_text = sale_text_match.group(1) if sale_text_match else ""

    block_match = re.search(
        rf"{data_name}\['{re.escape(currency)}'\]\s*=\s*\{{(.*?)\}}\s*;",
        html,
        re.S,
    )
    if not block_match:
        raise ScanError(f"Could not find Clip Studio {edition} pricing block for {currency}")

    fields = dict(re.findall(r"'([^']+)'\s*:\s*'([^']*)'", block_match.group(1)))

    normal_price_text = fields.get("price", "")
    sale_price_text = (
        fields.get("sale_US", "")
        + fields.get("sale_L_num", "")
        + fields.get("sale_S_num", "")
    ).strip()

    current_text = sale_price_text if sale_price_text else normal_price_text
    parsed = parse_price_text(current_text, currency)
    if not parsed:
        raise ScanError(f"Could not parse Clip Studio price: {current_text!r}")

    price, parsed_currency = parsed

    return PriceResult(
        name=product.name,
        price=price,
        currency=parsed_currency or currency,
        url=fields.get("url") or url,
        payload={
            "source": "clipstudio_onetime",
            "edition": edition,
            "currency": currency,
            "normal_price_text": normal_price_text,
            "sale_price_text": sale_price_text,
            "sale_text": sale_text,
            "store_url": fields.get("url"),
            "paypal_url": fields.get("url_paypal"),
            "raw_fields": fields,
        },
    )


async def scan_adobe_page(product: Product, *, timeout_seconds: int = 25) -> PriceResult:
    """
    Adobe UK pricing pages do not expose final prices in plain HTML.
    Instead, Adobe exposes promo markers / Milo OST price links in fragments.

    This scanner tracks the presence of known promo markers and maps them to
    known Adobe UK public prices. If the marker disappears, it falls back to
    the configured normal_price.
    """

    name_lower = product.name.lower()

    fragment_url = str(
        product.metadata.get(
            "fragment_url",
            "https://main--cc--adobecom.aem.live/uk/cc-shared/fragments/merch/products/photoshop/compare-plans/table/individual/intro-pricing",
        )
    )

    html = await _fetch_text(fragment_url, timeout_seconds=timeout_seconds)

    if "photoshop" in name_lower:
        promo_marker = str(product.metadata.get("promo_marker", "promo=PSHOP_3MO_UK"))
        promo_price = float(product.metadata.get("promo_price", 9.98))
        normal_price = product.normal_price if product.normal_price is not None else 21.98
        plan = "Photoshop Single App"
    elif "creative cloud" in name_lower or "all apps" in name_lower:
        promo_marker = str(product.metadata.get("promo_marker", "promo=CCI_AA_3MO_UK"))
        promo_price = float(product.metadata.get("promo_price", 32.66))
        normal_price = product.normal_price if product.normal_price is not None else 66.49
        plan = "Creative Cloud All Apps"
    else:
        raise ScanError(
            "Adobe page scanner currently supports Photoshop and Creative Cloud / All Apps by name."
        )

    promo_active = promo_marker in html
    price = promo_price if promo_active else float(normal_price)

    return PriceResult(
        name=product.name,
        price=price,
        currency=product.currency or "GBP",
        url=product.url,
        payload={
            "source": "adobe_page",
            "method": "adobe_promo_marker",
            "plan": plan,
            "fragment_url": fragment_url,
            "promo_marker": promo_marker,
            "promo_active": promo_active,
            "promo_price": promo_price,
            "normal_price": normal_price,
            "note": "Adobe prices are resolved dynamically; this tracks known promo markers in Adobe fragments.",
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
        visible_text = soup.get_text(" ", strip=True)
        parsed = parse_price_text(visible_text[:20000], product.currency)
        if parsed:
            price, currency = parsed
            candidates.append((price, currency, "page_text_fallback", {}))

    if not candidates:
        raise ScanError(
            "Could not find a price. Add a CSS selector with /add_product or use /add_appstore_app."
        )

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

    matches = list(PRICE_RE.finditer(text))
    for match in matches:
        symbol = match.group("symbol")
        raw_price = match.group("price")
        price = _normalise_number(raw_price)
        if price is not None:
            return price, CURRENCY_SYMBOLS.get(symbol, default_currency.upper())

    compact = text.strip()
    if re.fullmatch(r"\d{1,4}(?:[,.]\d{2})?", compact):
        price = _normalise_number(compact)
        if price is not None:
            return price, default_currency.upper()

    return None


def _normalise_number(raw: str) -> float | None:
    value = raw.strip().replace(" ", "")

    if value.count(",") > 0 and value.count(".") > 0:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif value.count(",") == 1 and value.count(".") == 0:
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
