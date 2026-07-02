# Deploy PikaPromoScanner on Oracle Cloud Always Free

This guide assumes you already pushed the repository to GitHub.

## 0. Safety first

If your bot token was ever pasted into a chat, screenshot, commit, terminal recording, or public place, reset it in the Discord Developer Portal before deploying.

Never commit `.env`.

## 1. Create an Oracle Cloud VM

Recommended shape for this bot:

- Ubuntu 24.04 or 22.04
- Always Free eligible VM
- 1 OCPU and 1 GB RAM is enough for light scanning
- Default boot volume is enough for the starter bot

## 2. SSH into the VM

From your PC:

```bash
ssh ubuntu@YOUR_SERVER_PUBLIC_IP
```

If Oracle gave you a private key file:

```bash
ssh -i path/to/private-key.key ubuntu@YOUR_SERVER_PUBLIC_IP
```

## 3. Install dependencies

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git
```

## 4. Clone the repo

```bash
git clone https://github.com/Hddguard/PikaPromoScanner.git
cd PikaPromoScanner
```

## 5. Create the virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 6. Create the .env file

```bash
cp .env.example .env
nano .env
```

Fill in at least:

```env
DISCORD_TOKEN=your_new_discord_bot_token_here
DISCORD_GUILD_ID=your_discord_server_id_here
SCAN_INTERVAL_MINUTES=360
DATABASE_PATH=data/pikapromo.sqlite3
```

Save in nano with `Ctrl+O`, Enter, then `Ctrl+X`.

## 7. Test manually

```bash
python run.py
```

In Discord, run:

```text
/setup_alert_channel
/pika_status
```

Stop the bot with `Ctrl+C` once it works.

## 8. Run as a systemd service

Create the service file:

```bash
sudo nano /etc/systemd/system/pikapromoscanner.service
```

Paste this:

```ini
[Unit]
Description=PikaPromoScanner Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/ubuntu/PikaPromoScanner
ExecStart=/home/ubuntu/PikaPromoScanner/.venv/bin/python /home/ubuntu/PikaPromoScanner/run.py
Restart=always
RestartSec=10
User=ubuntu
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pikapromoscanner
sudo systemctl start pikapromoscanner
```

Check status:

```bash
sudo systemctl status pikapromoscanner --no-pager
```

Follow logs:

```bash
journalctl -u pikapromoscanner -f
```

## 9. Updating the bot later

```bash
cd ~/PikaPromoScanner
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart pikapromoscanner
journalctl -u pikapromoscanner -f
```

## 10. Backup the SQLite database

```bash
cp data/pikapromo.sqlite3 data/pikapromo.backup.$(date +%Y%m%d-%H%M%S).sqlite3
```
