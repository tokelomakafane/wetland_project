#!/bin/bash
################################################################################
# Lesotho Wetland Monitoring System — Digital Ocean Deployment Script
# 
# Usage: bash deploy.sh
# 
# Prerequisites:
# 1. Ubuntu 24.04 LTS Digital Ocean droplet
# 2. SSH access as root
# 3. Domain configured in Cloudflare
# 4. Google Earth Engine service account key ready
#
# This script automates:
# - System dependency installation
# - Non-root user creation
# - Firewall configuration
# - Git repository cloning
# - Python environment setup
# - Django configuration
# - Gunicorn systemd service
# - Nginx reverse proxy
################################################################################

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

log_error() {
    echo -e "${RED}✗ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Validation function
validate_input() {
    local input="$1"
    local pattern="$2"
    if [[ ! $input =~ $pattern ]]; then
        log_error "Invalid input: $input"
        return 1
    fi
    return 0
}

################################################################################
# SECTION 1: Pre-deployment Configuration
################################################################################

log "${BLUE}========================================${NC}"
log "${BLUE}Lesotho Wetland Monitoring — Deployment${NC}"
log "${BLUE}========================================${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "This script must be run as root. Use: sudo bash deploy.sh"
    exit 1
fi

# Collect deployment parameters
log "Collecting deployment configuration..."

read -p "Enter the non-root username (default: wetland): " USERNAME
USERNAME=${USERNAME:-wetland}

read -p "Enter your domain (e.g., thuto.co.ls): " DOMAIN
if ! validate_input "$DOMAIN" "^[a-z0-9.-]+\.[a-z]+$"; then
    log_error "Invalid domain format"
    exit 1
fi

read -p "Enter your email for system notifications: " EMAIL
if ! validate_input "$EMAIL" "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"; then
    log_error "Invalid email format"
    exit 1
fi

read -p "Enter Google Earth Engine project name (e.g., tokelo-329815): " EE_PROJECT
read -p "Enter Google Earth Engine service account email: " EE_SERVICE_ACCOUNT
read -p "Enter path to Earth Engine key JSON file on this machine: " EE_KEY_PATH

if [ ! -f "$EE_KEY_PATH" ]; then
    log_error "Earth Engine key file not found: $EE_KEY_PATH"
    exit 1
fi

log_success "Configuration collected"

################################################################################
# SECTION 2: System Dependencies
################################################################################

log "${BLUE}Installing system dependencies...${NC}"

apt-get update
apt-get upgrade -y
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    git \
    nginx \
    ufw \
    curl \
    wget \
    build-essential \
    libssl-dev \
    libffi-dev

log_success "System dependencies installed"

################################################################################
# SECTION 3: Firewall Configuration
################################################################################

log "${BLUE}Configuring firewall...${NC}"

ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp  # SSH
ufw allow 80/tcp  # HTTP
ufw allow 443/tcp # HTTPS
ufw --force enable

log_success "Firewall configured"

################################################################################
# SECTION 4: Create Non-Root User
################################################################################

log "${BLUE}Creating user: $USERNAME${NC}"

if id "$USERNAME" &>/dev/null; then
    log_warning "User $USERNAME already exists, skipping user creation"
else
    adduser --disabled-password --gecos "" "$USERNAME"
    usermod -aG sudo "$USERNAME"
    log_success "User $USERNAME created with sudo access"
fi

# Create app directory
APP_DIR="/home/$USERNAME/app"
mkdir -p "$APP_DIR"
chown -R "$USERNAME:$USERNAME" "$APP_DIR"

################################################################################
# SECTION 5: Clone Repository
################################################################################

log "${BLUE}Cloning repository...${NC}"

cd "$APP_DIR"
sudo -u "$USERNAME" git clone https://github.com/tokelomakafane/wetland_project.git . 2>/dev/null || {
    log_warning "Repository already exists or clone failed, skipping..."
}

log_success "Repository ready at $APP_DIR"

################################################################################
# SECTION 6: Python Virtual Environment
################################################################################

log "${BLUE}Setting up Python virtual environment...${NC}"

cd "$APP_DIR"
sudo -u "$USERNAME" python3 -m venv venv
sudo -u "$USERNAME" bash -c "source venv/bin/activate && pip install --upgrade pip setuptools wheel"
sudo -u "$USERNAME" bash -c "source venv/bin/activate && pip install -r requirements.txt"
sudo -u "$USERNAME" bash -c "source venv/bin/activate && pip install gunicorn python-dotenv"

log_success "Python environment configured"

################################################################################
# SECTION 7: Environment Variables
################################################################################

log "${BLUE}Creating environment variables...${NC}"

