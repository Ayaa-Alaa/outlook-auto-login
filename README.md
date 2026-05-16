# Outlook Auto Login

Automated Outlook account access with recovery email verification. Uses CloakBrowser (stealth Chromium) to bypass bot detection. Control everything via Telegram bot.

## Quick Start

```bash
git clone https://github.com/Ayaa-Alaa/outlook-auto-login.git
cd outlook-auto-login
bash setup.sh
```

Setup script will:
1. Install Python dependencies (venv + pip)
2. Ask for Telegram bot token and chat ID
3. Create `.env` config
4. Start Telegram bot

## For AI Agents

When user pastes this repo link, follow `agent_config.json` → `installation_flow`:

1. Clone repo
2. Ask user for: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `PROXY_URL` (optional)
3. Create `.env` with user data
4. `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
5. Start bot: `nohup python3 telegram_bot.py > bot.log 2>&1 &`
6. Tell user: "Buka Telegram → cari bot → /start"

User then manages everything via Telegram bot — no need to touch terminal again.

## Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome + status dashboard |
| `/addaccount email\|pass` | Tambah akun Outlook |
| `/listaccounts` | Lihat daftar akun |
| `/removeaccount email` | Hapus akun |
| `/addrecovery email:app_pass` | Tambah recovery Gmail |
| `/proxy` | Kelola proxy (manual / Webshare API / rotating) |
| `/run` | Jalankan batch login semua akun |
| `/run email` | Login 1 akun |
| `/status` | Cek status proses |
| `/report` | Hasil terakhir |

## Proxy Options

- **Manual** — Input langsung: `http://user:pass@host:port`
- **Webshare API** — Auto-fetch dari [webshare.io](https://www.webshare.io/) (20 proxy pool)
- **Webshare Rotating** — Auto-rotate proxy tiap batch

## Files

- `telegram_bot.py` — Telegram bot interface (main entry point)
- `outlook_login.py` — Single account login engine
- `batch_login.py` — Multi-account batch processor (CLI)
- `setup.sh` — One-line setup script
- `agent_config.json` — AI agent installation flow + config
- `data/` — Persistent storage (created by bot)
- `.env` — Sensitive config (created by setup)

## CLI Usage (tanpa bot)

```bash
# Single account
python outlook_login.py --email user@outlook.com --pass MyPass123

# Batch
python batch_login.py
```

## Status

Beta — tested with 9 accounts, 100% success rate (~3 min per account).

## License

Private — do not distribute.
