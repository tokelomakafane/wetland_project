#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Lesotho Wetland Monitoring System — Droplet Setup
#
# One-shot provisioning script for Ubuntu 24.04 DigitalOcean.
#
# Usage:
#   sudo bash deploy.sh [domain]
#
# Examples:
#   sudo bash deploy.sh                    # auto-detect IP
#   sudo bash deploy.sh thuto.co.ls        # use specific domain
#
# What it does:
#   1. System updates + essential packages
#   2. Installs Python 3.12, pip, venv, Nginx, Git
#   3. Creates OS user "wetland" + app directory /opt/wetland
#   4. Clones the repository
#   5. Python venv + pip install
#   6. Creates .env file
#   7. Django setup (migrations, static files)
#   8. Gunicorn systemd service
#   9. Nginx reverse proxy
#  10. Firewall configuration
# ─────────────────────────────────────────────────────────────

set -euo pipefail

# ─── Configuration ─────────────────────────────────────────
APP_NAME="wetland"
APP_DIR="/opt/${APP_NAME}"
APP_USER="wetland"
DOMAIN="${1:-$(curl -s ifconfig.me)}"
REPO_URL="https://github.com/tokelomakafane/wetland_project.git"
BRANCH="feature/community-alerts-and-fixes"

# ─── Colors ────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
    exit 1
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# ─── Banner ────────────────────────────────────────────────
echo ""
echo "╔═════════════════════════════════════════════════════╗"
echo "║  Lesotho Wetland Monitoring — Droplet Setup        ║"
echo "╠═════════════════════════════════════════════════════╣"
echo "║  Domain/IP : ${DOMAIN}"
echo "║  App Dir   : ${APP_DIR}"
echo "║  User      : ${APP_USER}"
echo "╚═════════════════════════════════════════════════════╝"
echo ""

# ─── Check root ────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    log_error "This script must be run as root. Use: sudo bash deploy.sh"
fi

# ─────────────────────────────────────────────────────────────
# 1. System packages
# ─────────────────────────────────────────────────────────────
log "Installing system packages..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv python3-dev \
    git nginx ufw curl wget \
    build-essential libssl-dev libffi-dev

log_success "System packages installed"

# ─────────────────────────────────────────────────────────────
# 2. Firewall
# ─────────────────────────────────────────────────────────────
log "Configuring firewall..."
ufw default deny incoming >/dev/null 2>&1 || true
ufw default allow outgoing >/dev/null 2>&1 || true
ufw allow 22/tcp >/dev/null 2>&1 || true    # SSH
ufw allow 80/tcp >/dev/null 2>&1 || true    # HTTP
ufw allow 443/tcp >/dev/null 2>&1 || true   # HTTPS
ufw --force enable >/dev/null 2>&1 || true

log_success "Firewall configured (SSH, HTTP, HTTPS)"

# ─────────────────────────────────────────────────────────────
# 3. OS user + app directory
# ─────────────────────────────────────────────────────────────
log "Creating application user and directory..."
id -u "${APP_USER}" &>/dev/null || {
    useradd --system --shell /bin/bash --home "${APP_DIR}" "${APP_USER}"
}
mkdir -p "${APP_DIR}"

log_success "User '${APP_USER}' ready"

# ─────────────────────────────────────────────────────────────
# 4. Clone repository
# ─────────────────────────────────────────────────────────────
log "Cloning repository..."
if [ -d "${APP_DIR}/.git" ]; then
    log_warn "Repository already exists, pulling latest..."
    cd "${APP_DIR}"
    git fetch origin
    git reset --hard "origin/${BRANCH}"
else
    git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
fi

log_success "Repository ready at ${APP_DIR}"

# ─────────────────────────────────────────────────────────────
# 5. Python environment
# ─────────────────────────────────────────────────────────────
log "Setting up Python virtual environment..."
cd "${APP_DIR}"

sudo -u "${APP_USER}" python3 -m venv venv
sudo -u "${APP_USER}" bash -c "source venv/bin/activate && \
    pip install --upgrade pip setuptools wheel -q && \
    pip install -r requirements.txt -q && \
    pip install gunicorn python-dotenv -q"

log_success "Python environment configured"

# ─────────────────────────────────────────────────────────────
# 6. Environment file
# ─────────────────────────────────────────────────────────────
log "Creating environment variables..."
if [ ! -f "${APP_DIR}/.env" ]; then
    SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
    
    cat > "${APP_DIR}/.env" <<EOF
# Django Settings
DJANGO_SECRET_KEY=${SECRET}
DOMAIN=${DOMAIN}
DEBUG=False

# Database (SQLite default)
# For production, consider using PostgreSQL

# Email (optional)
# EMAIL=admin@${DOMAIN}

