"""
Batch Outlook Login — Process multiple accounts from accounts.json or accounts.txt.

Usage:
    python batch_login.py
    python batch_login.py --config config.json
    python batch_login.py --accounts accounts.txt
"""

import sys
import json
import time
import logging
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from outlook_login import OutlookLogin, RecoveryEmailManager, load_config, get_proxy

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("batch")

SCRIPT_DIR = Path(__file__).parent


def load_accounts(source: str = None) -> list[tuple[str, str]]:
    """Load accounts from .txt or .json file."""
    if source is None:
        # Try json first, then txt
        json_path = SCRIPT_DIR / "accounts.json"
        txt_path = SCRIPT_DIR / "accounts.txt"
        if json_path.exists():
            source = str(json_path)
        elif txt_path.exists():
            source = str(txt_path)
        else:
            log.error("No accounts file found. Create accounts.json or accounts.txt")
            return []

    path = Path(source)
    if not path.exists():
        log.error(f"Accounts file not found: {source}")
        return []

    if path.suffix == ".json":
        data = json.loads(path.read_text())
        return [(a["email"], a["password"]) for a in data]
    else:
        accounts = []
        for line in path.read_text().strip().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('|', 1)
            if len(parts) == 2:
                accounts.append((parts[0].strip(), parts[1].strip()))
        return accounts


def main():
    parser = argparse.ArgumentParser(description='Batch Outlook Login')
    parser.add_argument('--config', default=str(SCRIPT_DIR / "config.json"), help='Config file path')
    parser.add_argument('--accounts', default=None, help='Accounts file (.txt or .json)')
    parser.add_argument('--proxy', default=None, help='Override proxy URL')

    args = parser.parse_args()

    config = load_config(Path(args.config))
    proxy = args.proxy or get_proxy(config)
    recovery_mgr = RecoveryEmailManager(config=config)

    accounts = load_accounts(args.accounts)
    if not accounts:
        log.error("No accounts to process")
        sys.exit(1)

    log.info(f"Loaded {len(accounts)} accounts")
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
                headless=True, proxy=proxy
            )
            success = outlook.run()
        except Exception as e:
            log.error(f"Exception: {e}")
            success = False

        elapsed = int(time.time() - start)
        status = "✅ SUCCESS" if success else "❌ FAILED"
        results.append({"email": email, "success": success, "elapsed": elapsed})
        log.info(f"Result: {status} ({elapsed}s)")

        if i < len(accounts) - 1:
            time.sleep(3)

    # Summary
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    success_count = sum(1 for r in results if r["success"])
    for r in results:
        icon = "✅" if r["success"] else "❌"
        print(f"  {icon} {r['email']} ({r['elapsed']}s)")

    print(f"\n  {success_count}/{len(results)} accounts logged in successfully")
    print(f"{'='*60}")

    # Save results
    results_file = SCRIPT_DIR / "results.json"
    results_file.write_text(json.dumps(results, indent=2))
    log.info(f"Results saved to {results_file}")


if __name__ == '__main__':
    main()
