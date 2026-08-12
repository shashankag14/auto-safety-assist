# Docker Learnings

Notes from containerizing the three FastAPI microservices (`intent_classifier`, `retriever`, `response_generator`) with `uv`-managed dependencies.

### Useful Links

- https://devopscycle.com/blog/the-ultimate-docker-cheat-sheet
- https://devopscycle.com/blog/how-do-you-choose-a-docker-base-image
- https://wbarillon.medium.com/docker-python-image-with-psycopg2-installed-c10afa228016

---

## 1. Base image

- Started with `python:3.13-slim` for all three services. Slim over full: much smaller, still Debian-based (has `apt-get` when you need to add system libs).
- Avoided Alpine: it uses musl libc instead of glibc, which breaks the prebuilt `manylinux` wheels that heavy packages like `torch`/`sentence-transformers` rely on — would mean compiling those from source, which is painful and slow.
- Naming gotcha: `slim` (no suffix) floats to whatever Debian release is currently stable (e.g. moved from `bookworm` → `trixie`). Pin explicitly (`python:3.13-slim-bookworm`) if you want a reproducible, non-moving base.

## 2. Multi-stage builds

Every service Dockerfile has two stages:

```dockerfile
FROM python:3.13-slim AS builder
# ... install build tools, sync deps, copy source, sync project ...

FROM python:3.13-slim AS runtime
# ... copy only .venv + src from builder, run as non-root, set entrypoint ...
```

Why: build-only tools (`gcc`, `libpq-dev` for compiling `psycopg2`) are needed to *build* the venv, but should never ship in the final image. Multi-stage lets the builder stage carry all that weight, then the runtime stage cherry-picks only `/app/.venv` and `/app/src` via `COPY --from=builder`, leaving the compiler tooling behind entirely.

