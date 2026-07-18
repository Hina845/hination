# HINATION VPS Deployment Guide

## Prerequisites

- VPS with Ubuntu 22.04+ (or Debian 11+)
- SSH access to the VPS
- Domain: `dienbienforecast.site` pointed to your VPS IP
- Docker & Docker Compose installed on VPS

---

## Step 1: Prepare VPS

### 1.1 Install Docker on VPS

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install prerequisites
sudo apt install -y ca-certificates curl gnupg lsb-release

# Add Docker GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

### 1.2 Install Git

```bash
sudo apt install -y git
```

---

## Step 2: Transfer Project to VPS

### Option A: Clone from GitHub

```bash
# SSH to VPS, then:
git clone https://github.com/yourusername/hination.git
cd hination
```

### Option B: Copy from local machine

```bash
# On local machine:
cd /home/khang/job
tar -czvf hination.tar.gz hination/

# Copy to VPS
scp hination.tar.gz user@your-vps-ip:/home/user/
```

---

## Step 3: Configure Environment

### 3.1 Create .env file

```bash
cd hination
cp .env.example .env
nano .env
```

Add your configuration:

```env
# Optional: AI features (optional)
OPENAI_API_KEY=your_openai_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4

# Optional: Search integration
BRAVE_SEARCH_API_KEY=your_brave_key

# Optional: Custom tile URL
HINATION_TILE_URL=https://tile.openstreetmap.org/{z}/{x}/{y}.png
```

### 3.2 Update docker-compose.yml for production

The default config uses port 8084 for nginx. If you want to use port 80 directly:

```bash
# Edit nginx port mapping
nano docker-compose.yml
```

Change:
```yaml
nginx:
  ports:
    - "80:80"  # Direct HTTP (requires stopping existing nginx)
```

Or keep 8084 and configure existing nginx to proxy.

---

## Step 4: Domain DNS Configuration

### 4.1 Set DNS A Record

In your domain registrar (Namecheap, GoDaddy, Cloudflare, etc.):

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | @ | YOUR_VPS_IP | 300 |

### 4.2 Verify DNS propagation

```bash
# On local machine:
nslookup dienbienforecast.site
# or
dig dienbienforecast.site
```

---

## Step 5: Stop Existing Nginx on VPS

Since your VPS already has nginx on port 80, you have two options:

### Option A: Proxy through existing nginx (Recommended)

Add to existing nginx config:

```bash
sudo nano /etc/nginx/sites-available/dienbienforecast.site
```

```nginx
server {
    server_name dienbienforecast.site;

    location / {
        proxy_pass http://127.0.0.1:8084;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/dienbienforecast.site /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Option B: Change HINATION port and use different port

Keep docker-compose as-is (port 8084), then use iptables:

```bash
sudo iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 8084
```

---

## Step 6: Deploy with Docker Compose

### 6.1 Build and start containers

```bash
cd hination

# Build all images
docker compose build

# Start containers
docker compose up -d

# Check status
docker compose ps
```

### 6.2 Verify deployment

```bash
# Test locally
curl http://localhost:8084/healthz
curl http://localhost:8084/

# Test from external
curl http://dienbienforecast.site/healthz
```

---

## Step 7: Enable HTTPS (Recommended)

### Using Let's Encrypt with Certbot

```bash
sudo apt install -y certbot python3-certbot-nginx

# Stop existing nginx temporarily
sudo systemctl stop nginx

# Get certificate
sudo certbot certonly --standalone -d dienbienforecast.site

# Restart nginx
sudo systemctl start nginx
```

### Update nginx config for HTTPS

```bash
sudo nano /etc/nginx/sites-available/dienbienforecast.site
```

```nginx
server {
    listen 80;
    server_name dienbienforecast.site;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name dienbienforecast.site;

    ssl_certificate /etc/letsencrypt/live/dienbienforecast.site/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dienbienforecast.site/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8084;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
```

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### Auto-renewal

```bash
sudo crontab -e
# Add line:
0 0 * * * certbot renew --quiet
```

---

## Step 8: Enable Auto-Start on Boot

```bash
sudo systemctl enable docker
docker compose up -d
```

---

## Step 9: Monitoring & Logs

### View logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f nginx
```

### Check health

```bash
docker compose ps
curl http://localhost:8084/healthz
```

---

## Step 10: Update Deployment

```bash
cd hination

# Pull latest code
git pull

# Rebuild and restart
docker compose build
docker compose up -d
```

---

## Quick Reference

| Service | Port | URL |
|---------|------|-----|
| Nginx (HTTP) | 8084 | http://dienbienforecast.site |
| Frontend | 1111 | http://dienbienforecast.site:1111 |
| Backend API | 1112 | http://dienbienforecast.site:1112 |
| Health Check | - | http://dienbienforecast.site/healthz |

---

## Troubleshooting

### Container won't start

```bash
docker compose logs backend
docker compose logs frontend
```

### Port already in use

```bash
sudo lsof -i :8084
# or
sudo netstat -tlnp | grep 8084
```

### DNS not resolving

```bash
# Check DNS propagation
dig dienbienforecast.site
nslookup dienbienforecast.site

# Wait 5-10 minutes for propagation
```

### SSL certificate issues

```bash
sudo certbot certificates
sudo certbot renew --force-renewal
```