# Earth Engine (optional - add later)
# EE_PROJECT=your-project-id
# EE_SERVICE_ACCOUNT=your-sa@project.iam.gserviceaccount.com
# EE_SERVICE_ACCOUNT_KEY=/opt/wetland/ee-key.json
EOF
    
    chmod 600 "${APP_DIR}/.env"
    log_success "Created .env file"
else
    log_warn ".env already exists, skipping"
fi

# ─────────────────────────────────────────────────────────────
# 7. Django setup
# ─────────────────────────────────────────────────────────────
log "Running Django setup..."
cd "${APP_DIR}"

sudo -u "${APP_USER}" bash -c "source venv/bin/activate && \
    python manage.py migrate && \
    python manage.py seed_users && \
    python manage.py collectstatic --noinput"

log_success "Database migrated, users seeded, static files collected"

# ─────────────────────────────────────────────────────────────
# 8. Gunicorn systemd service
# ─────────────────────────────────────────────────────────────
log "Creating Gunicorn systemd service..."
cat > /etc/systemd/system/wetland.service <<'SYSTEMD'
[Unit]
Description=Lesotho Wetland Monitoring — Gunicorn
After=network.target

[Service]
Type=notify
User=wetland
Group=www-data
WorkingDirectory=/opt/wetland
EnvironmentFile=/opt/wetland/.env
ExecStart=/opt/wetland/venv/bin/gunicorn \
    --workers 3 \
    --worker-class sync \
    --bind unix:/opt/wetland/wetland.sock \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    wetland_project.wsgi:application

Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
SYSTEMD

systemctl daemon-reload
systemctl enable --now wetland

# Wait for socket
sleep 2
if [ -S "${APP_DIR}/wetland.sock" ]; then
    log_success "Gunicorn service running"
else
    log_error "Gunicorn socket not found"
fi

# ─────────────────────────────────────────────────────────────
# 9. Nginx configuration
# ─────────────────────────────────────────────────────────────
log "Configuring Nginx..."

# Remove default site
rm -f /etc/nginx/sites-enabled/default

# Create Nginx config
cat > /etc/nginx/sites-available/wetland <<NGINX
server {
    listen 80;
    server_name ${DOMAIN} www.${DOMAIN};

    client_max_body_size 50M;

    location /static/ {
        alias /opt/wetland/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /opt/wetland/media/;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/opt/wetland/wetland.sock;
        proxy_read_timeout 120s;
        proxy_set_header X-Forwarded-Proto \$http_x_forwarded_proto;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/wetland /etc/nginx/sites-enabled/wetland

# Test and reload
if nginx -t 2>/dev/null; then
    systemctl enable --now nginx
    systemctl reload nginx
    log_success "Nginx configured"
else
    log_error "Nginx configuration test failed"
fi

# ─────────────────────────────────────────────────────────────
# 10. Ownership
# ─────────────────────────────────────────────────────────────
log "Setting permissions..."
chown -R "${APP_USER}:www-data" "${APP_DIR}"
chmod -R 750 "${APP_DIR}"

log_success "Permissions set"

# ─────────────────────────────────────────────────────────────
# Done!
# ─────────────────────────────────────────────────────────────
echo ""
echo "╔═════════════════════════════════════════════════════╗"
echo "║  ✅  Deployment Complete!                          ║"
echo "╠═════════════════════════════════════════════════════╣"
echo "║"
echo "║  Site URL    : http://${DOMAIN}"
echo "║  App Dir     : ${APP_DIR}"
echo "║  .env file   : ${APP_DIR}/.env"
echo "║"
echo "║  Default Users:"
echo "║    admin         / admin"
echo "║    doe_officer   / doe123"
echo "║    dma_officer   / dma123"
echo "║    nul_researcher / nul123"
echo "║    community     / community123"
echo "║"
echo "║  🔐 IMPORTANT - NEXT STEPS:"
echo "║"
echo "║  1. Change all default passwords!"
echo "║     ssh wetland@${DOMAIN}"
echo "║     cd /opt/wetland"
echo "║     source venv/bin/activate"
echo "║     python manage.py changepassword admin"
echo "║"
echo "║  2. Configure Cloudflare DNS (if using):"
echo "║     A record: @ → $(hostname -I | awk '{print $1}')"
echo "║     A record: www → $(hostname -I | awk '{print $1}')"
echo "║     SSL/TLS: Set to 'Full'"
echo "║"
echo "║  3. Enable HTTPS (optional):"
echo "║     sudo certbot --nginx -d ${DOMAIN}"
echo "║"
echo "║  4. View logs:"
echo "║     sudo journalctl -u wetland -f"
echo "║     sudo tail -f /var/log/nginx/error.log"
echo "║"
echo "║  5. Add Earth Engine (optional):"
echo "║     scp ee-key.json wetland@${DOMAIN}:/opt/wetland/"
echo "║     Edit /opt/wetland/.env with EE variables"
echo "║     sudo systemctl restart wetland"
echo "║"
echo "╚═════════════════════════════════════════════════════╝"
echo ""
