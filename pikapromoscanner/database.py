from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class Product:
    id: int
    name: str
    url: str
    source: str
    currency: str
    normal_price: float | None
    current_price: float | None
    previous_price: float | None
    lowest_price: float | None
    threshold_percent: float
    css_selector: str | None
    metadata: dict[str, Any]
    active: bool
    last_checked: str | None
    last_error: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Product":
        return cls(
            id=row["id"],
            name=row["name"],
            url=row["url"],
            source=row["source"],
            currency=row["currency"],
            normal_price=row["normal_price"],
            current_price=row["current_price"],
            previous_price=row["previous_price"],
            lowest_price=row["lowest_price"],
            threshold_percent=row["threshold_percent"],
            css_selector=row["css_selector"],
            metadata=json.loads(row["metadata_json"] or "{}"),
            active=bool(row["active"]),
            last_checked=row["last_checked"],
            last_error=row["last_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class Database:
    def __init__(self, path: Path):
        self.path = path

    @asynccontextmanager
    async def connection(self):
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
        finally:
            await db.close()

    async def init(self) -> None:
        async with self.connection() as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'generic',
                    currency TEXT NOT NULL DEFAULT 'GBP',
                    normal_price REAL,
                    current_price REAL,
                    previous_price REAL,
                    lowest_price REAL,
                    threshold_percent REAL NOT NULL DEFAULT 15,
                    css_selector TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    active INTEGER NOT NULL DEFAULT 1,
                    last_checked TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    price REAL NOT NULL,
                    currency TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    source_payload_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS alerts_sent (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    price REAL NOT NULL,
                    old_price REAL,
                    normal_price REAL,
                    discount_percent REAL,
                    reason TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
                );
                """
            )
            await db.commit()

    async def set_setting(self, key: str, value: str) -> None:
        now = utc_now_iso()
        async with self.connection() as db:
            await db.execute(
                """
                INSERT INTO settings(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, now),
            )
            await db.commit()

    async def get_setting(self, key: str) -> str | None:
        async with self.connection() as db:
            cur = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = await cur.fetchone()
            return None if row is None else row["value"]

    async def add_product(
        self,
        *,
        name: str,
        url: str,
        source: str = "generic",
        currency: str = "GBP",
        normal_price: float | None = None,
        threshold_percent: float = 15,
        css_selector: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        now = utc_now_iso()
        async with self.connection() as db:
            cur = await db.execute(
                """
                INSERT INTO products(
                    name, url, source, currency, normal_price, threshold_percent,
                    css_selector, metadata_json, active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    name.strip(),
                    url.strip(),
                    source,
                    currency.upper().strip(),
                    normal_price,
                    threshold_percent,
                    css_selector.strip() if css_selector else None,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def get_product(self, product_id: int) -> Product | None:
        async with self.connection() as db:
            cur = await db.execute("SELECT * FROM products WHERE id = ?", (product_id,))
            row = await cur.fetchone()
            return Product.from_row(row) if row else None

    async def list_products(self, *, active_only: bool = True) -> list[Product]:
        sql = "SELECT * FROM products"
        params: tuple[Any, ...] = ()
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY id ASC"

        async with self.connection() as db:
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            return [Product.from_row(row) for row in rows]

    async def deactivate_product(self, product_id: int) -> bool:
        now = utc_now_iso()
        async with self.connection() as db:
            cur = await db.execute(
                "UPDATE products SET active = 0, updated_at = ? WHERE id = ? AND active = 1",
                (now, product_id),
            )
            await db.commit()
            return cur.rowcount > 0

    async def update_product_price(
        self,
        product: Product,
        *,
        price: float,
        currency: str,
        payload: dict[str, Any] | None = None,
    ) -> Product:
        now = utc_now_iso()
        previous_price = product.current_price
        lowest_price = price if product.lowest_price is None else min(product.lowest_price, price)

        async with self.connection() as db:
            await db.execute(
                """
                UPDATE products
                SET previous_price = ?, current_price = ?, lowest_price = ?, currency = ?,
                    last_checked = ?, last_error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (previous_price, price, lowest_price, currency.upper(), now, now, product.id),
            )
            await db.execute(
                """
                INSERT INTO price_history(product_id, price, currency, checked_at, source_payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    product.id,
                    price,
                    currency.upper(),
                    now,
                    json.dumps(payload or {}, ensure_ascii=False),
                ),
            )
            await db.commit()

        refreshed = await self.get_product(product.id)
        if refreshed is None:
            raise RuntimeError("Product disappeared after update")
        return refreshed

    async def mark_product_error(self, product: Product, error: str) -> None:
        now = utc_now_iso()
        async with self.connection() as db:
            await db.execute(
                """
                UPDATE products
                SET last_checked = ?, last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, error[:500], now, product.id),
            )
            await db.commit()

    async def record_alert(
        self,
        *,
        product_id: int,
        price: float,
        old_price: float | None,
        normal_price: float | None,
        discount_percent: float | None,
        reason: str,
    ) -> None:
        now = utc_now_iso()
        async with self.connection() as db:
            await db.execute(
                """
                INSERT INTO alerts_sent(
                    product_id, price, old_price, normal_price, discount_percent, reason, sent_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (product_id, price, old_price, normal_price, discount_percent, reason, now),
            )
            await db.commit()

    async def recent_deals(self, limit: int = 10) -> list[aiosqlite.Row]:
        async with self.connection() as db:
            cur = await db.execute(
                """
                SELECT a.*, p.name, p.url, p.currency
                FROM alerts_sent a
                JOIN products p ON p.id = a.product_id
                ORDER BY a.sent_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            return await cur.fetchall()

    async def price_history(self, product_id: int, limit: int = 10) -> list[aiosqlite.Row]:
        async with self.connection() as db:
            cur = await db.execute(
                """
                SELECT * FROM price_history
                WHERE product_id = ?
                ORDER BY checked_at DESC
                LIMIT ?
                """,
                (product_id, limit),
            )
            return await cur.fetchall()
