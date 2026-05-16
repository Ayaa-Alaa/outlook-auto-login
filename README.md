# Outlook Auto Login

Automated Outlook account access with recovery email verification. Uses CloakBrowser (stealth Chromium) to bypass bot detection.

## How It Works

1. Login to Outlook with email/password
2. If Microsoft asks for recovery email verification:
   - Match masked email against recovery email list from `.env`
   - Click "Send code" → wait for code via IMAP
   - If no code after 2 min → click "Use your password" (via dispatchEvent)
3. Bypass passkey setup by navigating directly to Outlook inbox

## Setup

```bash
# Install dependencies
pip install cloakbrowser python-dotenv

# Copy .env and fill in your values
cp .env.example .env
nano .env
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

## Files

- `outlook_login.py` — Single account login
- `batch_login.py` — Multi-account batch processor
- `.env` — Sensitive config (recovery emails, proxy, IMAP passwords)
- `.env.example` — Template for `.env`
- `accounts.txt` — Account list for batch mode
- `screenshots/` — Debug screenshots

## Status

Beta — tested with 9 accounts, 100% success rate (~3 min per account).

## License

Private — do not distribute.
