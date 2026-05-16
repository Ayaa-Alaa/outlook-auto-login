# Outlook Auto Login

Automated Outlook account access with recovery email verification. Uses CloakBrowser (stealth Chromium) to bypass bot detection. Control everything via Telegram bot.

## Quick Start

```bash
# 1. Clone repo
git clone https://github.com/Ayaa-Alaa/outlook-auto-login.git
cd outlook-auto-login

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
nano .env  # Fill in bot token, proxy, recovery emails

# 5. Run Telegram bot
python telegram_bot.py
```

## Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome + status |
| `/addaccount email\|pass` | Tambah akun Outlook |
| `/listaccounts` | Lihat daftar akun |
| `/removeaccount email` | Hapus akun |
| `/addrecovery email:app_pass` | Tambah recovery email |
| `/proxy` | Kelola proxy (manual / Webshare API) |
| `/run` | Jalankan batch login semua akun |
| `/run email` | Login 1 akun |
| `/status` | Cek status proses |
| `/report` | Hasil terakhir |

## Proxy Options

1. **Manual** — Set langsung: `http://user:pass@host:port`
2. **Webshare API** — Auto-fetch dari https://www.webshare.io/ (20 proxy pool)
3. **Webshare Rotating** — Auto-rotate proxy tiap batch

## CLI Usage (tanpa bot)

### Single account
```bash
python outlook_login.py --email user@outlook.com --pass MyPass123
```

### Batch (from accounts.txt)
```bash
python batch_login.py
```

## .env Configuration

```
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_ALLOWED_USERS=your_telegram_user_id
PROXY_URL=http://user:pass@host:port
RECOVERY_EMAILS=email1@gmail.com:app_pass,email2@gmail.com:app_pass
```

## Files

- `telegram_bot.py` — Telegram bot interface (main entry point)
- `outlook_login.py` — Single account login engine
- `batch_login.py` — Multi-account batch processor (CLI)
- `data/` — Persistent data (accounts.json, config.json, results.json)
- `.env` — Sensitive config
- `agent_config.json` — AI agent integration config

## Status

Beta — tested with 9 accounts, 100% success rate (~3 min per account).

## License

Private — do not distribute.
