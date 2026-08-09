# AEOS — Autonomous Engineering Operating System

**Transform any engineering objective into a verified, production-ready outcome — fully autonomously.**

AEOS is an interactive engineering agent that plans, decomposes, implements with TDD, reviews, and
verifies until your objective is complete. It only stops to ask you critical questions — everything
else runs autonomously.

---

## Table of Contents

- [How AEOS Works](#how-aeos-works)
- [Two Ways to Run](#two-ways-to-run)
- [Method 1 — Interactive REPL (Python)](#method-1--interactive-repl-python)
- [Method 2 — Docker](#method-2--docker)
  - [Understanding What Docker Builds vs What It Mounts](#understanding-what-docker-builds-vs-what-it-mounts)
  - [First-Time Setup](#first-time-docker-setup)
  - [Everyday Docker Workflow](#everyday-docker-workflow)
  - [When to Rebuild vs When to Just Restart](#when-to-rebuild-vs-when-to-just-restart)
  - [Running Subcommands via Docker](#running-subcommands-via-docker)
  - [Reaching Local LLM Servers from Docker](#reaching-local-llm-servers-from-docker)
- [Configuration Reference](#configuration-reference)
- [Local Models — Ollama & LM Studio](#local-models--ollama--lm-studio)
- [Model Routing](#model-routing)
  - [Routing from the CLI](#routing-from-the-cli)
- [TDD Workflow](#tdd-workflow)
- [State & Recovery](#state--recovery)
- [Vertex AI Setup](#vertex-ai-setup)
- [Project Structure](#project-structure)

---

## How AEOS Works

```
You type an objective  →  AEOS plans milestones and decomposes into atomic tasks
                       →  For each task: TDD Red → Green → Refactor → Verify → Review
                       →  Critical questions are asked inline, you answer in the REPL
                       →  State is saved after every operation — safe to interrupt anytime
                       →  Resume from the exact point of interruption
```

---

## Two Ways to Run

| | **REPL (Python)** | **Docker** |
|---|---|---|
| Requires | Python 3.12+ | Docker Desktop |
| Best for | Dev machines, local models | Any machine, CI, no Python needed |
| Interactive REPL | ✓ | ✓ identical experience |
| Local models (Ollama etc.) | ✓ Direct | ✓ Via `host.docker.internal` |
| Config changes | Edit file, restart | Edit file, restart — **no rebuild** |
| AEOS source changes | Restart | Requires `docker build` |
| State persistence | `.aeos/` in project | `.aeos/` volume-mounted from host |

---

## Method 1 — Interactive REPL (Python)

### Install

```bash
pip install -e "c:\Prasanna\antigravity\AEOS"
```

> **Windows PATH note:** If `aeos` isn't found, use this equivalent instead:
> ```bash
> python -m aeos.cli.main        # same as typing `aeos`
> ```
> Or add this folder to your PATH:
> `%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3.12_*\LocalCache\local-packages\Python312\Scripts`

### First-Time Setup

```bash
aeos init
```

This runs an interactive wizard that asks you:
1. Which **provider** to use — Ollama / LM Studio, Anthropic, OpenAI, Vertex AI
2. The **base URL** (for local models)
3. The **model name(s)** for inference/planning and coding tasks

It writes a ready-to-use `~/.aeos/config.yaml`.

> **LM Studio users:** Enter your LM Studio URL (e.g. `http://127.0.0.1:1234`) — AEOS
> automatically detects that LM Studio uses the OpenAI-compatible API and switches to the
> correct `/v1/chat/completions` endpoint. You will be prompted for the exact model ID
> shown in LM Studio (e.g. `lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF`).

### Launch the REPL

```bash
aeos
```

You'll see:

```
  ╔═══════════════════════════════════════════╗
  ║  AEOS  Autonomous Engineering OS          ║
  ╚═══════════════════════════════════════════╝
  Type your objective and press Enter to begin.
  Type /help for commands, /quit to exit.

aeos [INITIALIZE] ❯ _
```

The prompt shows the current workflow stage in brackets. It updates as AEOS progresses.

### Type Your Objective

```
aeos [INITIALIZE] ❯ Build a FastAPI REST service with JWT authentication and PostgreSQL
```

AEOS starts immediately — no flags, no extra arguments. Just type what you want built.

### AEOS Asks Critical Questions Inline

When AEOS needs a decision that affects architecture or irreversible choices, it pauses and asks you
directly inside the REPL:

```
  ┌──────────────────────────────────────────────────────┐
  │ ⚠ Critical Question                                   │
  │                                                       │
  │ Should the JWT tokens use RS256 or HS256 signing?    │
  └──────────────────────────────────────────────────────┘
  Your answer: RS256

  → Recorded: RS256
```

After you answer, AEOS continues autonomously without further interruption.

### REPL Slash Commands

Type these anytime — before, during, or after a session:

| Command | Description |
|---|---|
| `/status` | Task table with stage, status, and verification result per task |
| `/log` | Decision log, lessons learned, and failure history |
| `/providers` | Test connectivity to every configured LLM provider |
| `/config` | Show the resolved routing table (which model handles which tasks) |
| `/route` | Show routing table or change provider+model per task/complexity |
| `/model <name>` | Quick shorthand — set model name across all routes (keeps providers) |
| `/provider` | Register or remove providers without editing config.yaml |
| `/resume` | Resume an interrupted session from its saved stage |
| `/reset` | Archive current session, start fresh with a new objective |
| `/help` | Show all commands |
| `/quit` or `/q` | Exit AEOS — state is always saved before exit |
| `↑ / ↓` | Scroll through your previous objectives |

### Multiple Objectives in One Session

After AEOS completes an objective, you stay in the REPL and can immediately type another:

```
aeos [COMPLETE] ❯ Now add rate limiting to the API
aeos [COMPLETE] ❯ Write an OpenAPI spec for all endpoints
aeos [COMPLETE] ❯ /quit
```

Each objective creates a new session, but your history and decisions from earlier objectives
are preserved in the log.

### Interrupt and Resume

```bash
# Press Ctrl+C at any time
aeos [TASK_EXECUTION_ENGINE] ❯  ^C
⚠ Interrupted. State saved.
Type /resume to continue from here.

# Resume in the same session
aeos [TASK_EXECUTION_ENGINE] ❯ /resume

# Or close and reopen — AEOS detects the existing session
aeos
Session: a3f9c2d1  Stage: TASK_EXECUTION_ENGINE  Status: IN PROGRESS
Objective: Build a FastAPI REST service...

aeos [TASK_EXECUTION_ENGINE] ❯ /resume
```

---

## Method 2 — Docker

### Understanding What Docker Builds vs What It Mounts

This is the most important concept for Docker usage. The image and your config/state are **separate**:

```
What is BAKED into the image (docker build)        What is MOUNTED from your host (volumes)
─────────────────────────────────────────          ──────────────────────────────────────────
• Python runtime                                   • ~/.aeos/config.yaml    → /root/.aeos/config.yaml
• All pip dependencies                             • ~/.aeos/repl_history   → /root/.aeos/repl_history
• AEOS source code (aeos/ directory)               • your-project/.aeos/    → /project/.aeos/
                                                   • API keys               → via -e / .env file
```

**Consequence:** Changing your config, API keys, or session state **never requires a rebuild**.
Only changes to the AEOS source code (the Python files in `aeos/`) require `docker build`.

### First-Time Docker Setup

**Step 1 — Create your config** (one time only)

```bash
# Create the global config directory on your host
mkdir -p ~/.aeos          # macOS/Linux
mkdir "$HOME\.aeos"      # Windows PowerShell

# Copy the example config and fill it in
cp config.example.yaml ~/.aeos/config.yaml     # macOS/Linux
Copy-Item config.example.yaml "$HOME\.aeos\config.yaml"   # Windows
```

Edit `~/.aeos/config.yaml` to add your providers. See [Configuration Reference](#configuration-reference).

**Step 2 — Create your `.env` file** (for API keys)

```bash
cp .env.example .env
```

Open `.env` and fill in your API keys:
```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GROQ_API_KEY=gsk_...
```

**Step 3 — Build the image** (one time only; repeat only when AEOS source changes)

```bash
cd c:\Prasanna\antigravity\AEOS
docker build -t aeos:latest .
```

The build takes 2–3 minutes the first time (downloading dependencies). Subsequent builds are much
faster thanks to Docker layer caching.

**Step 4 — Start the REPL**

```bash
docker compose run --rm aeos
```

You're now in the identical interactive REPL experience.

---

### Everyday Docker Workflow

Once the image is built, your day-to-day is just:

```bash
# Start the REPL
docker compose run --rm aeos

# Or for one-off commands without the REPL
docker compose run --rm aeos aeos status
docker compose run --rm aeos aeos config show
docker compose run --rm aeos aeos providers
```

---

### When to Rebuild vs When to Just Restart

This is the key question. Use this decision table:

| You changed... | What to do |
|---|---|
| `~/.aeos/config.yaml` (added/changed a provider) | Just restart: `docker compose run --rm aeos` |
| `.env` (changed an API key) | Just restart: `docker compose run --rm aeos` |
| `docker-compose.yml` (changed a volume or env var) | Just restart: `docker compose run --rm aeos` |
| A file in `aeos/` (changed AEOS source code) | **Rebuild first:** `docker build -t aeos:latest .` then restart |
| `pyproject.toml` (added a dependency) | **Rebuild first:** `docker build -t aeos:latest .` then restart |
| Nothing — just starting a new work session | Just restart: `docker compose run --rm aeos` |

**Rule of thumb:** Config, keys, and state live outside the image — restart is enough.
Source code lives inside the image — rebuild is required.

#### Config Change Example (no rebuild needed)

```bash
# 1. Edit your config to add a new Ollama model
notepad "$HOME\.aeos\config.yaml"     # Windows
nano ~/.aeos/config.yaml              # macOS/Linux

# 2. That's it — just start AEOS again, it reads the file at startup
docker compose run --rm aeos

# Verify the new provider is visible
aeos [INITIALIZE] ❯ /config
```

#### Source Code Change Example (rebuild required)

```bash
# 1. You edited a file in aeos/ — e.g. aeos/core/agents/planner.py

# 2. Rebuild the image (fast because layers are cached — only changed layers rebuild)
docker build -t aeos:latest .
# Expected output: ... Step 8/12 : COPY . /app  <-- only this layer and below rebuild

# 3. Start as normal
docker compose run --rm aeos
```

---

### Running Subcommands via Docker

For scripting, CI pipelines, or one-off tasks without entering the REPL:

```bash
# Guided setup wizard (writes config template)
docker compose run --rm aeos aeos init

# Validate your config file (exits 1 if invalid)
docker compose run --rm aeos aeos config validate

# Show resolved routing table
docker compose run --rm aeos aeos config show

# Test all provider connections
docker compose run --rm aeos aeos providers

# Show current session status
docker compose run --rm aeos aeos status

# Show decision log
docker compose run --rm aeos aeos log

# One-shot non-interactive run (for CI)
docker compose run --rm aeos aeos run "Add unit tests to the payment module"

# Resume an interrupted session (non-interactive)
docker compose run --rm aeos aeos resume
```

For `docker run` without Compose (useful on machines where you don't have the repo):

```bash
# Windows PowerShell
docker run -it --rm `
  -v "${PWD}:/project" `
  -v "$env:USERPROFILE\.aeos:/root/.aeos" `
  -e ANTHROPIC_API_KEY=$env:ANTHROPIC_API_KEY `
  -e OPENAI_API_KEY=$env:OPENAI_API_KEY `
  --add-host host.docker.internal:host-gateway `
  aeos:latest

# macOS / Linux
docker run -it --rm \
  -v "$(pwd):/project" \
  -v "$HOME/.aeos:/root/.aeos" \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  --add-host host.docker.internal:host-gateway \
  aeos:latest
```

---

### Reaching Local LLM Servers from Docker

When you have Ollama, vLLM, LM Studio, or any other local LLM server running on your
**host machine**, you cannot reach it via `localhost` from inside the container — the container
has its own network namespace. Use `host.docker.internal` instead:

```yaml
# ~/.aeos/config.yaml
providers:
  local_ollama:
    type: ollama
    base_url: "http://host.docker.internal:11434"    # ← NOT http://localhost:11434

  local_vllm:
    type: openai
    base_url: "http://host.docker.internal:8000/v1"  # ← NOT http://localhost:8000/v1

  local_lm_studio:
    type: openai
    base_url: "http://host.docker.internal:1234/v1"
```

The `docker-compose.yml` already includes `extra_hosts: host.docker.internal:host-gateway`,
which enables this. If you use `docker run` directly, add `--add-host host.docker.internal:host-gateway`.

**No rebuild required** after this config change — just restart.

---

### State Persistence with Docker

All session state lives **outside the container** in volume-mounted directories:

```
Host filesystem                     What it contains
────────────────────────────────    ──────────────────────────────────────────────────────
~/.aeos/config.yaml                 Your provider and routing configuration
~/.aeos/repl_history                Up-arrow history of past objectives
./your-project/.aeos/state.json     Current session: stage, tasks, decisions, lessons
./your-project/.aeos/artifacts/     Generated artifacts (plans, designs, test files)
```

You can safely:
- `docker rm` any container — state is untouched
- `docker rmi aeos:latest` and rebuild — state is untouched
- Switch between Python REPL and Docker — they share the same state files

---

## Configuration Reference

AEOS loads config from three layers in this order (each overrides the previous):

| Priority | Location | When to use |
|---|---|---|
| 3 (highest) | `--config <path>` flag | Testing a specific config |
| 2 | `.aeos/config.yaml` in project dir | Project-specific model choices |
| 1 (base) | `~/.aeos/config.yaml` | Your global default providers |

### Provider Setup

The `type` field selects the **protocol**. The `base_url` points to **any host** — the same
`openai` type works for OpenAI cloud, vLLM, LM Studio, Groq, Together, or any OpenAI-compatible server:

```yaml
providers:
  # ── Local models on this machine ──────────────────────────
  local_ollama:
    type: ollama
    base_url: "http://localhost:11434"
    # When using Docker: "http://host.docker.internal:11434"

  local_vllm:                          # Also works for LM Studio, llama.cpp
    type: openai
    base_url: "http://localhost:8000/v1"
    # No api_key_env needed for local endpoints

  local_lm_studio:
    type: openai
    base_url: "http://localhost:1234/v1"

  # ── Local models on another machine ───────────────────────
  team_gpu_server:
    type: ollama
    base_url: "http://192.168.1.100:11434"

  team_vllm_server:
    type: openai
    base_url: "http://192.168.1.50:8000/v1"
    api_key_env: TEAM_VLLM_KEY         # optional API key

  # ── Local Anthropic-compatible proxy (LiteLLM etc.) ───────
  local_proxy:
    type: anthropic
    base_url: "http://localhost:4000"
    api_key_env: LOCAL_PROXY_KEY

  # ── Cloud providers ───────────────────────────────────────
  openai_cloud:
    type: openai
    base_url: "https://api.openai.com/v1"
    api_key_env: OPENAI_API_KEY

  anthropic_cloud:
    type: anthropic
    api_key_env: ANTHROPIC_API_KEY     # no base_url needed for Anthropic cloud

  vertex_ai:
    type: vertex_ai
    project: my-gcp-project
    location: us-central1              # uses Application Default Credentials

  # ── OpenAI-compatible cloud APIs ──────────────────────────
  groq:
    type: openai
    base_url: "https://api.groq.com/openai/v1"
    api_key_env: GROQ_API_KEY

  together:
    type: openai
    base_url: "https://api.together.xyz/v1"
    api_key_env: TOGETHER_API_KEY

  fireworks:
    type: openai
    base_url: "https://api.fireworks.ai/inference/v1"
    api_key_env: FIREWORKS_API_KEY
```

---

## Local Models — Ollama & LM Studio

### API Protocol Auto-Detection

AEOS auto-detects the API protocol from the `base_url`:

| Server | Default port | Protocol auto-selected |
|---|---|---|
| Ollama | `11434` | Native Ollama API (`POST /api/chat`) |
| LM Studio | `1234` | OpenAI-compatible (`POST /v1/chat/completions`) |
| vLLM | `8000` | OpenAI-compatible (`POST /v1/chat/completions`) |
| llama.cpp server | any | OpenAI-compatible (`POST /v1/chat/completions`) |

Any `base_url` other than `http://localhost:11434` is automatically treated as an OpenAI-compatible server. Override explicitly with `openai_compat: true/false` if needed.

---

### Token Budget — `context_window` vs `max_tokens`

Local models have a **fixed total context window**: the sum of prompt tokens and completion tokens cannot exceed it. If AEOS asks for more completion tokens than the window can accommodate, the server rejects the request immediately:

```
[ERROR] Channel Error          ← LM Studio / llama.cpp
RetryError[HTTPStatusError]    ← the AEOS side of the same error
```

Two config fields control this. They serve **different purposes**:

| Field | What it represents | When to use |
|---|---|---|
| `context_window` | **Total** token capacity (prompt + completion combined) | Simple — just tell AEOS the model's limit, it does the math |
| `max_tokens` | Hard cap on **completion tokens only** sent in the request | Advanced — when you need exact control over the output budget |

**Resolution priority (highest wins):**

```
1. provider.max_tokens is set
       → cap = min(requested, max_tokens)

2. provider.context_window is set, max_tokens is not
       → cap = min(requested, context_window / 2)
          (reserves the other half of the window for the prompt)

3. Neither is set
       → cap = min(requested, 2048)   [AEOS built-in safe default]
```

**Worked examples:**

```
context_window=4096, max_tokens not set
  → effective cap = 4096 / 2 = 2048
  → safe for prompts up to ~2000 tokens

context_window=4096, max_tokens=1500
  → effective cap = 1500   (max_tokens wins)
  → more headroom for large system prompts

context_window=32768, max_tokens not set   (← e.g. Llama 3.1 extended)
  → effective cap = 16384
  → generous; you may want an explicit max_tokens anyway
```

**Config examples:**

```yaml
providers:

  # Simplest — just declare the model's total context, AEOS handles the rest
  local_lm_studio:
    type: ollama
    base_url: "http://127.0.0.1:1234"
    context_window: 4096          # ← AEOS will cap completions at 2048

  # Advanced — override when your system prompts are unusually large
  local_lm_studio:
    type: ollama
    base_url: "http://127.0.0.1:1234"
    context_window: 4096
    max_tokens: 1200              # explicit cap; max_tokens always wins

  # Native Ollama — auto-detected from default port
  local_ollama:
    type: ollama
    base_url: "http://localhost:11434"
    context_window: 4096
```

---


## Model Routing

Map each task type and complexity to the right provider and model. You define this once in config;
AEOS routes automatically based on what each task needs:

```yaml
routing:
  inference:                           # requirements analysis, architecture decisions
    high:   { provider: anthropic_cloud, model: claude-opus-4-5 }
    medium: { provider: openai_cloud,    model: gpt-4o }
    low:    { provider: local_ollama,    model: mistral }

  coding:                              # implementation, refactoring
    high:   { provider: anthropic_cloud, model: claude-sonnet-4-5 }
    medium: { provider: local_vllm,      model: qwen2.5-coder-7b }
    low:    { provider: local_ollama,    model: codellama:7b }

  planning:                            # decomposition, milestone planning
    high:   { provider: anthropic_cloud, model: claude-opus-4-5 }
    medium: { provider: local_ollama,    model: llama3.1:8b }
    low:    { provider: local_ollama,    model: phi3:mini }

  verification:                        # test generation — SLMs handle this well
    high:   { provider: openai_cloud,    model: gpt-4o }
    medium: { provider: local_ollama,    model: codellama:7b }
    low:    { provider: local_ollama,    model: codellama:7b }

  review:                              # artifact quality and acceptance criteria
    high:   { provider: anthropic_cloud, model: claude-opus-4-5 }
    medium: { provider: openai_cloud,    model: gpt-4o }
    low:    { provider: local_ollama,    model: mistral }
```

**How complexity is assigned:**
- Decomposed subtasks are always `low` — designed for SLMs, keeping cloud costs low
- Complex architecture decisions use `high` — only where it genuinely matters
- Verification (writing tests) uses `low` — SLMs are excellent at this

**Check your routing at any time:**
```bash
aeos [INITIALIZE] ❯ /config       # in REPL
aeos config show                   # CLI
docker compose run --rm aeos aeos config show    # Docker
```

### Routing from the CLI

You can change routing live from the REPL without editing `config.yaml` manually.
All changes are written to disk and reloaded immediately.

#### `/route` — granular provider + model control

```
# Show the full routing table
/route

# Set a single cell: /route set <task_type> <complexity> <provider> <model>
/route set coding    high   anthropic_cloud  claude-sonnet-4-5
/route set inference high   anthropic_cloud  claude-opus-4-5
/route set inference medium openai_cloud     gpt-4o
/route set inference low    local_ollama     mistral

# Set all complexity tiers for one task type: /route <task_type> <provider> <model>
/route coding  local_ollama  codellama:7b
/route review  anthropic_cloud  claude-opus-4-5

# Set every single route to the same provider + model
/route local_lm_studio  lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF
```

Valid `task_type` values: `inference`, `coding`, `planning`, `review`, `verification`  
Valid `complexity` values: `high`, `medium`, `low`

#### `/model` — quick model swap (keeps providers)

```
# Show routing table
/model

# Change only the model name across all routes (providers are unchanged)
/model mistral
/model llama3.2:3b
```

Use `/model` for quick local-only experiments. Use `/route set` when you need
full provider + model control.

#### `/provider` — register new providers without editing files

```
# List configured providers
/provider list

# Register a new Ollama or LM Studio server
/provider add local_vllm  ollama  http://127.0.0.1:8000
/provider add lm_studio   ollama  http://127.0.0.1:1234

# Register an OpenAI-compatible cloud endpoint
/provider add openai_cloud  openai  https://api.openai.com/v1  OPENAI_API_KEY
/provider add groq          openai  https://api.groq.com/openai/v1  GROQ_API_KEY

# Register Anthropic
/provider add anthropic_cloud  anthropic  ANTHROPIC_API_KEY

# Remove a provider (warns if routing still references it)
/provider remove local_vllm
```

After adding a provider, point routes to it:
```
/route set coding medium local_vllm  qwen2.5-coder-7b
/route set coding low    local_vllm  qwen2.5-coder-7b
```

#### Full workflow example — mix cloud + local

```
# Start from a local-only setup and add cloud providers
/provider add anthropic_cloud  anthropic  ANTHROPIC_API_KEY
/provider add openai_cloud     openai     https://api.openai.com/v1  OPENAI_API_KEY

# Route heavy tasks to cloud, light tasks to local
/route set inference high   anthropic_cloud  claude-opus-4-5
/route set inference medium openai_cloud     gpt-4o
/route set inference low    local_ollama     mistral

/route set coding high   anthropic_cloud  claude-sonnet-4-5
/route set coding medium local_ollama     codellama:7b
/route set coding low    local_ollama     codellama:7b

# Verify
/config
```

---

## TDD Workflow

Every implementation task goes through this cycle, fully automated:

```
1. Red       VerifierAgent writes failing tests (tests must FAIL before implementation starts)
             → Tests saved to .aeos/tests/
             → pytest runs — confirms red

2. Green     ImplementerAgent writes minimum code to make tests pass
             → pytest runs — must turn green
             → If still failing: retry up to max_retries times with updated context

3. Refactor  ImplementerAgent improves code quality
             → pytest runs again — tests must stay green
             → If refactor breaks tests: refactor is reverted, green version kept

4. Verify    Results analysed by VerifierAgent
             → Coverage checked, output parsed

5. Review    ReviewerAgent issues a verdict:
             PASS     → task complete, advance to next
             REVISE   → minor issues, fix and resubmit
             RETRY    → try again with the same approach
             REPLAN   → decompose differently, start over for this task
             REJECT   → escalate — critical question asked to user
```

---

## State & Recovery

All state is saved to `.aeos/state.json` in your project directory after every single operation.

**Nothing is lost on interruption.** AEOS recovers to the exact stage, the exact task,
even the exact TDD phase it was in when interrupted.

```bash
# In the REPL
aeos [TASK_EXECUTION_ENGINE] ❯ /resume

# CLI
aeos resume

# Docker
docker compose run --rm aeos aeos resume

# What state contains:
# - Current workflow stage (e.g. TASK_EXECUTION_ENGINE)
# - Full task graph with status of each task
# - Retry history per task
# - All decisions made and reasons
# - Lessons learned from completed tasks
# - Verification results
# - Pending critical questions
```

---

## Vertex AI Setup

```bash
# Authenticate on your host machine
gcloud auth application-default login
```

```yaml
# ~/.aeos/config.yaml
providers:
  vertex_ai:
    type: vertex_ai
    project: your-gcp-project
    location: us-central1
```

**With Docker**, mount your credentials into the container:

```bash
# Docker run
docker run -it --rm \
  -v "$HOME/.config/gcloud:/root/.config/gcloud:ro" \
  -v "$(pwd):/project" \
  -v "$HOME/.aeos:/root/.aeos" \
  aeos:latest

# Docker Compose — add to docker-compose.yml volumes section:
# - ${HOME}/.config/gcloud:/root/.config/gcloud:ro
```

No rebuild required — this is just a volume mount change.

---

## Project Structure

```
AEOS/
├── Dockerfile                  # Multi-stage build (builder + slim runtime)
├── docker-compose.yml          # Docker Compose with volumes, env vars, host-gateway
├── .dockerignore               # Excludes secrets, caches, state from image
├── .env.example                # API key template — copy to .env and fill in
├── pyproject.toml              # Python package declaration + dependencies
├── config.example.yaml         # Fully annotated example config (all provider types)
├── pytest.ini                  # Test configuration
│
├── aeos/
│   ├── cli/
│   │   ├── main.py             # Entry point — `aeos` with no args → REPL
│   │   ├── repl.py             # Interactive REPL (prompt_toolkit + rich)
│   │   ├── run.py              # One-shot non-interactive run (for CI/scripts)
│   │   ├── init_cmd.py         # Guided setup wizard
│   │   ├── status.py           # Status display
│   │   └── config_cmd.py       # `aeos config validate` and `aeos config show`
│   │
│   ├── prompts/                # Jinja2 templates for each agent
│   │   ├── system.j2           # Master system context injected into all agents
│   │   ├── planner.j2          # Project plan → milestones → tasks
│   │   ├── decomposer.j2       # Task decomposition with TDD ordering
│   │   ├── verifier.j2         # Test generation (TDD Red phase)
│   │   ├── implementer.j2      # Implementation (TDD Green + Refactor)
│   │   └── reviewer.j2         # PASS/REVISE/RETRY/REPLAN/REJECT verdict
│   │
│   └── core/
│       ├── config/             # Pydantic schema + 3-layer YAML loader
│       ├── providers/          # OpenAI, Anthropic, Vertex AI, Ollama adapters + router
│       ├── agents/             # Planner, Decomposer, Designer, Implementer,
│       │                       #   Reviewer, Verifier (each uses router for model selection)
│       ├── state/              # Persistent AEOSState + atomic save with backup rotation
│       ├── tasks/              # Priority queue, TDD executor, recursive decomposer
│       ├── artifacts/          # Artifact schema + file store (.aeos/artifacts/)
│       ├── tools/              # Shell (async), filesystem, git, browser (httpx)
│       ├── workflow/           # WorkflowStage enum, transition table, engine (state machine)
│       └── reflection.py       # Captures lessons after each task/stage for future prompts
│
└── tests/                      # 76 tests, all passing
    ├── conftest.py             # Fixtures: minimal config, temp workspace, fresh state
    ├── test_config.py          # Schema validation, routing resolution, env-var injection
    ├── test_state.py           # TaskRecord, AEOSState, StateManager persistence + recovery
    ├── test_providers.py       # All 4 adapters + router
    ├── test_workflow.py        # Stage lifecycle, transitions, task queue ordering
    └── test_tools.py           # Shell, filesystem, git, artifact store
```
