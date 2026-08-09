# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tooling only
RUN pip install --upgrade pip wheel setuptools

# Copy dependency declaration first (layer-cached until pyproject.toml changes)
COPY pyproject.toml ./
COPY aeos/__init__.py ./aeos/__init__.py

# Pre-download all dependencies into a wheel cache
RUN pip wheel --no-cache-dir --wheel-dir /wheels \
    "anthropic>=0.21.0" \
    "openai>=1.30.0" \
    "pydantic>=2.7.0" \
    "pydantic-settings>=2.2.0" \
    "pyyaml>=6.0.1" \
    "jinja2>=3.1.3" \
    "rich>=13.7.1" \
    "typer>=0.12.3" \
    "prompt_toolkit>=3.0.47" \
    "httpx>=0.27.0" \
    "gitpython>=3.1.43" \
    "anyio>=4.4.0" \
    "tenacity>=8.3.0" \
    "aiohttp>=3.9.5" \
    "python-dotenv>=1.0.1"


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="AEOS"
LABEL org.opencontainers.image.description="Autonomous Engineering Operating System"
LABEL org.opencontainers.image.version="0.1.0"

# System dependencies for git operations
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Configure git for container use
RUN git config --global --add safe.directory /project && \
    git config --global user.email "aeos@autonomous.dev" && \
    git config --global user.name "AEOS"

WORKDIR /app

# Install pre-built wheels from builder stage
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl && \
    rm -rf /wheels

# Copy the AEOS source
COPY . /app

# Install AEOS itself (editable for config discovery)
RUN pip install --no-cache-dir -e /app

# ── Directories ───────────────────────────────────────────────────────────────
# /project   → mounted from host (the project being engineered)
# /root/.aeos → mounted from host (config + history)
RUN mkdir -p /project /root/.aeos

# ── Environment defaults ───────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TERM=xterm-256color \
    AEOS_PROJECT_DIR=/project \
    AEOS_CONFIG_DIR=/root/.aeos

# ── Entrypoint ────────────────────────────────────────────────────────────────
# Default: interactive REPL (same as running `aeos` with no args)
# Can be overridden with any aeos subcommand, e.g.:
#   docker run ... aeos-image aeos init
#   docker run ... aeos-image aeos config show
ENTRYPOINT ["python", "-m", "aeos.cli.main"]
CMD []