**Gotcha (real bug we hit):** installing `libpq-dev`/`gcc` only in the builder stage is enough to *compile* `psycopg2`, but `psycopg2` also dynamically links against `libpq.so.5` **at import time**, not just build time. The runtime stage is a fresh image that never installed that shared library, so `import psycopg2` failed with `libpq.so.5: cannot open shared object file`. Fix: install the runtime-only counterpart in the runtime stage too:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*
```

(`libpq5` = shared library only, no compiler needed there — `libpq-dev` stays builder-only.)

## 3. `uv` + Docker

- Copy `uv` itself from its official image rather than pip-installing it: `COPY --from=docker.io/astral/uv:latest /uv /uvx /usr/local/bin/`.
- Two-step `uv sync` pattern for better layer caching:
  1. `COPY pyproject.toml uv.lock ./` then `RUN uv sync --frozen --no-dev --no-install-project --group <service>` — installs *only dependencies*, cached as long as the lockfile doesn't change.
  2. `COPY` the actual source, then `RUN uv sync --frozen --no-dev --group <service>` again — installs the project itself. Changing source code doesn't bust the (expensive) dependency-install layer from step 1.
- `--group <service>` per-service dependency groups (`intent-classifier`, `retriever`, `response-generator` in `pyproject.toml`) mean each service only installs what it actually imports — e.g. `intent_classifier` never pulls in `torch`/`psycopg2`, which `retriever` needs. Packages shared by all three (`fastapi`, `uvicorn`, `loguru`, `pydantic`, `python-dotenv`) stay in the top-level `[project.dependencies]`.
- **Windows vs Linux venv layout**: `uv sync` run *inside the Linux container* creates `.venv/bin/`, not `.venv/Scripts/` — even though a venv created locally on Windows uses `Scripts/`. These are two entirely separate venvs (host vs. container filesystem); never `COPY` a locally-built Windows `.venv` into a Linux image, always let `uv sync` build it fresh inside the container.
- Put the venv on `PATH` in the runtime stage so bare commands like `uvicorn` work without activation: `ENV PATH="/app/.venv/bin:$PATH"`. (Activating a venv via `RUN source .venv/bin/activate` doesn't work across Dockerfile instructions anyway — each `RUN` is a fresh shell, so anything an activate script exports dies with that shell.)

## 4. Dockerfile instruction gotchas

- **`ENV KEY=value`, no spaces around `=`.** Writing `ENV HF_HOME = .cache/huggingface` (with spaces) doesn't error — it silently falls back to Docker's legacy `ENV <key> <value>` form, which takes *everything after the key* as a literal value, stray `=` included. Actual value ended up being the string `"= .cache/huggingface"`, not the path. Always write `ENV KEY=value` tight, no spaces.
- **Shell form vs exec form.** `ENTRYPOINT ["uvicorn", "..."]` (exec form, JSON array) runs the binary directly as PID 1 — proper signal handling (`SIGTERM` on `docker stop` reaches the process cleanly). `ENTRYPOINT uvicorn ...` (shell form) quietly runs it as `/bin/sh -c "uvicorn ..."`, making the *shell* PID 1 instead, which doesn't forward signals properly → slow/dirty shutdowns. Always prefer exec form.
- **Exec-form arrays don't do variable substitution.** `CMD ["--port", "$PORT"]` will NOT expand `$PORT` — no shell is involved to do that expansion, so it's passed through as the literal string `"$PORT"`. Variable substitution across an exec-form array simply isn't a thing; you'd need shell form (and accept its signal-handling downside) or bake the value in via a mechanism that runs before container start.
- **`ENTRYPOINT` vs `CMD`.** `ENTRYPOINT` = the fixed program that always runs. `CMD` = default *arguments*, which get silently appended to `ENTRYPOINT` (not replacing it) unless overridden. Splitting them lets you override just the port without rebuilding or retyping the whole command:
  ```dockerfile
  ENTRYPOINT ["uvicorn", "src.services.retriever.retriever:retriever_api", "--host", "0.0.0.0"]
  CMD ["--port", "8001"]
  ```
  `docker run retriever --port 9000` overrides only the `CMD` part.
- **`EXPOSE` is documentation only.** It does not open, publish, or restrict any port — purely informational metadata (and enables `docker run -P` to auto-publish). The actual reachability decision happens at `docker run -p ...` time.
- **`ARG` vs `ENV`.** `ARG` only exists during the *build* (`docker build --build-arg X=Y`) and isn't automatically available inside the running container. Also: `ARG` values used in build steps get recorded in `docker history` — **never** put secrets in an `ARG`. Also learned: a build-time `ARG` is usually the wrong tool for something like "which port to listen on" — that's a run-time decision; the `ENTRYPOINT`/`CMD` split above already solves it without any rebuild.
- **`--chown` on `COPY`.** `COPY --from=builder --chown=appuser:appusergroup /app/.venv /app/.venv` sets file ownership at copy time, so files copied while still root (before `USER appuser` runs) are immediately owned by the non-root user instead of relying on root-owned files happening to be world-readable/executable.

## 5. Non-root user

```dockerfile
RUN groupadd -r appusergroup && useradd -r -g appusergroup appuser
...
USER appuser
```

Running as root inside a container is a real risk:
- If an attacker gets code execution (bad dependency, injection, whatever), they get it as root.
- Combined with container misconfigurations (mounted Docker socket, escape vulnerabilities), root-in-container can sometimes translate into host-level privilege.
- Even without an escape, root can read/write/modify anything in that container's own filesystem without restriction.

## 6. Secrets

- **Never bake `.env`/secrets into the image.** Image layers are cumulative and immutable — a secret written in one layer is still recoverable via `docker history`/layer inspection even if a *later* layer deletes the file. `python-dotenv`'s `load_dotenv()` also doesn't override variables already present in the real environment and doesn't error if no `.env` is found — so it's safe to just not ship one, and inject real env vars at container-start time instead.
- **Runtime secrets → `docker run --env-file .env`** (or `-e KEY=value` for one-offs, or Compose `env_file:`). Values only exist in the running container, never in the image itself.
- **`-e` overrides `--env-file`** for the same key — useful for keeping one shared `.env` as the "local truth" while overriding a single value just for the containerized run, e.g. `POSTGRES_HOST=localhost` in `.env` (for running the script directly on Windows) overridden to `host.docker.internal` only via `-e` when running in Docker — no need for two near-duplicate env files.
- **Build-time secrets (e.g. `HF_TOKEN` to speed up/authenticate a Hugging Face download during `docker build`) need a different mechanism** — `ARG`+`ENV` bakes them into `docker history` permanently. Correct approach: BuildKit secret mounts, scoped to a single `RUN`, never written to any layer:
  ```dockerfile
  # syntax=docker/dockerfile:1
  RUN --mount=type=secret,id=hf_token \
      HF_TOKEN=$(cat /run/secrets/hf_token) \
      uv run python -c "..."
  ```
  ```bash
  docker build --secret id=hf_token,env=HF_TOKEN -t retriever .
  ```
- **Endpoint-level risk beyond the Dockerfile:** `EXPOSE`/`--host 0.0.0.0` are not a security boundary by themselves (see networking section). The real risk for something like `/classify` (unauthenticated, calls OpenAI per request) is that anyone who can reach the port can rack up usage against the API key with no rate limiting. Layered mitigation: keep internal services off any published port entirely (only a gateway/public-facing service gets `-p`), add a simple shared-secret header check between internal services as defense-in-depth, and set a hard spending cap on the OpenAI project as a backstop regardless.

## 7. Networking — the two `0.0.0.0` / `127.0.0.1` questions

These come up in two *different* directions and easily get conflated:

**a) Inbound — can something *outside* the container reach the app?**

```
[ host's network interfaces ] --publish (-p)--> [ container's network ] --bind (--host)--> [ uvicorn ]
```

- `--host 0.0.0.0` (inside the container / in the `ENTRYPOINT`) — mandatory plumbing, not really a security choice. Docker delivers forwarded traffic to the container via its internal bridge interface, not the container's own loopback. If uvicorn only bound `127.0.0.1` *inside* the container, Docker's `-p` forwarding literally couldn't reach it, full stop.
- `-p 127.0.0.1:8000:8000` vs `-p 8000:8000` (on `docker run`, host side) — **this** is the actual access-control decision. `127.0.0.1:...` restricts the published port to processes on your own machine; omitting the host IP defaults to binding all of the host's interfaces, reachable from your LAN (and the internet, if the host has a public IP with no firewall).
- You cannot browse to `http://0.0.0.0:8000` — `0.0.0.0` is a "listen on everything" bind address, not a routable destination a client can connect *to*. Use `http://127.0.0.1:8000` or `http://localhost:8000` instead.

