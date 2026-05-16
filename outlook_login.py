"""
Outlook Auto Login — Automated Outlook account access with recovery email verification.

Flow:
1. Enter email → recovery page (if needed)
2. Match recovery email from config.json
3. Click "Send code" → wait for code via IMAP
4. If no code after 2 min → click "Use your password"
5. Navigate to Outlook (bypass passkey)

Usage:
    python outlook_login.py --email user@outlook.com --pass MyPass123
    python outlook_login.py --config config.json --email user@outlook.com --pass MyPass123
"""

import imaplib
import email
import re
import sys
import json
import time
import argparse
import logging
import datetime
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).parent
SCREENSHOT_DIR = SCRIPT_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("outlook_auto")


# ─── Config ───────────────────────────────────────────────────────────
def load_config(config_path: Path = None) -> dict:
    """Load config from config.json."""
    if config_path is None:
        config_path = SCRIPT_DIR / "config.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
    return {}


def get_proxy(config: dict) -> str:
    """Get proxy URL from config."""
    return config.get("proxy_url", "")


def get_recovery_emails(config: dict) -> dict:
    """Get recovery emails dict from config. {email: app_password}"""
    return config.get("recovery_emails", {})


# ─── Recovery email matching ─────────────────────────────────────────
class RecoveryEmailManager:
    def __init__(self, emails: dict[str, str] = None, config: dict = None):
        if emails:
            self.emails = emails
        elif config:
            self.emails = get_recovery_emails(config)
        else:
            self.emails = {}
        log.info(f"Loaded {len(self.emails)} recovery emails")

    def match_masked(self, masked: str) -> list[str]:
        m = re.match(r'^([a-z0-9.]+)\*+@(.+)$', masked.lower())
        if not m:
            return []
        prefix, domain = m.group(1), m.group(2)
        return sorted(
            [e for e in self.emails if e.endswith(f"@{domain}") and e.startswith(prefix)],
            key=lambda e: len(e.split('@')[0])
        )


# ─── IMAP code polling ───────────────────────────────────────────────
def wait_for_code(gmail_addr: str, app_password: str, after_time: float, max_wait: int = 120) -> Optional[str]:
    """Wait for NEW Microsoft verification code via IMAP."""
    log.info(f"  Polling {gmail_addr} for new code (max {max_wait}s)...")
    start = time.time()

    while time.time() - start < max_wait:
        try:
            mail = imaplib.IMAP4_SSL('imap.gmail.com', 993)
            mail.login(gmail_addr, app_password)
            mail.select('inbox')

            today = datetime.datetime.now().strftime("%d-%b-%Y")
            status, msgs = mail.search(None, f'(SINCE "{today}")', 'FROM', 'microsoft')
            ids = msgs[0].split() if msgs[0] else []

            for msg_id in reversed(ids[-10:]):
                status, data = mail.fetch(msg_id, '(BODY[HEADER.FIELDS (DATE)])')
                header = data[0][1].decode('utf-8', errors='ignore')
                try:
                    email_date = email.utils.parsedate_to_datetime(header.replace('Date:', '').strip())
                    if email_date.timestamp() < after_time:
                        continue
                except:
                    continue

                status, data = mail.fetch(msg_id, '(RFC822)')
                msg = email.message_from_bytes(data[0][1])
                body = ''
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == 'text/plain':
                            body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                            break
                else:
                    body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')

                match = re.search(r'(?:code is|コード)[:\s]*(\d{4,8})', body, re.IGNORECASE)
                if not match:
                    match = re.search(r'(\d{6})', body)
                if match:
                    code = match.group(1)
                    log.info(f"  Found NEW code: {code}")
                    mail.logout()
                    return code

            mail.logout()
        except Exception as e:
            log.warning(f"  IMAP error: {e}")

        elapsed = int(time.time() - start)
        print(f"  Waiting... ({elapsed}s)", end='\r')
        time.sleep(10)

    log.warning(f"  Timeout after {max_wait}s — no new code received")
    return None


