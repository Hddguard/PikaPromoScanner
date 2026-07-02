from __future__ import annotations

import asyncio
import logging
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .config import Config
from .database import Database, Product
from .scanners import PriceResult, ScanError, scan_product

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
LOGGER = logging.getLogger("PikaPromoScanner")

CONFIG = Config.from_env()
DB = Database(CONFIG.database_path)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def money(price: float | None, currency: str = "GBP") -> str:
    if price is None:
        return "n/a"
    if currency.upper() == "GBP":
        return f"£{price:,.2f}"
    if currency.upper() == "USD":
        return f"${price:,.2f}"
    if currency.upper() == "EUR":
        return f"€{price:,.2f}"
    return f"{price:,.2f} {currency.upper()}"


def discount_percent(current_price: float, normal_price: float | None) -> float | None:
    if normal_price is None or normal_price <= 0:
        return None
    return round(((normal_price - current_price) / normal_price) * 100, 2)


def should_alert(product: Product, updated: Product) -> tuple[bool, str, float | None]:
    current = updated.current_price
    if current is None:
        return False, "", None

    discount = discount_percent(current, updated.normal_price)
    previous = product.current_price

    if previous is None:
        # First scan establishes baseline only; no alert yet.
        return False, "baseline", discount

    if current < previous:
        drop = round(((previous - current) / previous) * 100, 2) if previous > 0 else 0
        return True, f"price dropped {drop}% from previous scan", discount

    if discount is not None and discount >= updated.threshold_percent:
        # Avoid repeating the same discount alert every scan by requiring the price to have changed.
        if previous != current:
            return True, f"discount reached {discount}%", discount

    return False, "", discount


def product_embed(product: Product, *, title_prefix: str = "📦") -> discord.Embed:
    embed = discord.Embed(title=f"{title_prefix} {product.name}", url=product.url)
    embed.add_field(name="ID", value=str(product.id), inline=True)
    embed.add_field(name="Source", value=product.source, inline=True)
    embed.add_field(name="Current", value=money(product.current_price, product.currency), inline=True)
    embed.add_field(name="Normal", value=money(product.normal_price, product.currency), inline=True)
    embed.add_field(name="Lowest", value=money(product.lowest_price, product.currency), inline=True)
    embed.add_field(name="Threshold", value=f"{product.threshold_percent:g}%", inline=True)
    if product.last_checked:
        embed.add_field(name="Last checked", value=product.last_checked, inline=False)
    if product.last_error:
        embed.add_field(name="Last error", value=product.last_error[:1000], inline=False)
    return embed


def alert_embed(product: Product, result: PriceResult, reason: str, discount: float | None) -> discord.Embed:
    embed = discord.Embed(
        title=f"🔥 Price alert: {product.name}",
        description=reason,
        url=result.url,
    )
    embed.add_field(name="Now", value=money(result.price, result.currency), inline=True)
    embed.add_field(name="Previous", value=money(product.current_price, product.currency), inline=True)
    embed.add_field(name="Normal", value=money(product.normal_price, result.currency), inline=True)
    if discount is not None:
        embed.add_field(name="Discount", value=f"{discount:g}%", inline=True)
    embed.add_field(name="Source", value=product.source, inline=True)
    embed.set_footer(text="PikaPromoScanner")
    return embed


async def get_alert_channel() -> discord.abc.Messageable | None:
    channel_id_raw = await DB.get_setting("deals_channel_id")
    channel_id = None
    if channel_id_raw:
        channel_id = int(channel_id_raw)
    elif CONFIG.deals_channel_id:
        channel_id = CONFIG.deals_channel_id

    if not channel_id:
        return None

    channel = bot.get_channel(channel_id)
    if channel:
        return channel  # type: ignore[return-value]

    try:
        fetched = await bot.fetch_channel(channel_id)
        return fetched if hasattr(fetched, "send") else None
    except discord.DiscordException:
        LOGGER.exception("Could not fetch configured deals channel %s", channel_id)
        return None


async def scan_one(product: Product, *, send_alerts: bool = True) -> tuple[bool, str]:
    try:
        result = await scan_product(product, timeout_seconds=CONFIG.http_timeout_seconds)
        updated = await DB.update_product_price(
            product,
            price=result.price,
            currency=result.currency,
            payload=result.payload,
        )
        alert, reason, discount = should_alert(product, updated)

        if alert and send_alerts:
            channel = await get_alert_channel()
            if channel is None:
                LOGGER.warning("Deal found but no alert channel is configured")
                return True, f"Deal found for {product.name}, but no alert channel is configured."

            await channel.send(embed=alert_embed(product, result, reason, discount))
            await DB.record_alert(
                product_id=product.id,
                price=result.price,
                old_price=product.current_price,
                normal_price=product.normal_price,
                discount_percent=discount,
                reason=reason,
            )
            return True, f"Alert sent for {product.name}: {reason}."

        return False, f"Checked {product.name}: {money(result.price, result.currency)}."

    except (ScanError, asyncio.TimeoutError) as exc:
        await DB.mark_product_error(product, str(exc))
        return False, f"Could not scan {product.name}: {exc}"
    except Exception as exc:  # Keep the scanner loop alive.
        LOGGER.exception("Unexpected scan failure for product %s", product.id)
        await DB.mark_product_error(product, f"Unexpected error: {exc}")
        return False, f"Unexpected error scanning {product.name}: {exc}"


