# Outlook Auto Login

Automated Outlook account login with recovery email verification. Uses CloakBrowser (stealth Chromium) to bypass bot detection.

## Quick Start

```bash
git clone https://github.com/Ayaa-Alaa/outlook-auto-login.git
cd outlook-auto-login
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp config.json.example config.json
# Edit config.json — add recovery emails and proxy
cp accounts.txt.example accounts.txt
# Edit accounts.txt — add Outlook accounts
python batch_login.py
```

## For AI Agents

Paste this repo link to your agent. Agent reads `agent_config.json` and follows the installation flow:

1. Clone & install deps
2. Ask user for: recovery emails, proxy (optional), accounts
3. Create `config.json` and `accounts.txt`
4. Test single account → run batch → report results

## CLI Usage

### Single account
```bash
python outlook_login.py --email user@outlook.com --pass MyPass123
```

### Single with custom config
```bash
python outlook_login.py --config config.json --email user@outlook.com --pass MyPass123
```

### Batch (from accounts.txt or accounts.json)
```bash
python batch_login.py
python batch_login.py --accounts my_accounts.txt
python batch_login.py --proxy http://user:pass@host:port
```

## Config

`config.json`:
```json
{
  "proxy_url": "http://user:pass@host:port",
  "recovery_emails": {
    "recovery1@gmail.com": "app_password",
    "recovery2@gmail.com": "app_password"
  }
}
```

## Files

- `outlook_login.py` — Single account login engine
- `batch_login.py` — Multi-account batch processor
- `config.json` — Runtime config (create from `config.json.example`)
- `accounts.txt` — Account list (create from `accounts.txt.example`)
- `results.json` — Auto-generated after batch run
- `agent_config.json` — Agent installation flow & reference

## Status

Tested with 9 accounts, 100% success rate (~3 min per account).

## License

Private — do not distribute.
