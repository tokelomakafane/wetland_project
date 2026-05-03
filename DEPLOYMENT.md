# Deployment Guide — Lesotho Wetland Monitoring System
**Target:** Digital Ocean Droplet · Domain: `thuto.co.ls` (Cloudflare proxied)

---

## 1. Digital Ocean Droplet Setup

Create a droplet on Digital Ocean:
- **Image:** Ubuntu 24.04 LTS
- **Size:** Basic — 2 vCPU / 2 GB RAM minimum (4 GB recommended for EE API calls)
- **Region:** closest to Lesotho (e.g. Amsterdam or Johannesburg if available)
- Add your SSH key during creation

SSH in:
```bash
ssh root@<your-droplet-ip>
```

Create a non-root user:
```bash
adduser wetland
usermod -aG sudo wetland
su - wetland
```

---

## 2. Install System Dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git nginx ufw
```

---

## 3. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

---

## 4. Clone the Repository

```bash
cd /home/wetland
git clone https://github.com/tokelomakafane/wetland_project.git app
cd app
```

---

## 5. Python Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

---

## 6. Environment Variables

Create `/home/wetland/app/.env` — **never commit this file**:

```bash
nano /home/wetland/app/.env
```

```env
DJANGO_SECRET_KEY=<generate-a-long-random-string>
EE_PROJECT=tokelo-329815
EE_SERVICE_ACCOUNT_KEY=/home/wetland/ee-key.json
EE_SERVICE_ACCOUNT=your-sa@tokelo-329815.iam.gserviceaccount.com
```

Generate a secret key:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## 7. Django Production Settings

Edit `wetland_project/settings.py`:

```python
import os
from dotenv import load_dotenv          # add:  pip install python-dotenv
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.environ['DJANGO_SECRET_KEY']

DEBUG = False

ALLOWED_HOSTS = ['thuto.co.ls', 'www.thuto.co.ls', '<your-droplet-ip>']

CSRF_TRUSTED_ORIGINS = [
    'https://thuto.co.ls',
    'https://www.thuto.co.ls',
]

# Cloudflare terminates SSL and forwards requests over HTTP to your server.
# This tells Django to treat X-Forwarded-Proto: https as a secure connection.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

STATIC_ROOT = BASE_DIR / 'staticfiles'
```

Install python-dotenv:
```bash
pip install python-dotenv
```

---

## 8. Google Earth Engine — Service Account

1. In the [GEE Cloud Console](https://console.cloud.google.com/), create a service account with **Earth Engine** access.
2. Download the JSON key and upload it to the server:
   ```bash
   # From your local machine
   scp ee-key.json wetland@<droplet-ip>:/home/wetland/ee-key.json
   chmod 400 /home/wetland/ee-key.json
   ```

---

## 9. Database & Static Files

```bash
source venv/bin/activate
python manage.py migrate
python manage.py seed_users
python manage.py collectstatic --no-input
```

Default accounts created by `seed_users`:

| Username | Password | Role |
|---|---|---|
| `admin` | `admin` | System Admin (superuser) |
| `doe_officer` | `doe123` | DOE Officer |
| `dma_officer` | `dma123` | DMA Officer |
| `nul_researcher` | `nul123` | NUL Researcher |
| `community` | `community123` | Community Member |

> **Change all default passwords immediately after deployment.**

---

## 10. Gunicorn Systemd Service

Create `/etc/systemd/system/wetland.service`:

```bash
sudo nano /etc/systemd/system/wetland.service
```

```ini
[Unit]
Description=Lesotho Wetland Monitoring — Gunicorn
After=network.target

[Service]
User=wetland
Group=www-data
WorkingDirectory=/home/wetland/app
EnvironmentFile=/home/wetland/app/.env
ExecStart=/home/wetland/app/venv/bin/gunicorn \
    wetland_project.wsgi:application \
    --bind unix:/home/wetland/app/wetland.sock \
    --workers 3 \
    --timeout 120
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable wetland
sudo systemctl start wetland
sudo systemctl status wetland
```

---

## 11. Nginx Configuration

Create `/etc/nginx/sites-available/wetland`:

```bash
sudo nano /etc/nginx/sites-available/wetland
```

```nginx
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
        alias /home/wetland/app/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /home/wetland/app/media/;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/home/wetland/app/wetland.sock;
        proxy_read_timeout 120s;
        proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
    }
}
```

Enable and reload:
```bash
sudo ln -s /etc/nginx/sites-available/wetland /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 12. Cloudflare DNS & SSL

In your Cloudflare dashboard for `thuto.co.ls`:

1. **DNS** — Add an A record:
   | Type | Name | Content | Proxy |
   |---|---|---|---|
   | A | `@` | `<your-droplet-ip>` | Proxied (orange cloud) |
   | A | `www` | `<your-droplet-ip>` | Proxied (orange cloud) |

2. **SSL/TLS** — Set encryption mode to **Full** (not Full Strict, since your server uses HTTP internally).

3. **SSL/TLS → Edge Certificates** — Enable **Always Use HTTPS**.

4. **Security → Settings** — Set Security Level to **Medium** or higher.

> Cloudflare handles the HTTPS certificate automatically. No certbot needed on the server.

---

## 13. Useful Commands

```bash
# View application logs
sudo journalctl -u wetland -f

# Restart after code changes
cd /home/wetland/app
git pull
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --no-input
sudo systemctl restart wetland

# Check nginx errors
sudo tail -f /var/log/nginx/error.log

# Check Gunicorn socket
sudo systemctl status wetland
```

---

## 14. Pre-Launch Checklist

- [ ] `DEBUG = False` in settings
- [ ] `DJANGO_SECRET_KEY` set in `.env` (not hardcoded)
- [ ] All default passwords changed
- [ ] EE service account key file on server, `chmod 400`
- [ ] `python manage.py migrate` and `seed_users` complete
- [ ] `python manage.py collectstatic` complete
- [ ] Nginx test passes: `sudo nginx -t`
- [ ] Gunicorn service running: `sudo systemctl status wetland`
- [ ] Cloudflare DNS A record points to droplet IP
- [ ] Cloudflare SSL mode set to **Full**
- [ ] Site loads at `https://thuto.co.ls`
