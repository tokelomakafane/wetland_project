# Deployment Script Usage Guide

This guide explains how to use the automated deployment scripts for the Lesotho Wetland Monitoring System.

## Files

- **deploy.sh** — Full automated deployment (run once on fresh droplet)
- **update.sh** — Quick update script (run after code changes)
- **DEPLOYMENT.md** — Detailed manual deployment guide (reference)

---

## Prerequisites

Before running the deployment script:

1. **Digital Ocean Droplet Created**
   - Ubuntu 24.04 LTS
   - 2 vCPU / 2 GB RAM minimum (4 GB recommended)
   - SSH key pair configured

2. **Google Earth Engine Setup**
   - Service account created in GEE Cloud Console
   - Service account key JSON file downloaded locally
   - Service account has Earth Engine access

3. **Domain & Cloudflare**
   - Domain registered
   - Cloudflare account created and configured

---

## Step 1: Connect to Droplet

```bash
ssh root@<your-droplet-ip>
```

Replace `<your-droplet-ip>` with your actual droplet IP address.

---

## Step 2: Prepare for Deployment

### Option A: Download Script from GitHub

```bash
cd /tmp
wget https://raw.githubusercontent.com/tokelomakafane/wetland_project/main/deploy.sh
chmod +x deploy.sh
sudo bash deploy.sh
```

### Option B: Manual File Upload

If you cloned the repo locally:

```bash
# From your local machine
scp deploy.sh root@<your-droplet-ip>:/tmp/
scp update.sh root@<your-droplet-ip>:/tmp/

# Then on droplet
chmod +x /tmp/deploy.sh
sudo bash /tmp/deploy.sh
```

---

## Step 3: Run Deployment Script

```bash
sudo bash deploy.sh
```

The script will prompt you for:

1. **Non-root username** (default: `wetland`)
   - Account that will run the application
   - Should be non-root for security

2. **Domain** (e.g., `thuto.co.ls`)
   - Your primary domain name
   - Used for Nginx and Django ALLOWED_HOSTS

3. **Email** (e.g., `admin@example.com`)
   - For system notifications
   - Used in deployment logs

4. **Google Earth Engine Project**
   - GEE project ID (e.g., `tokelo-329815`)
   - Service account email
   - Path to service account JSON key

### Example Run

```
[16:30:45] Lesotho Wetland Monitoring — Deployment
[16:30:45] Collecting deployment configuration...
Enter the non-root username (default: wetland): wetland
Enter your domain (e.g., thuto.co.ls): thuto.co.ls
Enter your email for system notifications: admin@thuto.co.ls
Enter Google Earth Engine project name (e.g., tokelo-329815): tokelo-329815
Enter Google Earth Engine service account email: sa@tokelo-329815.iam.gserviceaccount.com
Enter path to Earth Engine key JSON file on this machine: /home/user/ee-key.json
```

---

## Step 4: Automated Process

The script will:

- ✓ Install system dependencies (Python, Nginx, Git, etc.)
- ✓ Configure firewall (UFW) — ports 22, 80, 443
- ✓ Create non-root user with sudo access
- ✓ Clone repository from GitHub
- ✓ Create Python virtual environment
- ✓ Install Python dependencies from requirements.txt
- ✓ Generate Django SECRET_KEY
- ✓ Copy Earth Engine service account key
- ✓ Configure Django settings for production
- ✓ Run database migrations
- ✓ Seed default user accounts
- ✓ Collect static files
- ✓ Create Gunicorn systemd service
- ✓ Configure Nginx reverse proxy
- ✓ Set up log rotation
- ✓ Harden SSH security

**Estimated time:** 10-15 minutes

---

## Step 5: Post-Deployment Configuration

### 1. Change Default Passwords

**IMMEDIATELY change all default passwords:**

```bash
ssh wetland@<your-droplet-ip>
cd /home/wetland/app
source venv/bin/activate
python manage.py changepassword admin
# Repeat for: doe_officer, dma_officer, nul_researcher, community
```

Default credentials created by `seed_users`:

| Username | Default Password |
|---|---|
| admin | admin |
| doe_officer | doe123 |
| dma_officer | dma123 |
| nul_researcher | nul123 |
| community | community123 |

### 2. Configure Cloudflare DNS