@tasks.loop(minutes=CONFIG.scan_interval_minutes)
async def scheduled_scan() -> None:
    products = await DB.list_products(active_only=True)
    if not products:
        LOGGER.info("No active products to scan yet")
        return

    LOGGER.info("Scanning %s active products", len(products))
    for product in products:
        alert_sent, message = await scan_one(product, send_alerts=True)
        LOGGER.info("%s | alert=%s", message, alert_sent)
        await asyncio.sleep(2)  # Be gentle with stores and APIs.


@scheduled_scan.before_loop
async def before_scheduled_scan() -> None:
    await bot.wait_until_ready()


@bot.event
async def on_ready() -> None:
    await DB.init()

    if CONFIG.guild_id:
        guild = discord.Object(id=CONFIG.guild_id)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        LOGGER.info("Synced %s command(s) to guild %s", len(synced), CONFIG.guild_id)
    else:
        synced = await bot.tree.sync()
        LOGGER.info("Synced %s global command(s)", len(synced))

    if not scheduled_scan.is_running():
        scheduled_scan.start()

    LOGGER.info("Logged in as %s", bot.user)


@bot.tree.command(name="setup_alert_channel", description="Set this channel as the PikaPromoScanner alert channel.")
@app_commands.default_permissions(manage_guild=True)
async def setup_alert_channel(interaction: discord.Interaction) -> None:
    await DB.set_setting("deals_channel_id", str(interaction.channel_id))
    await interaction.response.send_message(
        f"Done — I’ll post deal alerts in {interaction.channel.mention}. 🛒",
        ephemeral=True,
    )


@bot.tree.command(name="add_product", description="Add a generic product/store page to scan for price drops.")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    name="Product name, e.g. Clip Studio Paint EX",
    url="Store/product page URL",
    normal_price="Usual full price. Used to calculate discount percentage.",
    currency="Currency code, e.g. GBP, USD, EUR",
    threshold_percent="Alert when discount reaches this percentage.",
    css_selector="Optional CSS selector for the price element. Strongly recommended for generic pages.",
)
async def add_product(
    interaction: discord.Interaction,
    name: str,
    url: str,
    normal_price: float | None = None,
    currency: str = "GBP",
    threshold_percent: float = CONFIG.default_discount_threshold_percent,
    css_selector: str | None = None,
) -> None:
    product_id = await DB.add_product(
        name=name,
        url=url,
        source="generic",
        currency=currency,
        normal_price=normal_price,
        threshold_percent=threshold_percent,
        css_selector=css_selector,
    )
    await interaction.response.send_message(
        f"Added **{name}** as product #{product_id}. Use `/scan_now product_id:{product_id}` to test it. ⚡",
        ephemeral=True,
    )


@bot.tree.command(name="add_appstore_app", description="Add an Apple App Store app to scan by track ID or search term.")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    name="Display name, e.g. Procreate",
    country="Two-letter App Store country code, e.g. GB, US, VN",
    track_id="Optional App Store track ID. Best option if you know it.",
    search_term="Optional search term if you do not know the track ID.",
    normal_price="Usual full price. Used to calculate discount percentage.",
    threshold_percent="Alert when discount reaches this percentage.",
)
async def add_appstore_app(
    interaction: discord.Interaction,
    name: str,
    country: str = "GB",
    track_id: int | None = None,
    search_term: str | None = None,
    normal_price: float | None = None,
    threshold_percent: float = CONFIG.default_discount_threshold_percent,
) -> None:
    metadata = {"country": country.upper()}
    if track_id:
        metadata["track_id"] = track_id
    if search_term:
        metadata["term"] = search_term

    placeholder_url = "https://apps.apple.com/"
    product_id = await DB.add_product(
        name=name,
        url=placeholder_url,
        source="app_store",
        currency="GBP" if country.upper() == "GB" else "USD",
        normal_price=normal_price,
        threshold_percent=threshold_percent,
        metadata=metadata,
    )
    await interaction.response.send_message(
        f"Added App Store app **{name}** as product #{product_id}. Use `/scan_now product_id:{product_id}` to resolve the live listing. 🍎",
        ephemeral=True,
    )


@bot.tree.command(name="products", description="List tracked products.")
@app_commands.describe(show_inactive="Show inactive/removed products too")
async def products(interaction: discord.Interaction, show_inactive: bool = False) -> None:
    items = await DB.list_products(active_only=not show_inactive)
    if not items:
        await interaction.response.send_message("No products are being tracked yet.", ephemeral=True)
        return

    lines = []
    for item in items[:25]:
        status = "✅" if item.active else "⏸️"
        lines.append(
            f"{status} **#{item.id} {item.name}** — {money(item.current_price, item.currency)} "
            f"/ normal {money(item.normal_price, item.currency)} — `{item.source}`"
        )

    if len(items) > 25:
        lines.append(f"…and {len(items) - 25} more.")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="product", description="Show details for one tracked product.")