**b) Outbound — can the container reach something on the host?**

- `localhost`/`127.0.0.1` *inside* a container refers to the container itself, not the host machine. Hit this running `retriever` against a Postgres instance installed natively on Windows: `get_postgres_config()` defaulted `POSTGRES_HOST=localhost`, which inside the container pointed at nothing.
- Fix: **`host.docker.internal`** — a Docker Desktop-provided DNS name that resolves to the host machine's IP from inside any container. Solves exactly this "container needs to reach a service running directly on the host OS" case.
  - Docker Desktop (Windows/Mac) only. On plain Linux Docker Engine, add `--add-host=host.docker.internal:host-gateway` to get the same behavior.
  - If Postgres were itself containerized instead, the fix would be different: put both containers on the same user-defined Docker network and use the Postgres container's name — Docker's built-in DNS resolves container names automatically.
- Getting DNS resolution right isn't the whole story — Postgres has its own access control, independent of Docker:
  - `postgresql.conf`'s `listen_addresses` must not be restricted to `localhost` only (`'*'` works).
  - `pg_hba.conf` must have a rule permitting the Docker network's IP range, e.g. `host all all 172.16.0.0/12 scram-sha-256` (covers the ranges Docker Desktop's bridge/WSL2 networking typically uses).
  - Symptom difference: "connection refused" = traffic isn't reaching Postgres at all (network/listen_addresses issue). A `pg_hba.conf` rejection reads differently ("no pg_hba.conf entry for host...") — that means traffic *did* arrive and got turned away at the access-control step.
  - Windows Firewall is a possible remaining blocker even after both configs are correct — Docker Desktop's WSL2 virtual adapter sometimes lands under the "Public" network profile, which Windows Firewall blocks by default.

