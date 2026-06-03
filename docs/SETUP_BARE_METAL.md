# Bare-Metal Deployment

Deploy sellm on a Ubuntu 24.04 server with nginx, Neo4j, ChromaDB, and optional SSL.

## Quick Install

```bash
# Clone the repo
git clone https://github.com/Snickdx/sellm.git /opt/sellm
cd /opt/sellm

# Run the automated setup script (as root)
sudo bash scripts/update sellm.nmendez.app
```

Omit the domain to skip nginx/SSL setup:
```bash
sudo bash scripts/update
```

## What the Script Does

| Step | Component | Details |
|------|-----------|---------|
| 1 | System deps | Python 3, Java 17, nginx, curl, gpg |
| 2 | Python venv | Creates `/opt/sellm/venv`, installs requirements |
| 3 | Neo4j | Installs from apt, sets password, starts on `:7687` |
| 4 | Env config | Copies `app/.env.example` → `app/.env`, sets template LLM |
| 5 | ChromaDB | Builds vector index from `data.xlsx` |
| 6 | Systemd | Registers `sellm.service` (FastAPI on `127.0.0.1:8000`) |
| 7 | nginx | Reverse proxy to the app (if domain supplied) |
| 8 | SSL (certbot) | Auto-provisions Let's Encrypt cert (if domain supplied) |

## Manual Setup

### 1. System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv python3-full openjdk-17-jdk nginx wget curl gpg
```

### 2. Python Environment

```bash
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install "torch>=2.2.0,<2.6.0"
venv/bin/pip install -r requirements.txt
```

> `torch==2.1.1` (pinned in requirements.txt) is incompatible with Python ≥3.12.
> The install above overrides it with a compatible version.

### 3. Neo4j

```bash
wget -O - https://debian.neo4j.com/neotechnology.gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/neo4j.gpg
echo 'deb [signed-by=/usr/share/keyrings/neo4j.gpg] https://debian.neo4j.com stable latest' | sudo tee /etc/apt/sources.list.d/neo4j.list
sudo apt-get update && sudo apt-get install -y neo4j cypher-shell
sudo systemctl stop neo4j
sudo neo4j-admin dbms set-initial-password password
sudo systemctl start neo4j
```

Verify: `echo "RETURN 1" | cypher-shell -u neo4j -p password`

### 4. Environment

```bash
cp app/.env.example app/.env
# Edit app/.env — at minimum set LLM_BACKEND=template (no API key needed)
```

### 5. Chroma Index

```bash
mkdir -p storage
python -m setup.chroma.init_chroma
```

### 6. Systemd Service

```ini
# /etc/systemd/system/sellm.service
[Unit]
Description=sellm FastAPI app
After=network.target neo4j.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/sellm
ExecStart=/opt/sellm/venv/bin/uvicorn app.api.app:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
Environment=PYTHONPATH=/opt/sellm

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now sellm
```

### 7. nginx Reverse Proxy

```nginx
# /etc/nginx/sites-available/sellm.nmendez.app
server {
    listen 80;
    server_name sellm.nmendez.app;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }
}
```

```bash
sudo ln -sf /etc/nginx/sites-available/sellm.nmendez.app /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### 8. SSL (Certbot)

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d sellm.nmendez.app
```

## Logs & Management

```bash
# App logs
journalctl -u sellm -f

# Neo4j logs
journalctl -u neo4j -f

# nginx logs
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log

# Restart services
systemctl restart sellm
systemctl restart neo4j
systemctl reload nginx
```

## Configuration

Edit `app/.env` to change:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_BACKEND` | `template` | `ollama`, `openai`, or `template` |
| `LLM_MODEL` | `llama3.2` | Model name (ignored for template) |
| `RAG_BACKEND` | `chromadb` | `chromadb` or `neo4j` |
| `NEO4J_PASSWORD` | `password` | Must match the Neo4j password |
| `OPENAI_API_KEY` | — | Required if `LLM_BACKEND=openai` |

## Docker Alternative

For containerized deployment:

```bash
docker compose up --build
```

See [DEPLOY_EASYPANEL.md](DEPLOY_EASYPANEL.md) for cloud deployment.
