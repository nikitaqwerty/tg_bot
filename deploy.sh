#!/bin/bash

# Deployment script for Telegram Event Bot
# This script deploys the bot to a remote Ubuntu server

set -e

# Configuration
REMOTE_HOST="213.171.5.251"
REMOTE_USER="root"
REMOTE_PATH="/opt/event-telegram-bot"
PROJECT_NAME="event-telegram-bot"

echo "🚀 Starting deployment of Telegram Event Bot..."

# Create project directory on remote server
echo "📁 Creating project directory on remote server..."
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "mkdir -p ${REMOTE_PATH}"

# Copy files to remote server (excluding database and unnecessary files)
echo "📤 Copying project files to remote server..."
echo "⚠️  Excluding database files to preserve production data..."
rsync -avz --progress \
  --exclude 'data/' \
  --exclude '*.db' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  --exclude 'bot.log' \
  --exclude '.git/' \
  --exclude '.gitignore' \
  --exclude 'venv/' \
  --exclude '.venv/' \
  --exclude '*.swp' \
  --exclude '*.swo' \
  -e "ssh -o StrictHostKeyChecking=no" \
  . ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/

# Connect to remote server and setup
echo "🔧 Setting up Docker and deploying on remote server..."
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << EOF
    set -e

    echo "📦 Installing Docker if not present..."
    if ! command -v docker &> /dev/null; then
        apt-get update
        apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
        echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \$(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
        apt-get update
        apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
        systemctl start docker
        systemctl enable docker
    fi

    echo "🐳 Installing Docker Compose if not present..."
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        curl -L "https://github.com/docker/compose/releases/download/v2.12.2/docker-compose-\$(uname -s)-\$(uname -m)" -o /usr/local/bin/docker-compose
        chmod +x /usr/local/bin/docker-compose
    fi

    cd ${REMOTE_PATH}

    echo "🔧 Ensuring data directory exists..."
    mkdir -p data
    
    # Backup database if it exists
    if [ -f data/events.db ]; then
        echo "💾 Backing up existing database..."
        cp data/events.db data/events.db.backup.\$(date +%Y%m%d_%H%M%S)
        echo "✅ Database backed up successfully"
        # Keep only last 5 backups
        ls -t data/events.db.backup.* 2>/dev/null | tail -n +6 | xargs rm -f 2>/dev/null || true
    else
        echo "ℹ️  No existing database found (first deployment)"
    fi

    echo "⚙️  Setting up environment file..."
    if [ ! -f .env ]; then
        echo "⚠️  .env file not found. Please create one with your bot configuration:"
        echo "   BOT_TOKEN=your_bot_token"
        echo "   ADMIN_IDS=your_admin_ids"
        echo "   CHANNEL_ID=your_channel_id"
        echo ""
        echo "You can copy from config.env as a template:"
        cp config.env .env
        echo "✅ Created .env file from template. Please edit it with your actual values."
        exit 1
    fi

    echo "🏗️  Building and starting the bot..."
    if command -v docker-compose &> /dev/null; then
        docker-compose down || true
        docker-compose build --no-cache
        docker-compose up -d
    else
        docker compose down || true
        docker compose build --no-cache
        docker compose up -d
    fi

    echo "⏳ Waiting for bot to start..."
    sleep 10

    echo "📊 Checking deployment status..."
    if command -v docker-compose &> /dev/null; then
        docker-compose ps
        docker-compose logs --tail=20
    else
        docker compose ps
        docker compose logs --tail=20
    fi

    echo "🌐 Bot health check..."
    if curl -f http://localhost:8080 > /dev/null 2>&1; then
        echo "✅ Bot is running and healthy!"
    else
        echo "⚠️  Bot may not be fully started yet. Check logs with:"
        echo "   docker-compose logs -f"
    fi
EOF

echo "✅ Deployment completed!"
echo ""
echo "📋 Useful commands:"
echo "  SSH into server: ssh root@${REMOTE_HOST}"
echo "  View logs: docker-compose logs -f"
echo "  Restart bot: docker-compose restart"
echo "  Stop bot: docker-compose down"
echo "  Update bot: ./deploy.sh"
echo ""
echo "🌐 Bot health check URL: http://${REMOTE_HOST}:8080"
echo ""
echo "⚠️  IMPORTANT: Make sure to update the .env file on the server with your actual bot credentials!"