# ─── Login engine ─────────────────────────────────────────────────────
class OutlookLogin:
    def __init__(self, email_addr: str, password: str, recovery_mgr: RecoveryEmailManager,
                 headless: bool = True, proxy: str = ""):
        self.email = email_addr
        self.password = password
        self.recovery_mgr = recovery_mgr
        self.headless = headless
        self.proxy = proxy
        self.page = None
        self.browser = None

    def _screenshot(self, name: str):
        self.page.screenshot(path=str(SCREENSHOT_DIR / f"{name}.png"))

    def _text(self, n: int = 500) -> str:
        return self.page.evaluate(f'() => document.body.innerText.substring(0, {n})')

    def _fill(self, value: str, *selectors) -> bool:
        for s in selectors:
            try:
                self.page.fill(s, value)
                return True
            except:
                continue
        return False

    def _submit(self):
        self.page.click('button[type="submit"]', timeout=5000)

    def _click_use_password(self):
        self.page.evaluate('''() => {
            const els = document.querySelectorAll('*');
            for (const el of els) {
                const t = el.innerText?.trim();
                if ((t === 'Use your password' || t === 'パスワードを使用する') && el.children.length === 0) {
                    const rect = el.getBoundingClientRect();
                    ['mousedown','mouseup','click'].forEach(e => {
                        el.dispatchEvent(new MouseEvent(e, {
                            bubbles:true, cancelable:true, view:window,
                            clientX:rect.x+rect.width/2, clientY:rect.y+rect.height/2
                        }));
                    });
                    return true;
                }
            }
            return false;
        }''')

    def _click_send_code(self) -> Optional[str]:
        return self.page.evaluate('''() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                const t = b.innerText?.trim();
                if (t && (t.includes('Send code') || t.includes('コードの送信'))) {
                    b.click();
                    return t;
                }
            }
            return null;
        }''')

    def _enter_code(self, code: str) -> bool:
        for i, digit in enumerate(code[:6]):
            try:
                self.page.fill(f'#codeEntry-{i}', digit)
            except:
                self.page.evaluate(f'''() => {{
                    const el = document.querySelector('#codeEntry-{i}');
                    if (el) {{ el.value = '{digit}'; el.dispatchEvent(new Event('input', {{bubbles:true}})); }}
                }}''')
            time.sleep(0.2)
        time.sleep(1)
        self.page.keyboard.press('Enter')
        time.sleep(8)
        still_code = self.page.evaluate('() => !!document.querySelector("input[id*=codeEntry]")')
        return not still_code

    def run(self) -> bool:
        from cloakbrowser import launch

        log.info(f"Starting login for {self.email}")
        try:
            launch_kwargs = dict(headless=self.headless, humanize=False, geoip=True)
            if self.proxy:
                launch_kwargs["proxy"] = self.proxy

            self.browser = launch(**launch_kwargs)
            self.page = self.browser.new_page()

            log.info("[1] Opening login...")
            self.page.goto('https://login.live.com/', timeout=30000)
            time.sleep(10)
            self.page.wait_for_selector('#usernameEntry, input[type="email"]', timeout=15000)

            log.info(f"[2] Entering email: {self.email}")
            self._fill(self.email, '#usernameEntry', '#i0116', 'input[type="email"]')
            time.sleep(0.5)
            self._submit()
            time.sleep(8)

            text = self._text(600)
            has_pass = self.page.evaluate('() => !!document.querySelector("input[type=password]")')

            if has_pass:
                log.info("[3] Password field found directly")
                self.page.fill('input[type="password"]', self.password)
                time.sleep(0.5)
                self._submit()
                time.sleep(8)
            else:
                masked = re.findall(r'([a-z0-9.]+\*+@[a-z0-9.-]+\.[a-z]{2,})', text, re.IGNORECASE)
                if masked:
                    log.info(f"[3] Recovery required: {masked[0]}")
                    if not self._handle_recovery(masked[0]):
                        return False
                else:
                    log.error(f"[3] Unknown state: {text[:200]}")
                    return False

            log.info("[4] Navigating to Outlook...")
            self.page.goto('https://outlook.live.com/mail/0/inbox', timeout=30000)
            time.sleep(15)

            url = self.page.url
            text = self._text(500)
            self._screenshot("outlook_final")

            if 'outlook.live.com/mail' in url and 'Sign in' not in text[:100] and 'サインイン' not in text[:50]:
                log.info("=== LOGIN SUCCESSFUL! ===")
                emails = self.page.evaluate('''() => {
                    const items = document.querySelectorAll('[role="option"], [role="row"]');
                    return Array.from(items).slice(0, 5).map(el => el.innerText?.trim()?.substring(0, 120));
                }''')
                for e in emails:
                    if e:
                        log.info(f"  {e[:100]}")
                return True
            else:
                log.error(f"Failed. URL: {url}")
                return False

        except Exception as e:
            log.error(f"Login failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            if self.browser:
                self.browser.close()

    def _handle_recovery(self, masked: str) -> bool:
        matches = self.recovery_mgr.match_masked(masked)
        if not matches:
            log.error(f"  No recovery email match for: {masked}")
            return False

        log.info(f"  Matches: {matches}")

        for idx, recovery_email in enumerate(matches):
            recovery_pwd = self.recovery_mgr.emails.get(recovery_email)
            if not recovery_pwd:
                log.warning(f"  No IMAP password for {recovery_email}")
                continue

            log.info(f"  [{idx+1}/{len(matches)}] Trying: {recovery_email}")

            self._fill(recovery_email, '#proof-confirmation-email-input', 'input[type="text"]')
            time.sleep(0.5)

            log.info("  Clicking 'Send code'...")
            self._click_send_code()
            time.sleep(5)

            self._screenshot(f"send_code_{idx}")

            after_time = time.time()
            code = wait_for_code(recovery_email, recovery_pwd, after_time, max_wait=120)

            if code:
                log.info(f"  Entering code: {code}")
                if self._enter_code(code):
                    log.info("  Code accepted!")
                    self._handle_post_login()
                    return True
                else:
                    log.warning("  Code rejected")
            else:
                log.info("  No code, clicking 'Use your password'...")
                self._click_use_password()
                time.sleep(3)

                has_pass = self.page.evaluate('() => !!document.querySelector("input[type=password]")')
                if has_pass:
                    self.page.fill('input[type="password"]', self.password)
                    time.sleep(0.5)
                    self._submit()
                    time.sleep(8)
                    self._handle_post_login()
                    return True
                else:
                    log.warning("  'Use your password' didn't work")

            if idx < len(matches) - 1:
                log.info("  Restarting login...")
                self.page.goto('https://login.live.com/', timeout=30000)
                time.sleep(10)
                self._fill(self.email, '#usernameEntry', '#i0116', 'input[type="email"]')
                time.sleep(0.5)
                self._submit()
                time.sleep(8)

        log.error("  All recovery emails failed")
        return False

    def _handle_post_login(self):
        for _ in range(5):
            time.sleep(3)
            text = self._text(200)

            if 'プライバシー' in text[:80] or 'privacy notice' in text.lower()[:80]:
                log.info("  Privacy notice → OK")
                try:
                    self.page.click('button:has-text("OK")', timeout=3000)
                except:
                    pass
                continue

            if 'サインイン' in text[:50] and ('はい' in text or 'Yes' in text):
                log.info("  Stay signed in → Yes")
                try:
                    self.page.click('#idSIButton9, button:has-text("はい")', timeout=3000)
                except:
                    pass
                continue

            if 'パスキー' in text or 'passkey' in text.lower():
                log.info("  Passkey → skip")
                break

            break


def main():
    parser = argparse.ArgumentParser(description='Outlook Auto Login')
    parser.add_argument('--email', required=True, help='Outlook email')
    parser.add_argument('--pass', dest='password', required=True, help='Outlook password')
    parser.add_argument('--config', default=str(SCRIPT_DIR / "config.json"), help='Config file path')
    parser.add_argument('--headless', action='store_true', default=True)
    parser.add_argument('--headed', action='store_true')
    parser.add_argument('--proxy', default=None, help='Override proxy URL')

    args = parser.parse_args()

    config = load_config(Path(args.config))
    proxy = args.proxy or get_proxy(config)
    recovery_mgr = RecoveryEmailManager(config=config)

    outlook = OutlookLogin(
        email_addr=args.email, password=args.password,
        recovery_mgr=recovery_mgr,
        headless=not args.headed, proxy=proxy
    )
    success = outlook.run()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
