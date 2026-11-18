# web chat + mcp server in one image. no keys or consoles in here: .env and consoles.yaml are supplied at run time
# (see docker-compose.yml and docs/INSTALL_SERVER.md)
FROM python:3.12.16-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY config/__init__.py config/settings.py config/consoles.example.yaml config/
COPY agent agent
COPY kb4_mcp kb4_mcp
COPY knowbe4 knowbe4
COPY web web
COPY run_mcp.py run_web.py test_knowbe4.py ./
COPY docker/start.py docker/start.py
# package metadata only, so /health reports the real version (the dependencies are already installed)
COPY pyproject.toml README.md ./
RUN pip install --no-deps . && rm -rf build *.egg-info

# the nist guidance library (public pdfs); only the search index is kept
RUN python -m kb4_mcp.knowledge && rm -rf knowledge/pdfs

RUN useradd --uid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin kb4 \
    && mkdir -p /data web/static/charts exports \
    && chown kb4:kb4 /data web/static/charts exports
USER kb4

ENV MCP_HOST=127.0.0.1 \
    WEB_HOST=0.0.0.0 \
    KB4_USAGE_FILE=/data/kb4_usage.json

EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=30s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('WEB_PORT', '8080') + '/health', timeout=25)"]

CMD ["python", "docker/start.py"]