1. Log in to [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Select your domain
3. Go to **DNS** → **Records**
4. Add two A records:
   - **Name:** @ | **Content:** `<your-droplet-ip>` | **Proxy:** ☁️ Proxied
   - **Name:** www | **Content:** `<your-droplet-ip>` | **Proxy:** ☁️ Proxied

5. Go to **SSL/TLS** → **Overview**
   - Set encryption mode to **Full** (not Full Strict)

6. Go to **SSL/TLS** → **Edge Certificates**
   - Enable **Always Use HTTPS**

### 3. Verify Deployment

```bash
# Check services
ssh wetland@<your-droplet-ip>
sudo systemctl status wetland
sudo systemctl status nginx

# View logs
sudo journalctl -u wetland -f

# Test locally
curl http://localhost/
```

### 4. Access the Application

```
https://thuto.co.ls
```

---

## Step 6: Ongoing Operations

### Update Application Code

When you push new code to GitHub:

```bash
ssh wetland@<your-droplet-ip>
cd /home/wetland/app
bash update.sh
```

The `update.sh` script will:
- Pull latest code from GitHub
- Update dependencies
- Run migrations
- Collect static files
- Restart Gunicorn

### View Application Logs

```bash
ssh wetland@<your-droplet-ip>
sudo journalctl -u wetland -f
```

Press `Ctrl+C` to exit.

### Restart Application

```bash
ssh wetland@<your-droplet-ip>
sudo systemctl restart wetland
```

### Check Service Status

```bash
ssh wetland@<your-droplet-ip>
sudo systemctl status wetland
sudo systemctl status nginx
```

### Database Backup

```bash
ssh wetland@<your-droplet-ip>
cd /home/wetland/app
source venv/bin/activate
python manage.py dumpdata > backup_$(date +%Y%m%d).json
```

### SSH Login Without Password

Set up SSH key authentication (recommended):

```bash
# From your local machine
ssh-copy-id -i ~/.ssh/id_rsa.pub wetland@<your-droplet-ip>
```

---

## Troubleshooting

### Application Won't Start

```bash
# Check service status
sudo systemctl status wetland

# View detailed logs
sudo journalctl -u wetland -n 50

# Check socket exists
ls -la /home/wetland/app/wetland.sock

# Restart service
sudo systemctl restart wetland
```

### Nginx Errors

```bash
# Check Nginx configuration
sudo nginx -t

# View Nginx error log
sudo tail -f /var/log/nginx/error.log

# Reload Nginx
sudo systemctl reload nginx
```

### Database Issues

```bash
# Run migrations again
cd /home/wetland/app
source venv/bin/activate
python manage.py migrate

# Check database
python manage.py dbshell
```

### Earth Engine Authentication

```bash
# Test EE authentication
cd /home/wetland/app
source venv/bin/activate
python manage.py authenticate_earth_engine

# Check key file permissions
ls -la /home/wetland/ee-key.json
# Should show: -r-------- (400 permissions)
```

### Permission Denied Errors

```bash
# Fix directory ownership
sudo chown -R wetland:wetland /home/wetland/app
sudo chown -R wetland:www-data /home/wetland/app/media

# Fix socket permissions
sudo chown wetland:www-data /home/wetland/app/wetland.sock
```

---

## Security Checklist

- [ ] SSH password authentication disabled
- [ ] Root login disabled
- [ ] Firewall enabled (UFW)
- [ ] All default passwords changed
- [ ] DEBUG = False in settings.py
- [ ] SECRET_KEY in .env (not hardcoded)
- [ ] Earth Engine key has 400 permissions
- [ ] SSL enabled on Cloudflare (Full mode)
- [ ] Regular database backups scheduled
- [ ] Log rotation configured

---

## Monitoring & Maintenance

### Set Up Email Alerts (Optional)

Install and configure Postfix for email notifications:

```bash
sudo apt-get install -y postfix

# Configure to send alerts when services fail
# (Requires additional Nagios/Prometheus setup)
```

### Regular Backups

```bash
# Add to crontab for automatic backups
crontab -e

# Add this line for daily backups at 2 AM
0 2 * * * cd /home/wetland/app && source venv/bin/activate && python manage.py dumpdata > /home/wetland/backups/backup_$(date +\%Y\%m\%d).json
```

### Monitor Disk Space

```bash
df -h
du -sh /home/wetland/app/media
```

---

## Support

For issues or questions:

1. Check logs: `sudo journalctl -u wetland -f`
2. Review [DEPLOYMENT.md](DEPLOYMENT.md) for manual steps
3. Check Django documentation: https://docs.djangoproject.com/
4. Earth Engine docs: https://developers.google.com/earth-engine

---

**Last Updated:** May 2026
**Script Version:** 1.0
