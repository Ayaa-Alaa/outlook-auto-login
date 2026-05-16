# Outlook Auto Login

Automated Outlook account access with recovery email verification. Uses CloakBrowser (stealth Chromium) to bypass bot detection.

## How It Works

1. Login to Outlook with email/password
2. If Microsoft asks for recovery email verification:
   - Match masked email against recovery email list from `.env`
   - Click "Send code" → wait for code via IMAP
   - If no code after 2 min → click "Use your password" (via dispatchEvent)
3. Bypass passkey setup by navigating directly to Outlook inbox

## Quick Start

```bash
# 1. Clone repo
git clone https://github.com/Ayaa-Alaa/outlook-auto-login.git
cd outlook-auto-login

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies (includes geoip for proxy timezone detection)
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
nano .env  # Fill in your proxy and recovery email credentials

# 5. Add accounts
cp accounts.txt.example accounts.txt
nano accounts.txt  # Format: email|password per line

# 6. Run
python batch_login.py
```

## Usage

### Single account
```bash
python outlook_login.py --email user@outlook.com --pass MyPass123
```

### Batch (from accounts.txt)
```bash
# Format: email|password per line
python batch_login.py
```

## .env Configuration

```
PROXY_URL=http://user:pass@host:port
RECOVERY_EMAILS=email1@gmail.com:app_password,email2@gmail.com:app_password
```

- **PROXY_URL**: HTTP/SOCKS5 proxy for CloakBrowser (helps bypass geo-restrictions)
- **RECOVERY_EMAILS**: Gmail accounts used as recovery emails for Outlook. Need App Passwords for IMAP access. Generate at https://myaccount.google.com/apppasswords

## Files

- `outlook_login.py` — Single account login
- `batch_login.py` — Multi-account batch processor
- `.env` — Sensitive config (recovery emails, proxy, IMAP passwords)
- `.env.example` — Template for `.env`
- `accounts.txt` — Account list for batch mode
- `agent_config.json` — AI agent integration config (tools, APIs, flow)
- `screenshots/` — Debug screenshots (auto-created)

## Dependencies

- `cloakbrowser[geoip]` — Stealth Chromium with proxy geo-detection
- `python-dotenv` — Load .env files

## Status

Beta — tested with 9 accounts, 100% success rate (~3 min per account).

## License

Private — do not distribute.
