# PikaPromoScanner 🛒⚡

A Discord bot that scans creative apps, design software, and hardware for price drops and posts alerts to a Discord channel.

Good starter targets:

- CapCut
- Clip Studio Paint
- Procreate
- Photoshop / Adobe Creative Cloud
- Wacom, Huion, XP-Pen tablets
- Affinity apps
- Any store page with a visible price

## What this first version can do

- Slash commands for adding/removing products
- Scheduled scanning every few hours
- SQLite database for tracked products, price history, and sent alerts
- Generic web page scanner with optional CSS selector support
- Apple App Store scanner using Apple/iTunes catalog lookup/search
- Discord alert embeds when a price drops
- Manual `/scan_now` testing command

## Important notes

This bot is a practical starter project, not magic fairy dust. Some websites use dynamic prices, regional prices, cookies, JavaScript rendering, bot protection, or A/B testing. For those sites, the generic scanner may need a CSS selector or a source-specific scanner.

For Amazon/Wacom hardware tracking, consider adding Keepa later instead of scraping Amazon pages directly. Keepa is much more reliable for Amazon price history.

## Project structure

```text
PikaPromoScanner/
├── run.py
├── requirements.txt
├── .env.example
├── data/
│   └── pikapromo.sqlite3  # created automatically
└── pikapromoscanner/
    ├── bot.py
    ├── config.py
    ├── database.py
    └── scanners.py
```

## 1. Create your Discord application and bot

1. Go to the Discord Developer Portal.
2. Create a new application named `PikaPromoScanner`.
3. Open the **Bot** page.
4. Add/reset the bot token and copy it.
5. Keep the token private. Do not paste it into Discord, GitHub, screenshots, or public chats.

## 2. Invite the bot to your server

In the Developer Portal:

1. Open **OAuth2**.
2. Use the URL Generator.
3. Select scopes:
   - `bot`
   - `applications.commands`
4. Select bot permissions:
   - Send Messages
   - Embed Links
   - Read Message History
   - View Channels
5. Open the generated invite link and add it to your server.

For testing, you need permission to manage the server or install apps on that server.

## 3. Install locally on Windows

Open PowerShell in the folder where you extracted this project.

```powershell
cd PikaPromoScanner
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
notepad .env
```

Fill in:

```env
DISCORD_TOKEN=your_bot_token_here
```

Optional but recommended during testing:

```env
DISCORD_GUILD_ID=your_server_id_here
```

Using a guild/server ID makes slash command updates appear faster while testing.

## 4. Run the bot

```powershell
python run.py
```

You should see something like:

```text
Logged in as PikaPromoScanner#1234
Synced 10 command(s)
```

## 5. First setup in Discord

In the Discord channel where you want alerts:

```text
/setup_alert_channel
```

Then check status:

```text
/pika_status
```

## 6. Add an App Store app, like Procreate

Use either a search term:

```text
/add_appstore_app name:Procreate country:GB search_term:Procreate normal_price:12.99 threshold_percent:10
```

Or use a track ID if you know it:

```text
/add_appstore_app name:Procreate country:GB track_id:425073498 normal_price:12.99 threshold_percent:10
```

Then test it:

```text
/scan_now product_id:1 send_alerts:false
```

The first scan creates a baseline. Alerts are sent after later scans detect a price drop or a changed price that meets your discount threshold.

## 7. Add a generic product/store page

For pages with clean product metadata:

```text
/add_product name:Clip Studio Paint url:https://example.com normal_price:179.99 currency:GBP threshold_percent:20
```

If the scanner cannot find the price, add a CSS selector for the page's price element:

```text
/add_product name:Clip Studio Paint url:https://example.com normal_price:179.99 currency:GBP threshold_percent:20 css_selector:.price
```

To find a CSS selector:

1. Open the product page in your browser.
2. Right-click the price.
3. Click **Inspect**.
4. Find a stable class/id around the price.
5. Try selectors like `.price`, `.sale-price`, `[data-testid="price"]`, or `span.price`.

## 8. Useful Discord commands

```text
/products
/product product_id:1
/scan_now product_id:1 send_alerts:false
/scan_now send_alerts:true
/deals
/price_history product_id:1
/remove_product product_id:1
/scanner_loop action:start
/scanner_loop action:stop
```

## 9. Recommended tracking strategy

Use source-specific tracking where possible:

| Target | Recommended approach |
|---|---|
| Procreate | `/add_appstore_app` |
| iOS/iPadOS creative apps | `/add_appstore_app` |
| Clip Studio Paint | official page + CSS selector if needed |
| Adobe / Photoshop | official regional pricing page, but may need custom scanner later |
| Wacom / Huion / XP-Pen | retailer API or Keepa later |
| Amazon products | Keepa integration later |

## 10. Keeping it running

For a simple home setup, keep the PowerShell window open.

For something more permanent, host it on:

- a small VPS
- Docker
- a Raspberry Pi
- a Windows scheduled task / NSSM service
- Railway/Fly.io/Render style hosting, if they allow long-running bot processes on your plan

## 11. Safety and maintenance

- Never commit `.env`.
- Never expose your bot token.
- Scan politely. The default interval is 6 hours.
- Avoid scraping pages that forbid automated access.
- Prefer APIs for stores that provide them.
- Add source-specific scanners for sites that need JavaScript or have complex pricing.

## Update 1.1
Added source-specific promo scanners for CapCut Pro, Clip Studio Paint, Adobe UK promo pricing, and exact App Store track ID support. 
The bot can now reliably track Procreate, CapCut Pro Monthly/Yearly, Clip Studio Paint PRO/EX, Adobe Photoshop, and Adobe Creative Cloud Pro, with scheduled Discord alerts when prices change.

## Next improvements

Nice upgrades for version 2:

- Keepa integration for Amazon/Wacom price history
- Google Play scanner
- Adobe-specific plan scanner
- Clip Studio Paint-specific sale scanner
- Role-based notifications, e.g. `@CreativeDeals`
- Per-user watchlists
- Daily summary message
- Web dashboard
