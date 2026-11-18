# Installing on a Linux server (Docker)

This guide is for the administrator who installs and runs the chatbot on a server. It covers Ubuntu with an NVIDIA GPU, which is the recommended setup. For running it on a Windows PC without Docker, see the [README](../README.md).

What gets installed:

```
 staff browser ──HTTPS──> reverse proxy (nginx, optional but recommended)
                              │
                              ▼  port 8080
                ┌──────────── app container ────────────┐
                │ web chat (FastAPI) ──> MCP server     │──HTTPS──> KnowBe4 APIs
                │                      (127.0.0.1 only) │
                └──────────────┬────────────────────────┘
                               ▼  internal Docker network only
                ┌──────── ollama container ─────────────┐
                │ local AI model kb4-analyst (on GPU)   │
                └───────────────────────────────────────┘
```

- **No KnowBe4 data and no questions leave the server**, except the read-only requests to KnowBe4 itself. The AI model runs locally.
- **Only the web chat is published.** Ollama and the MCP server cannot be reached from outside.
- **The chat has no login.** Anyone who can open the page can ask about every console that has a key, including people's names and emails. Restrict who can reach it (section 7).

## Contents

1. [Requirements](#1-requirements)
2. [Install Docker](#2-install-docker)
3. [Install the NVIDIA driver and Container Toolkit](#3-install-the-nvidia-driver-and-container-toolkit)
4. [Copy the project to the server](#4-copy-the-project-to-the-server)
5. [Configure](#5-configure)
6. [Build and start](#6-build-and-start)
7. [Give staff access](#7-give-staff-access)
8. [Day-to-day operation](#8-day-to-day-operation)
9. [Updating](#9-updating)
10. [Backups](#10-backups)
11. [A server without internet access](#11-a-server-without-internet-access)
12. [Security checklist](#12-security-checklist)
13. [Troubleshooting](#13-troubleshooting)
14. [Uninstalling](#14-uninstalling)

## 1. Requirements

| | |
|---|---|
| Operating system | Ubuntu 22.04, 24.04 or 26.04 LTS, 64-bit (Docker's supported list, November 2026) |
| GPU | NVIDIA with **6 GB of video memory or more**. The model was tuned on a 6 GB card: its 32,768-token context is the largest that stays fully on that GPU. |
| Disk | About 10 GB free: the AI model is 3.3 GB, plus the Docker images |
| Network, outbound HTTPS | KnowBe4 for your region (below). For the first set-up only: Docker Hub, PyPI, `nvlpubs.nist.gov` (the NIST guidance PDFs) and `registry.ollama.ai` (the model). |
| Network, inbound | Port 443 (through the reverse proxy) or 8080 from the staff network |
| KnowBe4 | A Reporting API key per console; product API keys are optional |

KnowBe4 hosts per region (from `config/settings.py`):

| Region | Reporting API | Product APIs (GraphQL) | User Event API |
|---|---|---|---|
| us | `us.api.knowbe4.com` | `training.knowbe4.com` | `api.events.knowbe4.com` |
| eu | `eu.api.knowbe4.com` | `eu.knowbe4.com` | `api-eu.events.knowbe4.com` |
| ca | `ca.api.knowbe4.com` | `ca.knowbe4.com` | `api-ca.events.knowbe4.com` |
| uk | `uk.api.knowbe4.com` | `uk.knowbe4.com` | `api-uk.events.knowbe4.com` |
| de | `de.api.knowbe4.com` | `de.knowbe4.com` | `api-de.events.knowbe4.com` |

## 2. Install Docker

Use Docker's own repository, not the `docker.io` package from Ubuntu. These are the commands from [Docker's install guide](https://docs.docker.com/engine/install/ubuntu/); check it for changes before you run them.

```bash
sudo apt update
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo docker run hello-world
```

If an older `docker.io`, `docker-compose` or `docker-compose-v2` package is installed, remove it first, as Docker's guide describes.

The commands in this guide use `sudo docker …`. Adding an account to the `docker` group avoids `sudo`, but that group is effectively root, so only do it for administrators.

## 3. Install the NVIDIA driver and Container Toolkit

1. **The driver.** Install the NVIDIA driver for your card the way your organisation normally does (for example `sudo ubuntu-drivers install`). Then reboot and check that `nvidia-smi` lists the GPU.
2. **The Container Toolkit**, which lets containers use the GPU. These commands come from [NVIDIA's install guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html):

   ```bash
   sudo apt-get update && sudo apt-get install -y --no-install-recommends ca-certificates curl gnupg2
   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
     | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
   curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
     | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
     | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
   sudo apt-get update
   sudo apt-get install -y nvidia-container-toolkit
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl restart docker
   ```

3. **Check that a container can see the GPU** ([NVIDIA's sample workload](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/sample-workload.html)):

   ```bash
   sudo docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi
   ```

   It should print the same GPU table as `nvidia-smi` on the server itself.

## 4. Copy the project to the server

Put the project in a folder that only administrators can read, for example `/opt/kb4-chatbot`:

```bash
sudo mkdir -p /opt/kb4-chatbot
sudo chown "$USER": /opt/kb4-chatbot
git clone https://github.com/ZGreatEvil/kb4-reporting-mcp.git /opt/kb4-chatbot
cd /opt/kb4-chatbot
```

Copying a release folder instead of cloning works the same way.

## 5. Configure

There are two files, both created from the templates in the project. Neither is ever committed or copied into the image. They are read when the container starts.

```bash
cp .env.example .env
cp config/consoles.example.yaml config/consoles.yaml
chmod 600 .env
```

**`config/consoles.yaml`** lists your KnowBe4 consoles:

- **The fields:** each console has a short name (used in questions), a `display_name`, a `region` and `api_key_env`. `api_key_env` is the name of the `.env` variable that holds that console's key.
- **More than one console:** the first console that has a key is the default. Questions about another console must name it.
- **Product API keys:** optional, as `ksat_key_env` and the others listed in the file's comments.

**`.env`** holds the keys and settings. For a server, set at least:

| Setting | Value |
|---|---|
| `KB4_MAIN_API_KEY` (one per console, named as in consoles.yaml) | the Reporting API key |
| `WEB_ALLOWED_HOSTS` | every name staff type in the browser, comma-separated, e.g. `kb4-chat.example.internal` (otherwise the page answers "Invalid host header") |
| `WEB_PUBLISH_ADDRESS` | `127.0.0.1` when nginx runs on the same server (recommended), `0.0.0.0` to publish port 8080 on the network |

**Leave these as they are:** `LLM_BASE_URL`, `MCP_HOST`, `WEB_HOST`, `KB4_CONSOLES_FILE` and `KB4_USAGE_FILE`. `docker-compose.yml` overrides them with the right values for the container. Every other setting is explained in `.env.example` and the README's settings table.

**Rules for `.env`:**
- Never paste a key into a chat, ticket or email.
- If a value contains a `$`, wrap it in single quotes, so Docker Compose does not read it as a variable.

## 6. Build and start

```bash
sudo docker compose up -d --build
```

The first start takes several minutes:

1. **Build the app image.** This installs the Python packages and downloads the three NIST PDFs to build the guidance index.
2. **Start Ollama on the GPU.**
3. **Run `ollama-init` once.** It downloads `qwen3.5:4b` (3.3 GB) and creates `kb4-analyst` from `ollama/Modelfile`. Later starts see that the model exists and skip this step.
4. **Start the app** once the model is ready.

`docker compose up -d` waits until the model has been downloaded. That can take a long time on a slow connection. If the command stops or is interrupted, the download carries on in the background: run `sudo docker compose up -d` again once it has finished.

Follow progress with:

```bash
sudo docker compose logs -f ollama-init app
```

Then check everything:

```bash
sudo docker compose ps                    # ollama and app "healthy", ollama-init "exited (0)"
curl -s http://127.0.0.1:8080/health      # "status":"ok", "warnings":[], your consoles listed
sudo docker compose exec app python test_knowbe4.py   # each console's key against KnowBe4
```

**Is the model using the GPU?** Ask one question in the chat, then run `sudo docker compose exec ollama ollama ps`.
- It should show `kb4-analyst` at **100% GPU** with context 32768.
- If it shows CPU, see [Troubleshooting](#13-troubleshooting).

## 7. Give staff access

Choose one of these two options.

### Option A (recommended): nginx with HTTPS and a login

Keep `WEB_PUBLISH_ADDRESS=127.0.0.1`, so port 8080 is only reachable from the server itself, and put nginx in front of it.

1. **Install nginx and the password tool:** `sudo apt install nginx apache2-utils`.
2. **Create the password file** with one account per person. Do not share accounts.

   ```bash
   sudo htpasswd -c /etc/nginx/kb4-chat.htpasswd first.user
   sudo htpasswd /etc/nginx/kb4-chat.htpasswd second.user
   ```

3. **Use a certificate from your internal CA** for the name staff will use.

This is an example site, `/etc/nginx/sites-available/kb4-chat`. Replace the names and paths with yours.

```nginx
server {
    listen 443 ssl;
    server_name kb4-chat.example.internal;

    ssl_certificate     /etc/ssl/certs/kb4-chat.crt;
    ssl_certificate_key /etc/ssl/private/kb4-chat.key;

    auth_basic           "KnowBe4 chat";
    auth_basic_user_file /etc/nginx/kb4-chat.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # answers stream in pieces and can take a few minutes
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
}

server {
    listen 80;
    server_name kb4-chat.example.internal;
    return 301 https://$host$request_uri;
}
```

```bash
sudo ln -s /etc/nginx/sites-available/kb4-chat /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

- Put the same name in `.env` `WEB_ALLOWED_HOSTS`, then apply it with `sudo docker compose up -d`.
- `proxy_buffering off` lets the page show progress while an answer is being written.
- `proxy_read_timeout` must be longer than `LLM_TIMEOUT_SECONDS` (180 by default).

### Option B: open port 8080 to one network only

1. **Publish the port:** set `WEB_PUBLISH_ADDRESS=0.0.0.0` and the server's name in `WEB_ALLOWED_HOSTS`, then run `sudo docker compose up -d`.
2. **Limit who can connect** with the firewall. Staff then open `http://<server-name>:8080`.

Docker's published ports bypass `ufw`'s usual rules. So restrict the port in your network firewall, or follow [Docker's packet filtering guide](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

Option B has **no HTTPS and no login**. Use it only on a network where everyone may see the KnowBe4 data.

## 8. Day-to-day operation

Run these in `/opt/kb4-chatbot`:

| Task | Command |
|---|---|
| Status | `sudo docker compose ps` |
| Health | `curl -s http://127.0.0.1:8080/health` |
| Logs (last hour) | `sudo docker compose logs --since 1h app` |
| Stop / start | `sudo docker compose stop` / `sudo docker compose up -d` |
| Restart after a crash | not needed: containers restart on their own (`restart: unless-stopped`), also after a reboot |
| KnowBe4 requests used (24 h) | `sudo docker compose exec app python -c "import json, time; d = json.load(open('/data/kb4_usage.json')); print({k: sum(time.time() - t < 86400 for t in v) for k, v in d.items()})"` |

**After changing `.env` or `config/consoles.yaml`**, run `sudo docker compose up -d`. `docker compose restart` is not enough: [Docker's docs](https://docs.docker.com/reference/cli/docker/compose/restart/) note that restart does not apply configuration changes.

**Logs:**
- They record which tools ran and which argument names were used. They never record argument values, keys or answers.
- Each container keeps at most 5 × 10 MB of logs.

**The KnowBe4 request limit:**
- KnowBe4 allows 2,000 Reporting API requests plus one per licensed user in each 24-hour period, and 4 a second ([Fair Usage Policy](https://support.knowbe4.com/hc/en-us/articles/45870261990035-KnowBe4-Fair-Usage-Policy-Overview)).
- The app counts its own requests in the `kb4data` volume and stops before the limit. Once the limit is reached, it answers with a fixed message until requests free up.
- Normal use stays far below the limit: repeated questions within 10 minutes come from the cache.
- KnowBe4 counts per key, but the app only knows its own requests. A new install starts counting from zero. If the same key is also used elsewhere, for example by a test PC or another integration, the app's count is lower than KnowBe4's. Give each installation its own key, or keep other use of the key low.

## 9. Updating

```bash
cd /opt/kb4-chatbot
git pull
sudo docker compose up -d --build
sudo docker image prune -f      # removes the old image layers
```

Read `CHANGELOG.md` first for anything to do by hand.

**After a change to `ollama/Modelfile`**, create the model again:

```bash
sudo docker compose exec ollama ollama rm kb4-analyst
sudo docker compose up -d
```

**To update Ollama:** change the version of both `ollama/ollama` images in `docker-compose.yml`, then run `sudo docker compose up -d`.

## 10. Backups

| What | Why | How |
|---|---|---|
| `.env` and `config/consoles.yaml` | the keys and console list | copy them to your secrets store or password manager, never to a shared drive |
| `kb4data` volume | only the 24-hour request counter | not needed; it rebuilds itself |
| `ollama` volume | the model | not needed if the server can download it again; otherwise see section 11 |

The chat does not keep conversations. Charts and files are deleted after an hour, and they are lost when the app container restarts.

## 11. A server without internet access

If the server can reach KnowBe4 but not Docker Hub, PyPI or Ollama, prepare everything on a machine with internet and Docker, then copy it across.

1. **On the machine with internet**, in the project folder, build and start once so the model is downloaded:

   ```bash
   docker compose up -d --build
   docker save kb4-chatbot:latest ollama/ollama:0.40.16 | gzip > kb4-images.tar.gz
   docker run --rm -v kb4-chatbot_ollama:/from -v "$PWD":/to ubuntu tar czf /to/kb4-model.tar.gz -C /from .
   ```

   The compose file names the project `kb4-chatbot`, so the volume is `kb4-chatbot_ollama` whatever the folder is called.

2. **Copy the files to the server:** the project folder (without `.env`), `kb4-images.tar.gz` and `kb4-model.tar.gz`.

3. **On the server:**

   ```bash
   gunzip -c kb4-images.tar.gz | sudo docker load
   sudo docker volume create kb4-chatbot_ollama
   sudo docker run --rm -v kb4-chatbot_ollama:/to -v "$PWD":/from ubuntu tar xzf /from/kb4-model.tar.gz -C /to
   sudo docker compose up -d
   ```

   `ollama-init` then finds the model and does not try to download it.

## 12. Security checklist

- [ ] `.env` is `chmod 600`, owned by an administrator, and not in any backup that others can read.
- [ ] Reporting API keys are the read-only kind. Product API keys have read-only scopes where KnowBe4 offers them. The app only ever reads either way: it refuses GraphQL mutations before sending them.
- [ ] Port 8080 is not reachable from outside the intended network (section 7).
- [ ] Staff reach the chat over HTTPS with a personal login, or on a closed network where everyone may see the data.
- [ ] `WEB_ALLOWED_HOSTS` lists only the names you use.
- [ ] Ollama's port 11434 and the MCP server's port 8000 are not published. `docker-compose.yml` does not publish them; do not add them.
- [ ] Only administrators can run `docker` on the server.
- [ ] When a KnowBe4 key leaks or someone leaves, the key is replaced in KnowBe4 and `.env`, followed by `sudo docker compose up -d`.

## 13. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The app container restarts again and again | `sudo docker compose logs app`. A settings mistake is reported with the variable or consoles.yaml entry it concerns. Fix it, then `sudo docker compose up -d`. |
| `/health` says `degraded` | The `warnings` list says which part: the model, Ollama, the MCP server or a console without a key. |
| Page says "Invalid host header" | Add the name in the address bar to `WEB_ALLOWED_HOSTS`, then `sudo docker compose up -d`. |
| `could not select device driver "nvidia"` | The Container Toolkit is not registered with Docker. Run `sudo nvidia-ctk runtime configure --runtime=docker` and `sudo systemctl restart docker`. |
| `ollama ps` shows CPU, answers take minutes | The GPU is not visible in the container (check section 3, step 3), or another program is using its memory (`nvidia-smi`). |
| `ollama ps` shows 100% GPU, but answers still take minutes | The GPU is running slowly. Check `nvidia-smi --query-gpu=pstate,clocks.sm,clocks.max.sm,power.draw --format=csv` while a question is answered: a low clock or a P8 state under load means a power-saving setting or a power limit. On a test laptop, the same happens on battery: it ran at about 8 tokens a second instead of the normal speed. |
| `ollama-init` failed | `sudo docker compose logs ollama-init`. Usually no access to `registry.ollama.ai`: open it, or use section 11. |
| Answers say the daily KnowBe4 limit is reached | Wait for requests to free up (the message says so). KnowBe4's limit is per 24 hours. |
| HTTP 401 from KnowBe4 | The key is wrong or has expired. Replace it in `.env`, then `sudo docker compose up -d`. |
| Answers stop after about a minute behind nginx | `proxy_read_timeout` is too short, or `proxy_buffering` is still on. |
| Port 8080 already in use | Another service uses it. Change `WEB_PORT` in `.env` (and the nginx `proxy_pass`). |

## 14. Uninstalling

```bash
cd /opt/kb4-chatbot
sudo docker compose down            # stops and removes the containers
sudo docker compose down --volumes  # also deletes the model and the request counter
```

Then delete the folder, including `.env`, with a secure delete if your policy requires it, and revoke the KnowBe4 API keys in the KnowBe4 console.