## 8. Image size

Multi-stage builds aren't the only size lever. Biggest one we hit: **PyPI's default `torch` wheel bundles full CUDA/cuDNN/NCCL binaries** for GPU support, even though `retriever` only runs a small CPU embedding model (`all-MiniLM-L6-v2`) via `sentence-transformers`. That alone accounted for multiple GB out of an ~8GB image.

Diagnose before guessing — check which layer is actually heavy:

```bash
docker history retriever --format "{{.Size}}\t{{.CreatedBy}}" | sort -rh | head -20
```

Fix: point `uv` at PyTorch's CPU-only wheel index instead of the default GPU-enabled one:

```toml
[tool.uv.sources]
torch = { index = "pytorch-cpu" }

[[tool.uv.index]]
name = "pytorch-cpu"
url = "https://download.pytorch.org/whl/cpu"
explicit = true
```

Then `uv lock` + rebuild. Smaller, secondary wins: `apt-get install -y --no-install-recommends ... && rm -rf /var/lib/apt/lists/*` in the *same* `RUN` (deleting the apt index in a later layer doesn't reclaim space — layers are append-only, so cleanup only helps if it's in the same layer as the install).

## 9. Baking the embedding model into the image (avoid a per-container-start download)

`get_embedding_model()` calls `SentenceTransformer("all-MiniLM-L6-v2")`, which downloads from Hugging Face on first use if not cached. Two options:

- **Volume-mounted cache** (`-v hf-cache:/home/appuser/.cache/huggingface`) — simplest, no Dockerfile changes, but the *first* run on any given machine still needs network access.
- **Bake it into the image at build time** — fully self-contained, works with zero network access at container start, at the cost of ~80-90MB extra image size:
  ```dockerfile
  ENV HF_HOME=/app/.cache/huggingface
  RUN uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2', device='cpu')"
  ```
  then in the runtime stage, copy that cache dir over and set the same env var + `HF_HUB_OFFLINE=1` (fail loudly instead of silently hitting the network if the cache is ever missing).

**Gotcha we actually hit:** passing `cache_folder=$HF_HOME` *explicitly* to `SentenceTransformer(...)` at build time uses that path as-is. But the runtime code (`get_embedding_model()`) calls `SentenceTransformer(model_name)` with **no** `cache_folder` argument — it relies purely on the `HF_HOME` env var, which `huggingface_hub` resolves to **`$HF_HOME/hub`** (not `$HF_HOME` itself) by convention. Result: build time wrote the model under `$HF_HOME/models--.../`, runtime looked under `$HF_HOME/hub/models--.../` — a real, physical mismatch, and with `HF_HUB_OFFLINE=1` set it couldn't fall back to downloading either. **Fix: don't pass `cache_folder` explicitly at all** — let both the build-time download and the runtime load resolve their cache location the same way, purely from the `HF_HOME` env var, so they can't drift apart.

## 10. `.dockerignore`

One file at the repo root covers all three services (their Dockerfiles all use the repo root as build context). Main entries: `.git/`, `.env`, `.venv/` (Windows-built, wrong platform for the Linux image anyway, and shouldn't leak in even via a future `COPY . .`), `__pycache__/`, editor folders, and project data/docs folders not needed at runtime. Careful not to exclude anything an explicit `COPY` actually names (`pyproject.toml`, `uv.lock`, `src/`) — `.dockerignore` patterns apply to *any* `COPY`, not just wildcard ones.

## Useful commands

```bash
# build
docker build -f src/services/retriever/Dockerfile -t retriever .

# run, standalone local testing
docker run --rm --env-file .env -e POSTGRES_HOST=host.docker.internal -p 127.0.0.1:8001:8001 --name retriever retriever

# get a shell in a fresh container without auto-starting the app (skip the ENTRYPOINT)
docker run --rm -it --entrypoint sh --env-file .env retriever

# shell into an already-running container
docker exec -it retriever sh

# see which layer is actually contributing to image size
docker history retriever --format "{{.Size}}\t{{.CreatedBy}}" | sort -rh | head -20
```