# Generate Django secret key
DJANGO_SECRET_KEY=$(python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")

# Create .env file
ENV_FILE="$APP_DIR/.env"
cat > "$ENV_FILE" << EOF
DJANGO_SECRET_KEY=$DJANGO_SECRET_KEY
EE_PROJECT=$EE_PROJECT
EE_SERVICE_ACCOUNT=$EE_SERVICE_ACCOUNT
EE_SERVICE_ACCOUNT_KEY=/home/$USERNAME/ee-key.json
DOMAIN=$DOMAIN
EMAIL=$EMAIL
EOF

chown "$USERNAME:$USERNAME" "$ENV_FILE"
chmod 600 "$ENV_FILE"

log_success "Environment file created: $ENV_FILE"

################################################################################
# SECTION 8: Copy Earth Engine Key
################################################################################

log "${BLUE}Copying Earth Engine service account key...${NC}"

EE_KEY_DEST="/home/$USERNAME/ee-key.json"
cp "$EE_KEY_PATH" "$EE_KEY_DEST"
chown "$USERNAME:$USERNAME" "$EE_KEY_DEST"
chmod 400 "$EE_KEY_DEST"

log_success "Earth Engine key installed"

################################################################################
# SECTION 9: Django Configuration
################################################################################

log "${BLUE}Configuring Django...${NC}"

# Update settings.py to use environment variables
SETTINGS_FILE="$APP_DIR/wetland_project/settings.py"

# Backup original
cp "$SETTINGS_FILE" "${SETTINGS_FILE}.backup"

# Check if dotenv is already imported
if ! grep -q "from dotenv import load_dotenv" "$SETTINGS_FILE"; then
    # Add dotenv import after existing imports
    sudo -u "$USERNAME" sed -i "1a from dotenv import load_dotenv\nload_dotenv(BASE_DIR / '.env')" "$SETTINGS_FILE"
fi

# Update settings using Python
sudo -u "$USERNAME" bash << 'PYSETTINGS'
import os
import sys
sys.path.insert(0, 'APPDIR')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wetland_project.settings')

# Read the settings file
with open('wetland_project/settings.py', 'r') as f:
    content = f.read()

# Replace settings
replacements = [
    ("DEBUG = True", "DEBUG = False"),
    ("SECRET_KEY = 'django-insecure-", "SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '"),
]

for old, new in replacements:
    if old in content:
        content = content.replace(old, new)

# Update ALLOWED_HOSTS
if "ALLOWED_HOSTS = []" in content:
    domain = os.environ.get('DOMAIN', 'thuto.co.ls')
    allowed_hosts = f"ALLOWED_HOSTS = ['{domain}', 'www.{domain}']"
    content = content.replace("ALLOWED_HOSTS = []", allowed_hosts)

# Add security settings if not present
if "SECURE_PROXY_SSL_HEADER" not in content:
    security_settings = """
# Cloudflare SSL Proxy Settings
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

CSRF_TRUSTED_ORIGINS = [
    f'https://{os.environ.get("DOMAIN", "thuto.co.ls")}',
    f'https://www.{os.environ.get("DOMAIN", "thuto.co.ls")}',
]

STATIC_ROOT = BASE_DIR / 'staticfiles'
"""
    # Insert before the end of the file
    content = content.rstrip() + '\n' + security_settings

with open('wetland_project/settings.py', 'w') as f:
    f.write(content)
PYSETTINGS

log_success "Django settings updated"

################################################################################
# SECTION 10: Database & Static Files
################################################################################

log "${BLUE}Running Django migrations and setup...${NC}"

cd "$APP_DIR"
sudo -u "$USERNAME" bash -c "source venv/bin/activate && python manage.py migrate"
sudo -u "$USERNAME" bash -c "source venv/bin/activate && python manage.py seed_users"
sudo -u "$USERNAME" bash -c "source venv/bin/activate && python manage.py collectstatic --noinput"

log_success "Database migrated and static files collected"

################################################################################
# SECTION 11: Gunicorn Systemd Service
################################################################################

log "${BLUE}Creating Gunicorn systemd service...${NC}"

cat > /etc/systemd/system/wetland.service << EOF
[Unit]
Description=Lesotho Wetland Monitoring — Gunicorn
After=network.target

[Service]
Type=notify
User=$USERNAME
Group=www-data
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/gunicorn \\
    --workers 3 \\
    --worker-class sync \\
    --bind unix:$APP_DIR/wetland.sock \\
    --timeout 120 \\
    --access-logfile - \\
    --error-logfile - \\
    wetland_project.wsgi:application

Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable wetland
systemctl start wetland

# Wait for service to start
sleep 2
systemctl status wetland --no-pager

log_success "Gunicorn service created and started"

################################################################################
# SECTION 12: Nginx Configuration
################################################################################

log "${BLUE}Configuring Nginx...${NC}"

# Remove default config
rm -f /etc/nginx/sites-enabled/default

# Create wetland config
cat > /etc/nginx/sites-available/wetland << 'NGINX'
server {
    listen 80;
    server_name thuto.co.ls www.thuto.co.ls;

    # Trust Cloudflare's forwarded IP header
    set_real_ip_from 103.21.244.0/22;
    set_real_ip_from 103.22.200.0/22;
    set_real_ip_from 103.31.4.0/22;
    set_real_ip_from 104.16.0.0/13;
    set_real_ip_from 104.24.0.0/14;
    set_real_ip_from 108.162.192.0/18;
    set_real_ip_from 131.0.72.0/22;
    set_real_ip_from 141.101.64.0/18;
    set_real_ip_from 162.158.0.0/15;
    set_real_ip_from 172.64.0.0/13;
    set_real_ip_from 173.245.48.0/20;
    set_real_ip_from 188.114.96.0/20;
    set_real_ip_from 190.93.240.0/20;
    set_real_ip_from 197.234.240.0/22;
    set_real_ip_from 198.41.128.0/17;
    real_ip_header CF-Connecting-IP;

    client_max_body_size 50M;

    location /static/ {
        alias APPDIR/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias APPDIR/media/;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:APPDIR/wetland.sock;
        proxy_read_timeout 120s;
        proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
    }
}
NGINX

# Replace APPDIR placeholder
sed -i "s|APPDIR|$APP_DIR|g" /etc/nginx/sites-available/wetland

# Enable site
ln -sf /etc/nginx/sites-available/wetland /etc/nginx/sites-enabled/

# Test and reload
nginx -t
systemctl enable nginx
systemctl restart nginx

log_success "Nginx configured and reloaded"

################################################################################
# SECTION 13: Post-Deployment Tasks
################################################################################

log "${BLUE}Performing post-deployment setup...${NC}"

# Create log rotation
cat > /etc/logrotate.d/wetland << EOF
$APP_DIR/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 $USERNAME www-data
    sharedscripts
}
EOF

