"""
Outlook Auto Login - Telegram Bot Interface
Control panel untuk manage accounts, proxy, dan jalankan batch login via Telegram.

Usage:
    python telegram_bot.py
"""

import json
import os
import sys
import asyncio
import logging
import time
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from telegram.constants import ParseMode

# ─── Config ───────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

ACCOUNTS_FILE = DATA_DIR / "accounts.json"
CONFIG_FILE = DATA_DIR / "config.json"
RESULTS_FILE = DATA_DIR / "results.json"

# Telegram bot token from .env or hardcoded
from dotenv import load_dotenv
load_dotenv(SCRIPT_DIR / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USERS = os.getenv("TELEGRAM_ALLOWED_USERS", "")  # comma-separated user IDs

WEBHARE_API_BASE = "https://proxy.webshare.io/api/v2"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("tg_bot")

# ─── State ────────────────────────────────────────────────────────────
running_task: Optional[asyncio.Task] = None
running_process: Optional[subprocess.Popen] = None
is_running = False
last_results: list[dict] = []


# ─── Data helpers ─────────────────────────────────────────────────────
def load_json(path: Path, default=None):
    if path.exists():
        return json.loads(path.read_text())
    return default if default is not None else {}


def save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def get_config() -> dict:
    return load_json(CONFIG_FILE, {
        "proxy_url": "",
        "proxy_mode": "manual",  # manual | webshare
        "webshare_api_key": "",
        "webshare_username": "",
        "webshare_proxies": [],
        "recovery_emails": {}
    })


def save_config(cfg: dict):
    save_json(CONFIG_FILE, cfg)


def get_accounts() -> list[dict]:
    return load_json(ACCOUNTS_FILE, [])


def save_accounts(accounts: list[dict]):
    save_json(ACCOUNTS_FILE, accounts)


def get_results() -> list[dict]:
    return load_json(RESULTS_FILE, [])


def save_results(results: list[dict]):
    save_json(RESULTS_FILE, results)


# ─── Auth check ───────────────────────────────────────────────────────
def is_allowed(user_id: int) -> bool:
    if not ALLOWED_USERS:
        return True  # no restriction if not set
    allowed = [int(x.strip()) for x in ALLOWED_USERS.split(",") if x.strip()]
    return user_id in allowed


async def check_auth(update: Update) -> bool:
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized. Add your user ID to TELEGRAM_ALLOWED_USERS in .env")
        return False
    return True


# ─── /start ───────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    cfg = get_config()
    accounts = get_accounts()
    proxy_status = "✅ Set" if cfg.get("proxy_url") else "❌ Not set"
    recovery_count = len(cfg.get("recovery_emails", {}))

    text = (
        "🔐 *Outlook Auto Login Bot*\n\n"
        f"📧 Accounts: *{len(accounts)}*\n"
        f"🌐 Proxy: *{proxy_status}*\n"
        f"🔑 Recovery emails: *{recovery_count}*\n\n"
        "📋 *Commands:*\n"
        "/addaccount `email|pass` — Tambah akun\n"
        "/listaccounts — Lihat daftar akun\n"
        "/removeaccount `email` — Hapus akun\n"
        "/addrecovery `email:app_pass` — Tambah recovery\n"
        "/proxy — Kelola proxy (manual/Webshare)\n"
        "/run — Jalankan batch login\n"
        "/run `email` — Login 1 akun\n"
        "/status — Status proses\n"
        "/report — Hasil terakhir\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ─── /addaccount ──────────────────────────────────────────────────────
async def cmd_addaccount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /addaccount `email@outlook.com|password`", parse_mode=ParseMode.MARKDOWN)
        return

    raw = " ".join(context.args)
    parts = raw.split("|", 1)
    if len(parts) != 2:
        await update.message.reply_text("❌ Format: `email|password`", parse_mode=ParseMode.MARKDOWN)
        return

    email, password = parts[0].strip(), parts[1].strip()
    accounts = get_accounts()

    # Check duplicate
    if any(a["email"] == email for a in accounts):
        await update.message.reply_text(f"⚠️ `{email}` sudah ada. /removeaccount dulu kalau mau update.", parse_mode=ParseMode.MARKDOWN)
        return

    accounts.append({"email": email, "password": password, "added": datetime.now().isoformat()})
    save_accounts(accounts)

    await update.message.reply_text(f"✅ Ditambahkan: `{email}` (total: {len(accounts)})", parse_mode=ParseMode.MARKDOWN)


# ─── /listaccounts ────────────────────────────────────────────────────
async def cmd_listaccounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    accounts = get_accounts()
    if not accounts:
        await update.message.reply_text("📭 Belum ada akun. /addaccount untuk tambah.")
        return

    lines = [f"📧 *Daftar Akun ({len(accounts)}):*\n"]
    for i, a in enumerate(accounts, 1):
        lines.append(f"{i}. `{a['email']}`")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ─── /removeaccount ───────────────────────────────────────────────────
async def cmd_removeaccount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /removeaccount `email@outlook.com`", parse_mode=ParseMode.MARKDOWN)
        return

    email = context.args[0].strip()
    accounts = get_accounts()
    before = len(accounts)
    accounts = [a for a in accounts if a["email"] != email]

    if len(accounts) == before:
        await update.message.reply_text(f"❌ `{email}` tidak ditemukan.", parse_mode=ParseMode.MARKDOWN)
        return

    save_accounts(accounts)
    await update.message.reply_text(f"🗑️ Dihapus: `{email}` (sisa: {len(accounts)})", parse_mode=ParseMode.MARKDOWN)


# ─── /addrecovery ─────────────────────────────────────────────────────
async def cmd_addrecovery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /addrecovery `email@gmail.com:app_password`\n"
            "App password: https://myaccount.google.com/apppasswords",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    raw = " ".join(context.args)
    parts = raw.split(":", 1)
    if len(parts) != 2:
        await update.message.reply_text("❌ Format: `email@gmail.com:app_password`", parse_mode=ParseMode.MARKDOWN)
        return

    email, app_pass = parts[0].strip(), parts[1].strip()
    cfg = get_config()
    cfg.setdefault("recovery_emails", {})[email] = app_pass
    save_config(cfg)

    await update.message.reply_text(
        f"✅ Recovery email ditambah: `{email}` (total: {len(cfg['recovery_emails'])})",
        parse_mode=ParseMode.MARKDOWN
    )


# ─── /proxy ───────────────────────────────────────────────────────────
async def cmd_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    cfg = get_config()
    current = cfg.get("proxy_url", "")
    mode = cfg.get("proxy_mode", "manual")

    text = (
        "🌐 *Proxy Settings*\n\n"
        f"Mode: *{mode}*\n"
        f"Current: `{current or 'not set'}`\n\n"
        "Pilih opsi:"
    )

    keyboard = [
        [InlineKeyboardButton("✏️ Set Manual", callback_data="proxy_manual")],
        [InlineKeyboardButton("🔄 Webshare API", callback_data="proxy_webshare")],
        [InlineKeyboardButton("📡 Webshare Rotating", callback_data="proxy_webshare_rotate")],
        [InlineKeyboardButton("❌ Clear Proxy", callback_data="proxy_clear")],
    ]
    await update.message.reply_text(
        text, parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def proxy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action = query.data

    if action == "proxy_manual":
        await query.edit_message_text(
            "✏️ *Set Proxy Manual*\n\n"
            "Kirim proxy dalam format:\n"
            "`http://user:pass@host:port`\n"
            "atau\n"
            "`socks5://user:pass@host:port`\n\n"
            "Ketik /cancel untuk batal.",
            parse_mode=ParseMode.MARKDOWN
        )
        context.user_data["waiting_for"] = "proxy_manual"

    elif action == "proxy_webshare":
        cfg = get_config()
        api_key = cfg.get("webshare_api_key", "")
        if not api_key:
            await query.edit_message_text(
                "🔑 *Webshare API Key*\n\n"
                "Kirim API key dari https://www.webshare.io/\n"
                "Dapatkan di: Dashboard → API → API Key\n\n"
                "Ketik /cancel untuk batal.",
                parse_mode=ParseMode.MARKDOWN
            )
            context.user_data["waiting_for"] = "webshare_api_key"
        else:
            await _fetch_webshare_proxies(query, cfg)

    elif action == "proxy_webshare_rotate":
        cfg = get_config()
        if not cfg.get("webshare_api_key"):
            await query.edit_message_text("❌ Set Webshare API key dulu. Ketik /proxy → Webshare API")
            return

        proxies = cfg.get("webshare_proxies", [])
        if not proxies:
            await query.edit_message_text("❌ Tidak ada proxy. Ketik /proxy → Webshare API untuk fetch.")
            return

        # Set rotating proxy - pick random one
        import random
        p = random.choice(proxies)
        proxy_url = f"http://{p['username']}:{p['password']}@{p['host']}:{p['port']}"
        cfg["proxy_url"] = proxy_url
        cfg["proxy_mode"] = "webshare_rotate"
        save_config(cfg)

        await query.edit_message_text(
            f"🔄 *Rotating Proxy Aktif*\n\n"
            f"`{proxy_url}`\n\n"
            f"Total pool: {len(proxies)} proxy\n"
            f"Akan rotate otomatis tiap batch.",
            parse_mode=ParseMode.MARKDOWN
        )

    elif action == "proxy_clear":
        cfg = get_config()
        cfg["proxy_url"] = ""
        save_config(cfg)
        await query.edit_message_text("🗑️ Proxy di-clear.")


async def _fetch_webshare_proxies(query, cfg: dict):
    """Fetch proxy list from Webshare API."""
    import httpx

    api_key = cfg["webshare_api_key"]
    await query.edit_message_text("🔄 Fetching proxies dari Webshare...")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{WEBHARE_API_BASE}/proxy/list/?mode=direct",
                headers={"Authorization": f"Token {api_key}"},
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()

        proxies = []
        for p in data.get("results", []):
            if p.get("valid"):
                proxies.append({
                    "id": p["id"],
                    "host": p["proxy_address"],
                    "port": p["port"],
                    "username": p["username"],
                    "password": p["password"],
                    "country": p.get("country_code", ""),
                    "city": p.get("city_name", ""),
                })

        cfg["webshare_proxies"] = proxies
        cfg["proxy_mode"] = "webshare"

        # Set first proxy as default
        if proxies:
            p = proxies[0]
            cfg["proxy_url"] = f"http://{p['username']}:{p['password']}@{p['host']}:{p['port']}"

        save_config(cfg)

        lines = [f"✅ *{len(proxies)} proxy fetched* (valid)\n"]
        for i, p in enumerate(proxies[:5], 1):
            lines.append(f"{i}. `{p['host']}:{p['port']}` ({p['city']}, {p['country']})")
        if len(proxies) > 5:
            lines.append(f"... dan {len(proxies)-5} lainnya")
        lines.append(f"\nDefault: `{cfg['proxy_url']}`")

        await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        await query.edit_message_text(f"❌ Error fetch proxy: {e}")


# ─── Text handler (for proxy input) ───────────────────────────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    waiting = context.user_data.get("waiting_for")
    if not waiting:
        return

    text = update.message.text.strip()

    if text.startswith("/cancel"):
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text("❌ Dibatalkan.")
        return

    if waiting == "proxy_manual":
        if not (text.startswith("http://") or text.startswith("socks5://")):
            await update.message.reply_text("❌ Format salah. Harus `http://...` atau `socks5://...`")
            return
        cfg = get_config()
        cfg["proxy_url"] = text
        cfg["proxy_mode"] = "manual"
        save_config(cfg)
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text(f"✅ Proxy diset:\n`{text}`", parse_mode=ParseMode.MARKDOWN)

    elif waiting == "webshare_api_key":
        cfg = get_config()
        cfg["webshare_api_key"] = text
        save_config(cfg)
        context.user_data.pop("waiting_for", None)

        # Auto-fetch proxies
        cfg = get_config()
        await update.message.reply_text("🔄 API key disimpan. Fetching proxies...")

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{WEBHARE_API_BASE}/proxy/list/?mode=direct",
                    headers={"Authorization": f"Token {text}"},
                    timeout=15
                )
                resp.raise_for_status()
                data = resp.json()

            proxies = []
            for p in data.get("results", []):
                if p.get("valid"):
                    proxies.append({
                        "id": p["id"],
                        "host": p["proxy_address"],
                        "port": p["port"],
                        "username": p["username"],
                        "password": p["password"],
                        "country": p.get("country_code", ""),
                        "city": p.get("city_name", ""),
                    })

            cfg = get_config()
            cfg["webshare_proxies"] = proxies
            cfg["proxy_mode"] = "webshare"
            if proxies:
                p = proxies[0]
                cfg["proxy_url"] = f"http://{p['username']}:{p['password']}@{p['host']}:{p['port']}"
            save_config(cfg)

            lines = [f"✅ *{len(proxies)} proxy fetched!*\n"]
            for i, p in enumerate(proxies[:5], 1):
                lines.append(f"{i}. `{p['host']}:{p['port']}` ({p['city']})")
            if len(proxies) > 5:
                lines.append(f"... +{len(proxies)-5} lainnya")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")


# ─── /run ─────────────────────────────────────────────────────────────
async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_running, running_task, last_results

    if not await check_auth(update):
        return

    if is_running:
        await update.message.reply_text("⚠️ Masih ada proses yang jalan. /status untuk cek.")
        return

    cfg = get_config()
    accounts = get_accounts()

    if not accounts:
        await update.message.reply_text("❌ Belum ada akun. /addaccount dulu.")
        return

    if not cfg.get("proxy_url"):
        await update.message.reply_text("❌ Proxy belum diset. /proxy dulu.")
        return

    if not cfg.get("recovery_emails"):
        await update.message.reply_text("❌ Recovery emails belum diset. /addrecovery dulu.")
        return

    # Filter by email if specified
    target_email = context.args[0].strip() if context.args else None
    if target_email:
        accounts = [a for a in accounts if a["email"] == target_email]
        if not accounts:
            await update.message.reply_text(f"❌ Akun `{target_email}` tidak ditemukan.", parse_mode=ParseMode.MARKDOWN)
            return

    # ─── Pre-run report ───
    report = (
        "📋 *Pre-Run Report*\n\n"
        f"📧 Accounts: *{len(accounts)}*\n"
        f"🌐 Proxy: `{cfg['proxy_url'][:40]}...`\n"
        f"🔑 Recovery: *{len(cfg['recovery_emails'])} emails*\n"
        f"⏱️ Est. time: *~{len(accounts) * 3} min*\n\n"
        "Daftar akun:\n"
    )
    for i, a in enumerate(accounts, 1):
        report += f"  {i}. `{a['email']}`\n"
    report += "\n🚀 Memulai proses..."

    await update.message.reply_text(report, parse_mode=ParseMode.MARKDOWN)

    # Run in background
    is_running = True
    last_results = []
    running_task = asyncio.create_task(_run_batch(update, context, accounts, cfg))


async def _run_batch(update: Update, context: ContextTypes.DEFAULT_TYPE, accounts: list, cfg: dict):
    """Run batch login in background, report per-account."""
    global is_running, last_results

    chat_id = update.effective_chat.id
    bot = context.bot
    results = []
    start_time = time.time()

    # Write temp files for the login script
    env_lines = [
        f"PROXY_URL={cfg['proxy_url']}",
        "RECOVERY_EMAILS=" + ",".join(f"{e}:{p}" for e, p in cfg["recovery_emails"].items())
    ]
    env_file = SCRIPT_DIR / ".env"
    env_content = env_file.read_text() if env_file.exists() else ""

    # Write temp accounts file
    tmp_accounts = DATA_DIR / "run_accounts.txt"
    tmp_accounts.write_text("\n".join(f"{a['email']}|{a['password']}" for a in accounts))

    # Update .env with current config
    lines = []
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if not line.startswith("PROXY_URL=") and not line.startswith("RECOVERY_EMAILS="):
                lines.append(line)
    lines.append(f"PROXY_URL={cfg['proxy_url']}")
    lines.append(f"RECOVERY_EMAILS=" + ",".join(f"{e}:{p}" for e, p in cfg["recovery_emails"].items()))
    env_file.write_text("\n".join(lines) + "\n")

    # Run each account
    for i, account in enumerate(accounts):
        email = account["email"]
        password = account["password"]

        await bot.send_message(chat_id, f"🔄 [{i+1}/{len(accounts)}] `{email}` — processing...", parse_mode=ParseMode.MARKDOWN)

        # Run outlook_login.py as subprocess
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(SCRIPT_DIR / "outlook_login.py"),
                "--email", email, "--pass", password,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(SCRIPT_DIR)
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
            output = stdout.decode() + stderr.decode()
            success = proc.returncode == 0 and "LOGIN SUCCESSFUL" in output

        except asyncio.TimeoutError:
            output = "Timeout after 600s"
            success = False
        except Exception as e:
            output = str(e)
            success = False

        elapsed = int(time.time() - start_time)
        result = {
            "email": email,
            "success": success,
            "output": output[-500:],  # last 500 chars
            "timestamp": datetime.now().isoformat()
        }
        results.append(result)
        last_results = results

        status = "✅ SUCCESS" if success else "❌ FAILED"
        await bot.send_message(
            chat_id,
            f"{status} `{email}` ({elapsed}s total)",
            parse_mode=ParseMode.MARKDOWN
        )

    # ─── Summary ───
    total_time = int(time.time() - start_time)
    success_count = sum(1 for r in results if r["success"])

    summary = (
        f"\n{'='*30}\n"
        f"📊 *BATCH COMPLETE*\n\n"
        f"✅ Success: *{success_count}/{len(results)}*\n"
        f"⏱️ Total time: *{total_time}s*\n\n"
    )
    for r in results:
        icon = "✅" if r["success"] else "❌"
        summary += f"{icon} `{r['email']}`\n"

    await bot.send_message(chat_id, summary, parse_mode=ParseMode.MARKDOWN)

    # Save results
    save_results(results)
    is_running = False
    running_task = None


# ─── /status ──────────────────────────────────────────────────────────
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    if is_running:
        count = len(last_results)
        await update.message.reply_text(f"🔄 *Running* — {count} akun selesai sejauh ini.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("💤 Idle — tidak ada proses yang jalan.")


# ─── /report ──────────────────────────────────────────────────────────
async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    results = get_results()
    if not results:
        await update.message.reply_text("📭 Belum ada hasil. /run dulu.")
        return

    success = sum(1 for r in results if r.get("success"))
    text = f"📊 *Last Report* ({len(results)} akun)\n\n"
    for r in results:
        icon = "✅" if r.get("success") else "❌"
        text += f"{icon} `{r['email']}` — {r.get('timestamp', '?')[:16]}\n"
    text += f"\n✅ {success}/{len(results)} berhasil"

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ─── /cancel ──────────────────────────────────────────────────────────
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("waiting_for", None)
    await update.message.reply_text("❌ Dibatalkan.")


# ─── Main ─────────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set in .env!")
        print("   Add to .env: TELEGRAM_BOT_TOKEN=your_bot_token_here")
        sys.exit(1)

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("addaccount", cmd_addaccount))
    app.add_handler(CommandHandler("listaccounts", cmd_listaccounts))
    app.add_handler(CommandHandler("removeaccount", cmd_removeaccount))
    app.add_handler(CommandHandler("addrecovery", cmd_addrecovery))
    app.add_handler(CommandHandler("proxy", cmd_proxy))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    # Callbacks
    app.add_handler(CallbackQueryHandler(proxy_callback, pattern="^proxy_"))

    # Text handler (for proxy input)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("🤖 Telegram bot started!")
    app.run_polling()


if __name__ == "__main__":
    main()
