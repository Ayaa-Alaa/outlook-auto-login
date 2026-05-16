#!/bin/bash
# Outlook Auto Login — One-line Setup
# Usage: curl -sSL <raw_url> | bash
# Or: git clone ... && cd outlook-auto-login && bash setup.sh

set -e

echo "╔══════════════════════════════════════════╗"
echo "║   Outlook Auto Login — Setup             ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "❌ Python3 not found. Installing..."
    sudo apt update -qq && sudo apt install -y python3 python3-pip python3-venv
fi

PYTHON_VERSION=$(python3 --version | grep -oP '\d+\.\d+')
echo "✅ Python $PYTHON_VERSION"

# Setup venv
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate

# Install deps
echo "📦 Installing dependencies (cloakbrowser, telegram-bot, httpx)..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "✅ Dependencies installed"
echo ""

# ─── .env setup ───
if [ -f ".env" ] && grep -q "TELEGRAM_BOT_TOKEN=" .env; then
    EXISTING_TOKEN=$(grep "^TELEGRAM_BOT_TOKEN=" .env | cut -d'=' -f2)
    if [ "$EXISTING_TOKEN" != "" ] && [ "$EXISTING_TOKEN" != "YOUR_BOT_TOKEN_HERE" ]; then
        echo "✅ .env already configured (token: ${EXISTING_TOKEN:0:10}...)"
        echo ""
        read -p "🔄 Reconfigure? (y/N): " RECONFIG
        if [ "$RECONFIG" != "y" ] && [ "$RECONFIG" != "Y" ]; then
            echo ""
            echo "🚀 Starting bot..."
            exec python3 telegram_bot.py
        fi
    fi
fi

echo "╔══════════════════════════════════════════╗"
echo "║   Configuration                          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Bot token
echo "🤖 Telegram Bot Token"
echo "   Get from @BotFather → /newbot"
read -p "   Token: " BOT_TOKEN
if [ -z "$BOT_TOKEN" ]; then
    echo "❌ Bot token is required!"
    exit 1
fi

# Chat ID
echo ""
echo "💬 Your Telegram Chat ID"
echo "   Get from @userinfobot → /start"
read -p "   Chat ID: " CHAT_ID

# Proxy (optional)
echo ""
echo "🌐 Proxy (optional)"
echo "   Format: http://user:pass@host:port"
echo "   Leave empty to set later via bot /proxy command"
read -p "   Proxy URL: " PROXY_URL

# Write .env
cat > .env << EOF
# Outlook Auto Login - Environment
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_ALLOWED_USERS=$CHAT_ID
PROXY_URL=${PROXY_URL:-}
RECOVERY_EMAILS=
EOF

echo ""
echo "✅ .env created"
echo ""

# ─── Summary ───
echo "╔══════════════════════════════════════════╗"
echo "║   Setup Complete!                        ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "📧 Accounts: 0 (add via bot: /addaccount)"
echo "🔑 Recovery: 0 (add via bot: /addrecovery)"
echo "🌐 Proxy: ${PROXY_URL:-not set (add via bot: /proxy)}"
echo ""
echo "🤖 Bot token: ${BOT_TOKEN:0:10}..."
echo "💬 Chat ID: ${CHAT_ID:-not set}"
echo ""
echo "🚀 Starting Telegram bot..."
echo "   Open Telegram → find your bot → send /start"
echo ""
echo "════════════════════════════════════════════"
echo ""

exec python3 telegram_bot.py