# Create logs directory
mkdir -p "$APP_DIR/logs"
chown "$USERNAME:$USERNAME" "$APP_DIR/logs"

log_success "Log rotation configured"

################################################################################
# SECTION 14: Security Hardening
################################################################################

log "${BLUE}Hardening security...${NC}"

# Secure SSH
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart ssh

# Remove unnecessary packages
apt-get autoremove -y
apt-get autoclean -y

log_success "Security hardening complete"

################################################################################
# SECTION 15: Deployment Summary
################################################################################

log "${GREEN}========================================${NC}"
log "${GREEN}✓ DEPLOYMENT COMPLETE${NC}"
log "${GREEN}========================================${NC}"

cat << EOF

${GREEN}Deployment Summary${NC}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

${BLUE}Application Details:${NC}
  App Directory:  $APP_DIR
  Username:       $USERNAME
  Domain:         $DOMAIN
  
${BLUE}Services:${NC}
  • Gunicorn:     $APP_DIR/wetland.sock (systemd: wetland)
  • Nginx:        Reverse proxy on port 80
  • Firewall:     UFW enabled (22, 80, 443)

${BLUE}Default User Accounts:${NC}
  admin          / admin           (System Admin)
  doe_officer    / doe123          (DOE Officer)
  dma_officer    / dma123          (DMA Officer)
  nul_researcher / nul123          (NUL Researcher)
  community      / community123    (Community Member)

${YELLOW}⚠ IMPORTANT - NEXT STEPS:${NC}

1. ${RED}Change default passwords immediately:${NC}
   ssh $USERNAME@<your-droplet-ip>
   cd $APP_DIR
   source venv/bin/activate
   python manage.py changepassword admin

2. ${RED}Configure Cloudflare DNS:${NC}
   • Add A record: @ → <your-droplet-ip> (Proxied)
   • Add A record: www → <your-droplet-ip> (Proxied)
   • Set SSL/TLS mode to "Full"
   • Enable "Always Use HTTPS"

3. ${RED}Verify deployment:${NC}
   • Check services: sudo systemctl status wetland
   • View logs: sudo journalctl -u wetland -f
   • Test app: curl http://localhost/

4. ${RED}Email notification:${NC}
   Admin email: $EMAIL

${BLUE}Useful Commands:${NC}
  • Restart app:        sudo systemctl restart wetland
  • View logs:          sudo journalctl -u wetland -f
  • Nginx errors:       sudo tail -f /var/log/nginx/error.log
  • Update code:        cd $APP_DIR && git pull && sudo systemctl restart wetland
  • Database backup:    python manage.py dumpdata > backup.json

${GREEN}Happy monitoring! 🌿${NC}

EOF

log_success "Deployment script completed successfully"
