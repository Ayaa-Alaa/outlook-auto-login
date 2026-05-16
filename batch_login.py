"""Batch Outlook login - process multiple accounts from accounts.txt."""

import sys
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from outlook_login import OutlookLogin, RecoveryEmailManager, PROXY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("batch")

ACCOUNTS_FILE = Path(__file__).parent / "accounts.txt"


def main():
    accounts = []
    for line in ACCOUNTS_FILE.read_text().strip().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split('|', 1)
        if len(parts) == 2:
            accounts.append((parts[0].strip(), parts[1].strip()))

    log.info(f"Loaded {len(accounts)} accounts")
    recovery_mgr = RecoveryEmailManager()
    results = []

    for i, (email, password) in enumerate(accounts):
        log.info(f"\n{'='*60}")
        log.info(f"[{i+1}/{len(accounts)}] {email}")
        log.info(f"{'='*60}")

        start = time.time()
        try:
            outlook = OutlookLogin(
                email_addr=email, password=password,
                recovery_mgr=recovery_mgr,
                headless=True, proxy=PROXY
            )
            success = outlook.run()
        except Exception as e:
            log.error(f"Exception: {e}")
            success = False

        elapsed = int(time.time() - start)
        status = "✅ SUCCESS" if success else "❌ FAILED"
        results.append((email, status, elapsed))
        log.info(f"Result: {status} ({elapsed}s)")

        if i < len(accounts) - 1:
            time.sleep(3)

    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    success_count = 0
    for email, status, elapsed in results:
        print(f"  {status} {email} ({elapsed}s)")
        if "SUCCESS" in status:
            success_count += 1

    print(f"\n  {success_count}/{len(results)} accounts logged in successfully")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
