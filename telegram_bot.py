"""
Outlook Auto Login - Telegram Bot v2
Menu-driven interface with inline keyboards. No need to type commands repeatedly.

Usage:
    python telegram_bot.py
"""

import json
import os
import sys
import asyncio
import logging
import time
import random
from pathlib import Path
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
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

from dotenv import load_dotenv
load_dotenv(SCRIPT_DIR / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USERS = os.getenv("TELEGRAM_ALLOWED_USERS", "")
WEBSHARE_API_BASE = "https://proxy.webshare.io/api/v2"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("tg_bot")

# ─── State ────────────────────────────────────────────────────────────
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
        "proxy_mode": "manual",
        "webshare_api_key": "",
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


# ─── Auth ─────────────────────────────────────────────────────────────
def is_allowed(user_id: int) -> bool:
    if not ALLOWED_USERS:
        return True
    allowed = [int(x.strip()) for x in ALLOWED_USERS.split(",") if x.strip()]
    return user_id in allowed


async def check_auth(update: Update) -> bool:
    uid = update.effective_user.id
    if update.callback_query:
        uid = update.callback_query.from_user.id
    if not is_allowed(uid):
        target = update.callback_query or update.message
        await target.reply_text("❌ Unauthorized")
        return False
    return True


# ─── Keyboard builders ────────────────────────────────────────────────
def kb_main() -> InlineKeyboardMarkup:
    cfg = get_config()
    accounts = get_accounts()
    recovery_count = len(cfg.get("recovery_emails", {}))
    proxy_set = bool(cfg.get("proxy_url"))
    results = get_results()

    proxy_icon = "🟢" if proxy_set else "🔴"
    accounts_icon = f"🟢 {len(accounts)}" if accounts else "🔴 0"
    recovery_icon = f"🟢 {recovery_count}" if recovery_count else "🔴 0"

    keyboard = [
        [
            InlineKeyboardButton(f"📧 Akun ({len(accounts)})", callback_data="menu_accounts"),
            InlineKeyboardButton(f"🔑 Recovery ({recovery_count})", callback_data="menu_recovery"),
        ],
        [
            InlineKeyboardButton(f"{proxy_icon} Proxy", callback_data="menu_proxy"),
            InlineKeyboardButton("🚀 Run", callback_data="menu_run"),
        ],
        [
            InlineKeyboardButton("📊 Report", callback_data="show_report"),
            InlineKeyboardButton("⚙️ Status", callback_data="show_status"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def kb_accounts() -> InlineKeyboardMarkup:
    accounts = get_accounts()
    keyboard = []

    for a in accounts:
        email = a["email"]
        short = email.split("@")[0][:15]
        keyboard.append([
            InlineKeyboardButton(f"📧 {short}...", callback_data=f"noop"),
            InlineKeyboardButton("🗑️", callback_data=f"account_del|{email}"),
        ])

    keyboard.append([
        InlineKeyboardButton("➕ Tambah Satu", callback_data="account_add"),
        InlineKeyboardButton("📄 Upload File", callback_data="account_batch"),
    ])
    keyboard.append([InlineKeyboardButton("🔙 Menu Utama", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)


def kb_recovery() -> InlineKeyboardMarkup:
    cfg = get_config()
    emails = cfg.get("recovery_emails", {})
    keyboard = []

    for email in emails:
        short = email[:20]
        keyboard.append([
            InlineKeyboardButton(f"🔑 {short}", callback_data="noop"),
            InlineKeyboardButton("🗑️", callback_data=f"recovery_del|{email}"),
        ])

    keyboard.append([InlineKeyboardButton("➕ Tambah Recovery", callback_data="recovery_add")])
    keyboard.append([InlineKeyboardButton("🔙 Menu Utama", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)


def kb_proxy() -> InlineKeyboardMarkup:
    cfg = get_config()
    mode = cfg.get("proxy_mode", "manual")
    has_ws_key = bool(cfg.get("webshare_api_key"))
    proxy_set = bool(cfg.get("proxy_url"))

    status = "🟢 Set" if proxy_set else "🔴 Belum"
    proxy_url = cfg.get("proxy_url", "-")
    display = proxy_url[:40] + "..." if len(proxy_url) > 40 else proxy_url

    keyboard = [
        [InlineKeyboardButton(f"Status: {status}", callback_data="noop")],
        [InlineKeyboardButton(f"📍 {display}", callback_data="noop")],
        [InlineKeyboardButton("✏️ Set Manual", callback_data="proxy_manual")],
        [InlineKeyboardButton("📡 Webshare API (fetch)", callback_data="proxy_webshare")],
        [InlineKeyboardButton("🔄 Webshare Rotating", callback_data="proxy_rotate")],
        [InlineKeyboardButton("❌ Clear Proxy", callback_data="proxy_clear")],
        [InlineKeyboardButton("🔙 Menu Utama", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def kb_run() -> InlineKeyboardMarkup:
    accounts = get_accounts()
    cfg = get_config()
    proxy_ok = bool(cfg.get("proxy_url"))
    recovery_ok = bool(cfg.get("recovery_emails"))

    can_run = accounts and proxy_ok and recovery_ok

    keyboard = []
    if can_run:
        keyboard.append([InlineKeyboardButton(f"🚀 Run Semua ({len(accounts)} akun)", callback_data="run_all")])
        for a in accounts:
            short = a["email"].split("@")[0][:15]
            keyboard.append([
                InlineKeyboardButton(f"▶️ {short}...", callback_data=f"run_one|{a['email']}")
            ])
    else:
        reasons = []
        if not accounts:
            reasons.append("❌ Belum ada akun")
        if not proxy_ok:
            reasons.append("❌ Proxy belum diset")
        if not recovery_ok:
            reasons.append("❌ Recovery email belum diset")
        for r in reasons:
            keyboard.append([InlineKeyboardButton(r, callback_data="noop")])

    keyboard.append([InlineKeyboardButton("🔙 Menu Utama", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)


# ─── Menu screens ─────────────────────────────────────────────────────
async def show_main(update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
    cfg = get_config()
    accounts = get_accounts()
    results = get_results()

    success_last = sum(1 for r in results if r.get("success")) if results else 0
    proxy_mode = cfg.get("proxy_mode", "-")

    text = (
        "🔐 *Outlook Auto Login*\n\n"
        f"📧 Akun: *{len(accounts)}*\n"
        f"🔑 Recovery: *{len(cfg.get('recovery_emails', {}))}*\n"
        f"🌐 Proxy: *{proxy_mode}*\n"
        f"📊 Last run: *{success_last}/{len(results)}* berhasil\n\n"
        "Pilih menu:"
    )

    if edit and update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_main()
        )
    else:
        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_main()
        )


async def show_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = get_accounts()
    if not accounts:
        text = "📭 *Belum ada akun*\n\nKlik tombol di bawah untuk tambah."
    else:
        text = f"📧 *Daftar Akun ({len(accounts)}):*\n\n"
        for i, a in enumerate(accounts, 1):
            text += f"{i}. `{a['email']}`\n"
        text += "\n🗑️ Klik × untuk hapus"

    await update.callback_query.edit_message_text(
        text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_accounts()
    )


async def show_recovery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = get_config()
    emails = cfg.get("recovery_emails", {})
    if not emails:
        text = "🔑 *Belum ada recovery email*\n\nGmail accounts yang dipakai sebagai recovery email Outlook."
    else:
        text = f"🔑 *Recovery Emails ({len(emails)}):*\n\n"
        for email in emails:
            text += f"• `{email}`\n"
        text += "\n🗑️ Klik × untuk hapus"

    await update.callback_query.edit_message_text(
        text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_recovery()
    )


async def show_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = get_config()
    proxy_url = cfg.get("proxy_url", "")
    mode = cfg.get("proxy_mode", "-")
    ws_count = len(cfg.get("webshare_proxies", []))

    display = proxy_url if proxy_url else "Belum diset"
    if len(display) > 50:
        display = display[:50] + "..."

    text = (
        "🌐 *Proxy Settings*\n\n"
        f"Mode: *{mode}*\n"
        f"Current: `{display}`\n"
    )
    if ws_count:
        text += f"Webshare pool: *{ws_count} proxy*\n"
    text += "\nPilih opsi:"

    await update.callback_query.edit_message_text(
        text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_proxy()
    )


async def show_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = get_accounts()
    cfg = get_config()
    proxy_ok = bool(cfg.get("proxy_url"))
    recovery_ok = bool(cfg.get("recovery_emails"))

    text = "🚀 *Jalankan Login*\n\n"

    if accounts and proxy_ok and recovery_ok:
        text += f"📧 Akun: *{len(accounts)}*\n"
        text += f"⏱️ Est: *~{len(accounts) * 3} min*\n\n"
        text += "Pilih:"
    else:
        text += "⚠️ *Belum siap:*\n"
        if not accounts:
            text += "• ❌ Tambah akun dulu\n"
        if not proxy_ok:
            text += "• ❌ Set proxy dulu\n"
        if not recovery_ok:
            text += "• ❌ Tambah recovery email dulu\n"

    await update.callback_query.edit_message_text(
        text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_run()
    )


# ─── Callback handlers ────────────────────────────────────────────────
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    query = update.callback_query
    data = query.data

    # ─── Navigation ───
    if data == "main_menu":
        await query.answer()
        await show_main(update, context, edit=True)

    elif data == "noop":
        await query.answer()

    # ─── Accounts ───
    elif data == "menu_accounts":
        await query.answer()
        await show_accounts(update, context)

    elif data == "account_add":
        await query.answer()
        await query.edit_message_text(
            "📧 *Tambah Akun*\n\n"
            "Kirim dalam format:\n"
            "`email@outlook.com|password`\n\n"
            "Contoh:\n"
            "`user@outlook.com|MyPass123`\n\n"
            "Ketik /cancel untuk batal.",
            parse_mode=ParseMode.MARKDOWN
        )
        context.user_data["waiting_for"] = "add_account"

    elif data == "account_batch":
        await query.answer()
        await query.edit_message_text(
            "📄 *Upload Batch Akun*\n\n"
            "Kirim file `.txt` dengan format:\n"
            "```\nemail1@outlook.com|password1\nemail2@outlook.com|password2\n```\n\n"
            "Atau langsung paste list di chat:\n"
            "```\nemail1@outlook.com|pass1\nemail2@outlook.com|pass2\n```\n\n"
            "⚠️ Akun yang sudah ada akan di-skip.\n\n"
            "Ketik /cancel untuk batal.",
            parse_mode=ParseMode.MARKDOWN
        )
        context.user_data["waiting_for"] = "add_batch"

    elif data.startswith("account_del|"):
        email = data.split("|", 1)[1]
        accounts = get_accounts()
        accounts = [a for a in accounts if a["email"] != email]
        save_accounts(accounts)
        await query.answer(f"🗑️ {email} dihapus")
        await show_accounts(update, context)

    # ─── Recovery ───
    elif data == "menu_recovery":
        await query.answer()
        await show_recovery(update, context)

    elif data == "recovery_add":
        await query.answer()
        await query.edit_message_text(
            "🔑 *Tambah Recovery Email*\n\n"
            "Kirim dalam format:\n"
            "`email@gmail.com:app_password`\n\n"
            "App password: https://myaccount.google.com/apppasswords\n\n"
            "Ketik /cancel untuk batal.",
            parse_mode=ParseMode.MARKDOWN
        )
        context.user_data["waiting_for"] = "add_recovery"

    elif data.startswith("recovery_del|"):
        email = data.split("|", 1)[1]
        cfg = get_config()
        cfg.get("recovery_emails", {}).pop(email, None)
        save_config(cfg)
        await query.answer(f"🗑️ {email} dihapus")
        await show_recovery(update, context)

    # ─── Proxy ───
    elif data == "menu_proxy":
        await query.answer()
        await show_proxy(update, context)

    elif data == "proxy_manual":
        await query.answer()
        await query.edit_message_text(
            "✏️ *Set Proxy Manual*\n\n"
            "Kirim proxy URL:\n"
            "`http://user:pass@host:port`\n"
            "atau `socks5://user:pass@host:port`\n\n"
            "Ketik /cancel untuk batal.",
            parse_mode=ParseMode.MARKDOWN
        )
        context.user_data["waiting_for"] = "proxy_manual"

    elif data == "proxy_webshare":
        await query.answer()
        cfg = get_config()
        if not cfg.get("webshare_api_key"):
            await query.edit_message_text(
                "🔑 *Webshare API Key*\n\n"
                "Kirim API key dari https://www.webshare.io/\n"
                "Dashboard → API → API Key\n\n"
                "Ketik /cancel untuk batal.",
                parse_mode=ParseMode.MARKDOWN
            )
            context.user_data["waiting_for"] = "webshare_api_key"
        else:
            await query.edit_message_text("🔄 Fetching proxies...")
            await _fetch_webshare(query, cfg)

    elif data == "proxy_rotate":
        await query.answer()
        cfg = get_config()
        proxies = cfg.get("webshare_proxies", [])
        if not proxies:
            await query.edit_message_text(
                "❌ Belum ada proxy pool.\n\nKlik 📡 Webshare API untuk fetch dulu.",
                reply_markup=kb_proxy()
            )
            return
        p = random.choice(proxies)
        proxy_url = f"http://{p['username']}:{p['password']}@{p['host']}:{p['port']}"
        cfg["proxy_url"] = proxy_url
        cfg["proxy_mode"] = "webshare_rotate"
        save_config(cfg)
        await show_proxy(update, context)

    elif data == "proxy_clear":
        cfg = get_config()
        cfg["proxy_url"] = ""
        cfg["proxy_mode"] = "manual"
        save_config(cfg)
        await query.answer("🗑️ Proxy di-clear")
        await show_proxy(update, context)

    # ─── Run ───
    elif data == "menu_run":
        await query.answer()
        await show_run(update, context)

    elif data == "run_all":
        await query.answer()
        accounts = get_accounts()
        cfg = get_config()
        await query.edit_message_text(
            f"📋 *Pre-Run Report*\n\n"
            f"📧 Akun: *{len(accounts)}*\n"
            f"🌐 Proxy: `{cfg['proxy_url'][:40]}...`\n"
            f"🔑 Recovery: *{len(cfg.get('recovery_emails', {}))}*\n"
            f"⏱️ Est: *~{len(accounts) * 3} min*\n\n"
            f"🚀 Memulai proses...",
            parse_mode=ParseMode.MARKDOWN
        )
        await _run_batch(update, context, accounts, cfg)

    elif data.startswith("run_one|"):
        await query.answer()
        email = data.split("|", 1)[1]
        accounts = [a for a in get_accounts() if a["email"] == email]
        cfg = get_config()
        if accounts:
            await query.edit_message_text(
                f"🚀 Login `{email}`...",
                parse_mode=ParseMode.MARKDOWN
            )
            await _run_batch(update, context, accounts, cfg)

    # ─── Report & Status ───
    elif data == "show_report":
        await query.answer()
        results = get_results()
        if not results:
            await query.edit_message_text(
                "📭 Belum ada hasil. Jalankan /run dulu.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu Utama", callback_data="main_menu")]])
            )
            return
        success = sum(1 for r in results if r.get("success"))
        text = f"📊 *Last Report* ({len(results)} akun)\n\n"
        for r in results:
            icon = "✅" if r.get("success") else "❌"
            text += f"{icon} `{r['email']}`\n"
        text += f"\n✅ {success}/{len(results)} berhasil"
        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu Utama", callback_data="main_menu")]])
        )

    elif data == "show_status":
        await query.answer()
        if is_running:
            count = len(last_results)
            text = f"🔄 *Running* — {count} akun selesai"
        else:
            text = "💤 Idle — tidak ada proses"
        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu Utama", callback_data="main_menu")]])
        )


# ─── Batch account processor ─────────────────────────────────────────
async def _process_batch_text(text: str) -> str:
    """Process pasted or uploaded batch account list."""
    accounts = get_accounts()
    existing = {a["email"] for a in accounts}

    added = 0
    skipped = 0
    errors = []

    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|", 1)
        if len(parts) != 2:
            errors.append(line)
            continue
        email, password = parts[0].strip(), parts[1].strip()
        if not email or not password:
            errors.append(line)
            continue
        if email in existing:
            skipped += 1
            continue
        accounts.append({"email": email, "password": password, "added": datetime.now().isoformat()})
        existing.add(email)
        added += 1

    save_accounts(accounts)

    result = f"📄 *Batch Upload Result*\n\n"
    result += f"✅ Ditambah: *{added}*\n"
    if skipped:
        result += f"⏭️ Skip (sudah ada): *{skipped}*\n"
    if errors:
        result += f"❌ Error format: *{len(errors)}*\n"
        for e in errors[:5]:
            result += f"   `{e[:40]}`\n"
        if len(errors) > 5:
            result += f"   ... +{len(errors)-5} lagi\n"
    result += f"\n📧 Total akun: *{len(accounts)}*"
    return result


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uploaded .txt files for batch account import."""
    if not await check_auth(update):
        return

    waiting = context.user_data.get("waiting_for")
    if waiting != "add_batch":
        await update.message.reply_text(
            "📄 Untuk upload file, klik 📄 Upload File di menu Akun dulu.",
            reply_markup=kb_main()
        )
        return

    doc = update.message.document
    if not doc.file_name.endswith(".txt"):
        await update.message.reply_text("❌ File harus .txt")
        return

    file = await doc.get_file()
    content = await file.download_as_bytearray()
    text = content.decode("utf-8", errors="ignore")

    result = await _process_batch_text(text)
    context.user_data.pop("waiting_for", None)
    await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_main())


# ─── Text input handler ───────────────────────────────────────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    waiting = context.user_data.get("waiting_for")
    if not waiting:
        await show_main(update, context)
        return

    text = update.message.text.strip()

    if text.startswith("/cancel"):
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text("❌ Dibatalkan.", reply_markup=kb_main())
        return

    # ─── Add account ───
    if waiting == "add_account":
        parts = text.split("|", 1)
        if len(parts) != 2:
            await update.message.reply_text("❌ Format: `email|password`", parse_mode=ParseMode.MARKDOWN)
            return
        email, password = parts[0].strip(), parts[1].strip()
        accounts = get_accounts()
        if any(a["email"] == email for a in accounts):
            await update.message.reply_text(f"⚠️ `{email}` sudah ada.", parse_mode=ParseMode.MARKDOWN)
            return
        accounts.append({"email": email, "password": password, "added": datetime.now().isoformat()})
        save_accounts(accounts)
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text(
            f"✅ `{email}` ditambahkan (total: {len(accounts)})",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_main()
        )

    # ─── Add batch (paste) ───
    elif waiting == "add_batch":
        result = await _process_batch_text(text)
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_main())

    # ─── Add recovery ───
    elif waiting == "add_recovery":
        parts = text.split(":", 1)
        if len(parts) != 2:
            await update.message.reply_text("❌ Format: `email@gmail.com:app_password`", parse_mode=ParseMode.MARKDOWN)
            return
        email, app_pass = parts[0].strip(), parts[1].strip()
        cfg = get_config()
        cfg.setdefault("recovery_emails", {})[email] = app_pass
        save_config(cfg)
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text(
            f"✅ `{email}` ditambahkan (total: {len(cfg['recovery_emails'])})",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_main()
        )

    # ─── Proxy manual ───
    elif waiting == "proxy_manual":
        if not (text.startswith("http://") or text.startswith("socks5://")):
            await update.message.reply_text("❌ Format: `http://user:pass@host:port`", parse_mode=ParseMode.MARKDOWN)
            return
        cfg = get_config()
        cfg["proxy_url"] = text
        cfg["proxy_mode"] = "manual"
        save_config(cfg)
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text(
            f"✅ Proxy diset:\n`{text}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_main()
        )

    # ─── Webshare API key ───
    elif waiting == "webshare_api_key":
        cfg = get_config()
        cfg["webshare_api_key"] = text
        save_config(cfg)
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text("🔄 API key disimpan. Fetching proxies...")
        try:
            msg = await update.message.reply_text("⏳ ...")
            # Create a fake query-like object for _fetch_webshare
            class FakeQuery:
                def __init__(self, message):
                    self.message = message
                async def edit_message_text(self, **kwargs):
                    await message.reply_text(**kwargs)
                async def answer(self, *args):
                    pass
            await _fetch_webshare_text(update, context, cfg)
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")


# ─── Webshare fetch ───────────────────────────────────────────────────
async def _fetch_webshare(query, cfg: dict):
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{WEBSHARE_API_BASE}/proxy/list/?mode=direct",
                headers={"Authorization": f"Token {cfg['webshare_api_key']}"},
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
        if proxies:
            p = proxies[0]
            cfg["proxy_url"] = f"http://{p['username']}:{p['password']}@{p['host']}:{p['port']}"
        save_config(cfg)

        text = f"✅ *{len(proxies)} proxy fetched!*\n\n"
        for i, p in enumerate(proxies[:5], 1):
            text += f"{i}. `{p['host']}:{p['port']}` ({p['city']}, {p['country']})\n"
        if len(proxies) > 5:
            text += f"... +{len(proxies)-5} lainnya\n"
        text += f"\nDefault: `{cfg['proxy_url']}`"

        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_proxy()
        )
    except Exception as e:
        await query.edit_message_text(
            f"❌ Error: {e}",
            reply_markup=kb_proxy()
        )


async def _fetch_webshare_text(update, context, cfg: dict):
    """Fetch webshare and send as new message (not edit)."""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{WEBSHARE_API_BASE}/proxy/list/?mode=direct",
                headers={"Authorization": f"Token {cfg['webshare_api_key']}"},
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
        if proxies:
            p = proxies[0]
            cfg["proxy_url"] = f"http://{p['username']}:{p['password']}@{p['host']}:{p['port']}"
        save_config(cfg)

        text = f"✅ *{len(proxies)} proxy fetched!*\n\n"
        for i, p in enumerate(proxies[:5], 1):
            text += f"{i}. `{p['host']}:{p['port']}` ({p['city']}, {p['country']})\n"
        if len(proxies) > 5:
            text += f"... +{len(proxies)-5} lainnya\n"
        text += f"\nDefault: `{cfg['proxy_url']}`"

        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_proxy()
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}", reply_markup=kb_proxy())


# ─── Batch runner ─────────────────────────────────────────────────────
async def _run_batch(update: Update, context: ContextTypes.DEFAULT_TYPE, accounts: list, cfg: dict):
    global is_running, last_results

    chat_id = update.effective_chat.id
    bot = context.bot
    results = []
    start_time = time.time()

    # Write .env from bot config (outlook_login.py reads from .env)
    env_file = SCRIPT_DIR / ".env"
    recovery_str = ",".join(f"{e}:{p}" for e, p in cfg.get("recovery_emails", {}).items())
    env_lines = [
        f"PROXY_URL={cfg.get('proxy_url', '')}",
        f"RECOVERY_EMAILS={recovery_str}",
    ]
    env_file.write_text("\n".join(env_lines) + "\n")
    log.info(f".env written: proxy={'set' if cfg.get('proxy_url') else 'NONE'}, recovery={len(cfg.get('recovery_emails', {}))} emails")

    is_running = True
    last_results = []

    for i, account in enumerate(accounts):
        email = account["email"]
        password = account["password"]

        await bot.send_message(chat_id, f"🔄 [{i+1}/{len(accounts)}] `{email}` — processing...", parse_mode=ParseMode.MARKDOWN)

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
            output = "Timeout"
            success = False
        except Exception as e:
            output = str(e)
            success = False

        elapsed = int(time.time() - start_time)
        result = {"email": email, "success": success, "output": output[-500:], "timestamp": datetime.now().isoformat()}
        results.append(result)
        last_results = results

        status = "✅ SUCCESS" if success else "❌ FAILED"
        await bot.send_message(chat_id, f"{status} `{email}` ({elapsed}s)", parse_mode=ParseMode.MARKDOWN)

    # Summary
    total_time = int(time.time() - start_time)
    success_count = sum(1 for r in results if r["success"])
    summary = (
        f"📊 *BATCH COMPLETE*\n\n"
        f"✅ Success: *{success_count}/{len(results)}*\n"
        f"⏱️ Total: *{total_time}s*\n\n"
    )
    for r in results:
        icon = "✅" if r["success"] else "❌"
        summary += f"{icon} `{r['email']}`\n"

    await bot.send_message(
        chat_id, summary, parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu Utama", callback_data="main_menu")]])
    )

    save_results(results)
    is_running = False


# ─── /start & /cancel ─────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    await show_main(update, context)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("waiting_for", None)
    await update.message.reply_text("❌ Dibatalkan.", reply_markup=kb_main())


# ─── Set bot menu commands ────────────────────────────────────────────
async def post_init(app: Application):
    commands = [
        BotCommand("start", "🏠 Menu utama"),
        BotCommand("cancel", "❌ Batal input"),
    ]
    await app.bot.set_my_commands(commands)
    log.info("✅ Bot menu commands set")


# ─── Main ─────────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set in .env!")
        print("   Add to .env: TELEGRAM_BOT_TOKEN=your_bot_token_here")
        sys.exit(1)

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("🤖 Telegram bot v2 started (menu-driven)!")
    app.run_polling()


if __name__ == "__main__":
    main()
