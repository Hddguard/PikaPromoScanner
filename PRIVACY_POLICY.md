# PikaPromoScanner Privacy Policy

**Effective date:** 2 July 2026  
**Application name:** PikaPromoScanner  
**Owner/operator:** Hddguard 

This Privacy Policy explains what information **PikaPromoScanner** may collect, how that information is used, how it is stored, and how users or server administrators can request deletion.

PikaPromoScanner is a Discord bot that tracks sales, discounts, price drops, and promotional information for creative software, apps, subscriptions, and hardware.

## 1\. Summary

PikaPromoScanner is designed to collect as little Discord user data as practical.

The bot mainly stores configuration and deal-tracking data, such as Discord server IDs, alert channel IDs, product names, product URLs, prices, and price history.

PikaPromoScanner does **not** sell personal data. It does **not** use Discord message content for advertising. It does **not** intentionally collect payment card details, passwords, private messages, or sensitive personal information.

## 2\. Information the bot may collect

Depending on how the bot is configured and used, PikaPromoScanner may collect and store the following information:

### Discord server and channel data

* Discord server/guild IDs where the bot is installed.
* Discord channel IDs selected for deal alerts.
* Basic configuration settings for each server.

### Discord user data

* Discord user IDs of users who run commands, only where needed for command handling, permissions, watchlists, audit/debugging, or future user-specific features.
* Discord usernames or display names may appear temporarily in Discord interactions or logs, depending on Discord's API responses and hosting logs.

### Product and deal-tracking data

* Product names.
* Product URLs.
* Product categories.
* Configured normal prices, target prices, and discount thresholds.
* Current prices and historical prices.
* Scan timestamps.
* Alert timestamps.
* Source type, such as generic webpage, App Store lookup, or another configured source.

### Technical and diagnostic data

* Error messages and logs generated when the bot runs.
* Basic runtime information needed to diagnose crashes, failed scans, command errors, or API issues.

## 3\. Information the bot does not intentionally collect

PikaPromoScanner does not intentionally collect:

* Discord passwords or authentication credentials.
* Payment card or bank details.
* Private direct messages.
* Voice, video, or call content.
* Full Discord message history.
* Sensitive personal information such as health, religion, political opinions, or precise location.

The bot should not require Discord's Message Content privileged intent for its normal slash-command and alert features.

## 4\. How information is used

PikaPromoScanner uses stored information to:

* Remember which Discord channel should receive alerts.
* Track configured products and prices.
* Compare current prices with previous prices or configured normal prices.
* Send price-drop, sale, or discount alerts.
* Respond to Discord slash commands.
* Prevent duplicate or excessive alerts.
* Diagnose bugs, failed scans, or hosting issues.
* Improve the bot's reliability and features.

## 5\. Legal basis for processing, where applicable

Where privacy laws such as the UK GDPR or EU GDPR apply, the bot's owner/operator may process limited data based on:

* **Legitimate interests**, such as operating the bot, preventing abuse, maintaining security, and providing requested deal alerts.
* **Consent or user/admin action**, where a server administrator installs the bot, configures alert channels, or a user chooses to use commands or watchlist features.
* **Compliance with legal obligations**, where applicable.

## 6\. Data sharing

PikaPromoScanner does not sell personal data.

Data may be shared or processed in limited ways with:

* **Discord**, because the bot runs on Discord and uses Discord's API.
* **Hosting providers**, such as a VPS, cloud server, or deployment platform used to run the bot.
* **Third-party websites or APIs**, when checking public product, app, or pricing information. These requests usually relate to product data, not Discord user identity.
* **Maintainers or operators**, only as needed to operate, debug, secure, or support the bot.

PikaPromoScanner may include links to third-party stores, app pages, product pages, or deal pages. Those websites have their own privacy policies and terms.

## 7\. Data storage

PikaPromoScanner stores data in a local SQLite database by default, usually named something like:

```text
./data/pikapromo.sqlite3
```

If hosted on a server, this database is stored on that server or on the configured persistent storage volume.

The bot token and configuration secrets should be stored in an environment file or hosting secret manager and should never be committed to a public repository.

## 8\. Data retention

PikaPromoScanner keeps configuration, product, and price-history data for as long as needed to operate the bot, unless deleted earlier.

Data may be deleted when:

* A server administrator removes tracked products.
* A server administrator requests deletion of server data.
* The bot is removed from a server and the operator performs cleanup.
* The owner/operator resets the database.
* Data is no longer needed for bot operation.

Backups, if any, may persist for a limited period before being overwritten or deleted.

## 9\. Deletion requests

Server administrators or users may request deletion of data associated with a Discord server or user by contacting:

**\[Your contact email or support server link]**

To help process deletion requests, include:

* The Discord server ID, if requesting server data deletion.
* The Discord user ID, if requesting user-specific data deletion.
* A short description of what should be deleted.

The owner/operator may need to verify that the requester is authorised to request deletion of server-level configuration or data.

## 10\. Security

Reasonable steps should be taken to protect bot data, including:

* Keeping the Discord bot token secret.
* Not committing `.env` files or secrets to GitHub.
* Restricting server access.
* Keeping dependencies updated.
* Using only the Discord permissions the bot needs.
* Reviewing logs before sharing them publicly.

No system is perfectly secure, and PikaPromoScanner cannot guarantee absolute security.

## 11\. Children's privacy

PikaPromoScanner is intended for use within Discord servers and is not designed to knowingly collect personal information from children.

Discord users and server administrators are responsible for following Discord's age requirements and rules.

## 12\. International users

PikaPromoScanner may be hosted in a country different from the country where users are located. By using the bot, information may be processed in the country where the bot is hosted and where relevant service providers operate.

## 13\. Changes to this policy

This Privacy Policy may be updated from time to time. When changes are made, the effective date at the top of this file should be updated.

Continued use of PikaPromoScanner after changes means the updated policy applies.

## 14\. Contact

For questions, support, or privacy requests, contact:

**\[Your contact email or support server link]**