async def product(interaction: discord.Interaction, product_id: int) -> None:
    item = await DB.get_product(product_id)
    if item is None:
        await interaction.response.send_message("I couldn’t find that product ID.", ephemeral=True)
        return
    await interaction.response.send_message(embed=product_embed(item), ephemeral=True)


@bot.tree.command(name="remove_product", description="Deactivate a tracked product.")
@app_commands.default_permissions(manage_guild=True)
async def remove_product(interaction: discord.Interaction, product_id: int) -> None:
    removed = await DB.deactivate_product(product_id)
    if removed:
        await interaction.response.send_message(f"Removed product #{product_id}. 🧹", ephemeral=True)
    else:
        await interaction.response.send_message("I couldn’t find an active product with that ID.", ephemeral=True)


@bot.tree.command(name="scan_now", description="Run a manual scan for one product or all products.")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    product_id="Optional product ID. Leave blank to scan all active products.",
    send_alerts="Whether to send Discord alerts if deals are found.",
)
async def scan_now(
    interaction: discord.Interaction,
    product_id: int | None = None,
    send_alerts: bool = True,
) -> None:
    await interaction.response.defer(ephemeral=True, thinking=True)

    if product_id is not None:
        item = await DB.get_product(product_id)
        if item is None or not item.active:
            await interaction.followup.send("I couldn’t find that active product ID.", ephemeral=True)
            return
        _, message = await scan_one(item, send_alerts=send_alerts)
        await interaction.followup.send(message, ephemeral=True)
        return

    items = await DB.list_products(active_only=True)
    if not items:
        await interaction.followup.send("No active products to scan yet.", ephemeral=True)
        return

    messages: list[str] = []
    for item in items:
        _, message = await scan_one(item, send_alerts=send_alerts)
        messages.append(message)
        await asyncio.sleep(2)

    output = "\n".join(f"• {message}" for message in messages)
    if len(output) > 1900:
        output = output[:1900] + "\n…output trimmed."
    await interaction.followup.send(output, ephemeral=True)


@bot.tree.command(name="deals", description="Show recent deal alerts.")
@app_commands.describe(limit="How many recent alerts to show")
async def deals(interaction: discord.Interaction, limit: app_commands.Range[int, 1, 20] = 10) -> None:
    rows = await DB.recent_deals(limit=int(limit))
    if not rows:
        await interaction.response.send_message("No deal alerts yet. The first scan creates baselines.", ephemeral=True)
        return

    lines = []
    for row in rows:
        discount_text = f" — {row['discount_percent']:g}% off" if row["discount_percent"] is not None else ""
        lines.append(
            f"🔥 **{row['name']}** — {money(row['price'], row['currency'])}{discount_text}\n"
            f"Reason: {row['reason']}\n<{row['url']}>"
        )
    await interaction.response.send_message("\n\n".join(lines), ephemeral=True)


@bot.tree.command(name="price_history", description="Show recent price history for a product.")
async def price_history(interaction: discord.Interaction, product_id: int) -> None:
    item = await DB.get_product(product_id)
    if item is None:
        await interaction.response.send_message("I couldn’t find that product ID.", ephemeral=True)
        return

    rows = await DB.price_history(product_id, limit=10)
    if not rows:
        await interaction.response.send_message("No price history yet. Try `/scan_now` first.", ephemeral=True)
        return

    lines = [f"**{item.name}** recent prices:"]
    for row in rows:
        lines.append(f"• {row['checked_at']} — {money(row['price'], row['currency'])}")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="pika_status", description="Show PikaPromoScanner status.")
async def pika_status(interaction: discord.Interaction) -> None:
    products_count = len(await DB.list_products(active_only=True))
    channel_id = await DB.get_setting("deals_channel_id") or str(CONFIG.deals_channel_id or "not set")
    status = "running" if scheduled_scan.is_running() else "stopped"
    await interaction.response.send_message(
        "⚡ **PikaPromoScanner status**\n"
        f"Active products: **{products_count}**\n"
        f"Scan loop: **{status}**\n"
        f"Interval: **{CONFIG.scan_interval_minutes} minutes**\n"
        f"Alert channel ID: `{channel_id}`",
        ephemeral=True,
    )


@bot.tree.command(name="scanner_loop", description="Start or stop the scheduled scanner loop.")
@app_commands.default_permissions(manage_guild=True)
async def scanner_loop(
    interaction: discord.Interaction,
    action: Literal["start", "stop"],
) -> None:
    if action == "start":
        if not scheduled_scan.is_running():
            scheduled_scan.start()
        await interaction.response.send_message("Scheduled scanner loop started. ✅", ephemeral=True)
    else:
        if scheduled_scan.is_running():
            scheduled_scan.cancel()
        await interaction.response.send_message("Scheduled scanner loop stopped. ⏸️", ephemeral=True)


def main() -> None:
    bot.run(CONFIG.discord_token)
