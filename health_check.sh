#!/bin/bash
################################################################################
# Lesotho Wetland Monitoring — Health Check Script
#
# Usage: bash health_check.sh
#
# This script verifies that all components of the deployment are healthy.
# Useful for troubleshooting and monitoring.
################################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
NC='\033[0m'

# Status counters
PASSED=0
FAILED=0
WARNINGS=0

check_pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASSED++))
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
    ((FAILED++))
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARNINGS++))
}

section() {
    echo -e "\n${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

section "System Health Check"

# 1. Check if running as non-root (but can be root for checks)
if [ "$EUID" -eq 0 ]; then
    check_warn "Running as root (should run as application user for full checks)"
else
    check_pass "Running as non-root user"
fi

# 2. Check Python installation
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    check_pass "Python installed: $PYTHON_VERSION"
else
    check_fail "Python3 not found"
fi

# 3. Check virtual environment
APP_DIR="/home/wetland/app"
if [ -d "$APP_DIR/venv" ]; then
    check_pass "Virtual environment exists"
else
    check_fail "Virtual environment not found at $APP_DIR/venv"
fi

# 4. Check Git
if command -v git &> /dev/null; then
    check_pass "Git installed: $(git --version)"
else
    check_fail "Git not installed"
fi

# 5. Check Nginx
if command -v nginx &> /dev/null; then
    check_pass "Nginx installed: $(nginx -v 2>&1)"
else
    check_fail "Nginx not installed"
fi

section "Services Status"

# 6. Check Gunicorn service
if systemctl is-active --quiet wetland; then
    check_pass "Gunicorn service (wetland) is running"
else
    check_fail "Gunicorn service (wetland) is not running"
fi

# 7. Check Nginx service
if systemctl is-active --quiet nginx; then
    check_pass "Nginx service is running"
else
    check_fail "Nginx service is not running"
fi

# 8. Check SSH service
if systemctl is-active --quiet ssh; then
    check_pass "SSH service is running"
else
    check_fail "SSH service is not running"
fi

section "Network & Ports"

# 9. Check if port 80 is listening
if netstat -tuln 2>/dev/null | grep -q ":80 "; then
    check_pass "Port 80 (HTTP) is listening"
else
    check_warn "Port 80 not listening (Nginx may need restart)"
fi

# 10. Check if port 443 is listening (might not be, depends on Cloudflare)
if netstat -tuln 2>/dev/null | grep -q ":443 "; then
    check_pass "Port 443 (HTTPS) is listening"
else
    check_warn "Port 443 not listening (normal if using Cloudflare)"
fi

# 11. Check Gunicorn socket
if [ -S "$APP_DIR/wetland.sock" ]; then
    check_pass "Gunicorn socket exists and is accessible"
else
    check_fail "Gunicorn socket not found or not accessible"
fi

section "Application Files"

# 12. Check manage.py
if [ -f "$APP_DIR/manage.py" ]; then
    check_pass "Django manage.py found"
else
    check_fail "Django manage.py not found"
fi

# 13. Check requirements.txt
if [ -f "$APP_DIR/requirements.txt" ]; then
    check_pass "requirements.txt found"
else
    check_fail "requirements.txt not found"
fi

# 14. Check environment file
if [ -f "$APP_DIR/.env" ]; then
    check_pass "Environment file (.env) exists"
    # Check for required variables
    if grep -q "DJANGO_SECRET_KEY" "$APP_DIR/.env"; then
        check_pass "DJANGO_SECRET_KEY set"
    else
        check_fail "DJANGO_SECRET_KEY not set in .env"
    fi
    
    if grep -q "EE_SERVICE_ACCOUNT_KEY" "$APP_DIR/.env"; then
        check_pass "EE_SERVICE_ACCOUNT_KEY set"
    else
        check_fail "EE_SERVICE_ACCOUNT_KEY not set in .env"
    fi
else
    check_fail "Environment file (.env) not found"
fi

# 15. Check Earth Engine key
EE_KEY_PATH="/home/wetland/ee-key.json"
if [ -f "$EE_KEY_PATH" ]; then
    check_pass "Earth Engine key file exists"
    # Check permissions
    PERMS=$(stat -c "%a" "$EE_KEY_PATH" 2>/dev/null || stat -f "%OLp" "$EE_KEY_PATH" | tail -c 4)
    if [ "$PERMS" = "400" ] || [ "$PERMS" = "0400" ]; then
        check_pass "Earth Engine key has correct permissions (400)"
    else
        check_warn "Earth Engine key permissions: $PERMS (should be 400)"
    fi
else
    check_warn "Earth Engine key not found at $EE_KEY_PATH"
fi

# 16. Check static files
if [ -d "$APP_DIR/staticfiles" ]; then
    FILE_COUNT=$(find "$APP_DIR/staticfiles" -type f 2>/dev/null | wc -l)
    check_pass "Static files collected ($FILE_COUNT files)"
else
    check_warn "Static files directory not found"
fi

section "Database & Migrations"

# 17. Check database
if [ -f "$APP_DIR/db.sqlite3" ]; then
    check_pass "Database file exists (db.sqlite3)"
    # Check file size
    SIZE=$(du -h "$APP_DIR/db.sqlite3" | cut -f1)
    check_pass "Database size: $SIZE"
else
    check_warn "Database file not found (might be using remote database)"
fi

section "Configuration Verification"

# 18. Check Django DEBUG setting
if grep -q "DEBUG = False" "$APP_DIR/wetland_project/settings.py"; then
    check_pass "DEBUG is set to False (production mode)"
elif grep -q "DEBUG = True" "$APP_DIR/wetland_project/settings.py"; then
    check_fail "DEBUG is set to True (should be False in production)"
else
    check_warn "Cannot determine DEBUG setting"
fi

# 19. Check ALLOWED_HOSTS
if grep -q "ALLOWED_HOSTS" "$APP_DIR/wetland_project/settings.py"; then
    check_pass "ALLOWED_HOSTS is configured"
else
    check_fail "ALLOWED_HOSTS not found in settings"
fi

section "Disk Space & Resources"

# 20. Check root filesystem
ROOT_USAGE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$ROOT_USAGE" -lt 80 ]; then
    check_pass "Root filesystem usage: ${ROOT_USAGE}%"
else
    check_warn "Root filesystem usage high: ${ROOT_USAGE}%"
fi

# 21. Check app directory size
if [ -d "$APP_DIR" ]; then
    APP_SIZE=$(du -sh "$APP_DIR" 2>/dev/null | cut -f1)
    check_pass "Application directory size: $APP_SIZE"
fi

# 22. Check media directory
if [ -d "$APP_DIR/media" ]; then
    MEDIA_SIZE=$(du -sh "$APP_DIR/media" 2>/dev/null | cut -f1)
    check_pass "Media directory size: $MEDIA_SIZE"
fi

section "Log Files"

# 23. Check application logs
if [ -d "$APP_DIR/logs" ]; then
    check_pass "Logs directory exists"
    
    # Count error lines in recent logs
    ERROR_COUNT=$(find "$APP_DIR/logs" -type f -name "*.log" -mtime -1 2>/dev/null | xargs grep -c "ERROR" 2>/dev/null || echo 0)
    if [ "$ERROR_COUNT" -eq 0 ]; then
        check_pass "No recent errors in logs"
    else
        check_warn "Found $ERROR_COUNT error(s) in recent logs"
    fi
else
    check_warn "Logs directory not found"
fi

# 24. Check Nginx logs
if [ -f "/var/log/nginx/error.log" ]; then
    NGINX_ERRORS=$(tail -100 /var/log/nginx/error.log 2>/dev/null | grep -c "error" || echo 0)
    if [ "$NGINX_ERRORS" -eq 0 ]; then
        check_pass "No recent Nginx errors"
    else
        check_warn "Found $NGINX_ERRORS Nginx error(s) in recent logs"
    fi
fi

section "Connectivity Tests"

# 25. Test local HTTP connection
if command -v curl &> /dev/null; then
    if timeout 5 curl -s http://localhost/ > /dev/null 2>&1; then
        check_pass "Application responds to HTTP (localhost)"
    else
        check_fail "Application not responding to HTTP requests"
    fi
else
    check_warn "curl not installed, skipping HTTP test"
fi

# 26. Check Internet connectivity
if timeout 5 curl -s https://www.google.com > /dev/null 2>&1; then
    check_pass "Internet connectivity available"
else
    check_warn "Cannot reach external internet (required for Earth Engine)"
fi

section "Summary Report"

TOTAL=$((PASSED + FAILED + WARNINGS))

echo ""
echo -e "Total Checks: ${MAGENTA}$TOTAL${NC}"
echo -e "✓ Passed:  ${GREEN}$PASSED${NC}"
echo -e "✗ Failed:  ${RED}$FAILED${NC}"
echo -e "⚠ Warnings: ${YELLOW}$WARNINGS${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    if [ $WARNINGS -eq 0 ]; then
        echo -e "${GREEN}All systems operational! 🚀${NC}"
        exit 0
    else
        echo -e "${YELLOW}System operational with warnings ⚠${NC}"
        exit 0
    fi
else
    echo -e "${RED}System issues detected! Please review failures above.${NC}"
    exit 1
fi
