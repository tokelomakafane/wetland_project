#!/bin/bash
################################################################################
# Lesotho Wetland Monitoring — Post-Deployment Update Script
#
# Usage: bash update.sh
#
# This script updates the application after new code is pushed to GitHub.
# Run this instead of manual git/migrate steps.
################################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

log_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Check if in app directory
if [ ! -f "manage.py" ]; then
    log_error "Not in application directory. Run from: /home/wetland/app"
    exit 1
fi

log "${BLUE}Starting application update...${NC}"

# Activate virtual environment
source venv/bin/activate

# Pull latest code
log "Pulling latest code from GitHub..."
git pull origin main || {
    log_error "Git pull failed. Check repository status."
    exit 1
}
log_success "Code updated"

# Update dependencies
log "Updating Python dependencies..."
pip install -r requirements.txt --upgrade
log_success "Dependencies updated"

# Run migrations
log "Running database migrations..."
python manage.py migrate
log_success "Database migrations complete"

# Collect static files
log "Collecting static files..."
python manage.py collectstatic --noinput
log_success "Static files collected"

# Restart application
log "Restarting Gunicorn service..."
sudo systemctl restart wetland
sleep 2

# Verify service is running
if sudo systemctl is-active --quiet wetland; then
    log_success "Application restarted successfully"
else
    log_error "Application failed to restart. Check logs: sudo journalctl -u wetland"
    exit 1
fi

echo ""
log_success "Update complete! Application is running."
echo ""
log "View logs: sudo journalctl -u wetland -f"
