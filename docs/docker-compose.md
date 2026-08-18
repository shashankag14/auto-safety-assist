# Docker Compose Learnings

Notes from wiring `postgres` + the three FastAPI services + the `ingestion` batch job together in `docker-compose.yml`. Companion to [docker.md](./docker.md), which covers per-service Dockerfiles.

## 1. `build.context` vs `build.dockerfile`

`dockerfile:` is a path **relative to `context:`**, not to the compose file's own location:

```yaml
build:
  context: .
  dockerfile: src/services/retriever/Dockerfile
```

**Gotcha we hit:** tried narrowing `context` to `src/services/intent_classifier/` so `dockerfile: Dockerfile` could stay simple. This breaks the build — `context` isn't just "where the Dockerfile lives," it's the *entire set of files the Dockerfile is allowed to `COPY` from*. Since the Dockerfile does `COPY pyproject.toml uv.lock ./` and reaches into the sibling `src/common/`, the context has to stay the repo root (`.`) no matter where the Dockerfile file itself sits. A Dockerfile can never reach outside its own context, regardless of path syntax used inside it.

## 2. Bind mounts: destination path must match the in-image path exactly

A bind mount doesn't merge with or "find" existing content by name — it just makes the host path appear at exactly the container path you specify, nothing smarter than that.

**Gotcha we hit, three times (once per service):**

```yaml
volumes:
  - ./src/services/retriever:/app/src/retriever   # wrong — missing "services/"
```

The Dockerfile actually `COPY`s to `/app/src/services/retriever`, and `uvicorn` imports `src.services.retriever.retriever:retriever_api` from that exact path. With the wrong destination, editing code on the host updates a directory nothing imports from — the container keeps serving the original image-baked copy. No error, just silently-ignored edits. Always double check the mount destination against the Dockerfile's own `COPY` destinations, not just the module's dotted import path.

## 3. Bind mounts are live and bidirectional

- Editing a file on the host is visible inside the container immediately, and vice versa — a write from either side is a write to the same underlying file. This holds whether the container is running, stopped, or freshly (re)started; nothing is cached or frozen in between.
- This is why stopping a container, editing code, then starting it again always picks up the change — a fresh process start just reads whatever currently exists at the mounted path.
- Caveat for edits *while the container keeps running*: the file on disk updates instantly, but a long-running process (like `uvicorn`) won't notice unless it's watching for changes — hence pairing bind mounts with `--reload` for live dev.
- Side effect of mounting whole directories: anything the container writes into that path (e.g. Python's `__pycache__/*.pyc`) shows up on the host too. Not a bug, just something Python creates that isn't yours.

## 4. Named volumes vs bind mounts

| | Bind mount | Named volume |
|---|---|---|
| You choose the host path | Yes (`./src/...`) | No — Docker manages it |
| Browsable in Explorer/editor | Yes | No — lives inside Docker Desktop's internal WSL2 VM disk, not a normal Windows folder |
| Use for | Source code you want to hot-edit | State the *app* owns (DB data files, caches) that you don't need to hand-edit |

**Won't be switching everything to named volumes** — they solve different problems. Source code stays a bind mount (you need to open it in an editor); `pgdata` stays a named volume (Postgres's own data files, portable, survives container recreation, and you're not meant to poke at it directly).

To actually inspect a named volume's contents: `docker volume inspect <project>_pgdata` (gives you the internal mountpoint, not directly Explorer-navigable) or, more practically, `docker compose exec postgres sh -c "ls /var/lib/postgresql"` — look from inside a container that has it mounted rather than trying to reach it from Windows directly.

## 5. Dev-mode conveniences belong in Compose, not the Dockerfile

- `image:` (alongside `build:`) — names/tags the built image explicitly (`intent-classifier:1.0.0`) instead of Compose's auto-generated `<project>-<service>:latest`. Can reference an env var with a fallback: `image: intent-classifier:${TAG:-latest}`.
- `command:` — **replaces** the image's `CMD` entirely (doesn't append to it), while `ENTRYPOINT` stays fixed. Used this to inject `--port` + `--reload` for local dev:
  ```yaml
  command: ["--port", "8000", "--reload"]
  ```
  Reasoning: `--reload` is dev-only (Uvicorn itself advises against it in production). Baking it into the Dockerfile's `CMD` would make every image from that Dockerfile permanently dev-mode, in every environment. Keeping it in `docker-compose.yml` means the image itself stays generic and deployable anywhere; only the *local dev* invocation adds the override. The bind mounts and `--reload` are really one dev-mode package — worth keeping both together in the same file for that reason.

## 6. Env vars: two different substitution mechanisms with the same `.env` file

- **`env_file: [.env]`** on a service — injects those variables *into that container* at start time.
- **`${VAR}` inside the compose file itself** (e.g. `POSTGRES_DB=${DATABASE_NAME:-nhtsa}`) — Compose automatically loads a file literally named `.env` in the project root for substitutions *in the compose file's own text*, completely separate from the `env_file:` mechanism above. Same file, two different jobs.
- **`environment:` overrides `env_file:`** for the same key. Used this to keep `.env` as the "local truth" (`POSTGRES_HOST=localhost`, correct for running scripts directly on Windows) while overriding just the containerized run:
  ```yaml
  environment:
    - POSTGRES_HOST=postgres   # or host.docker.internal, before postgres was containerized
  ```
  No duplicate `.env` files needed for the two contexts.

## 7. `depends_on` alone doesn't wait for readiness

Plain `depends_on: [postgres]` only waits for the container process to *exist*, not for Postgres to actually be ready to accept connections — Postgres takes a moment to initialize on first run. Pair it with a `healthcheck:` and `condition: service_healthy`:

```yaml
postgres:
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
    interval: 5s
    timeout: 5s
    retries: 5

retriever:
  depends_on:
    postgres:
      condition: service_healthy
```

Note the `$$` — a single `$` would get swallowed by Compose's own variable substitution before it ever reaches the container's shell; `$$` escapes it so the literal `$POSTGRES_USER` reaches `pg_isready` inside the container.

## 8. `profiles:` for one-shot jobs that shouldn't auto-start

`ingestion` runs once and exits (fetch NHTSA data, embed, load) — it shouldn't join every `docker compose up` alongside the three persistent services. Tagging it:

```yaml
ingestion:
  profiles: ["jobs"]
```

excludes it from a plain `docker compose up`. Run it explicitly when needed:

```bash
docker compose --profile jobs run --rm ingestion
```

This is also the long-term-correct shape per the project plan (`structure.md` calls ingestion "the batch/cron job, NOT a live service") — actual scheduling (weekly runs) is deferred to Kubernetes' `CronJob` resource once Phase 2 arrives, rather than building a throwaway scheduler at the Compose stage.

## 9. Postgres-specific gotchas

- **Port conflict with a native install.** A native Postgres already listening on `5432` on the host means the containerized one needs a different host-side port: `127.0.0.1:5433:5432`. Also incidentally useful: this lets existing non-containerized scripts (`ingestion.py` before it had its own Dockerfile) reach the container via `POSTGRES_HOST=localhost POSTGRES_PORT=5433`.
- **Postgres 18+ changed its data directory convention.** Mounting the volume the old way —
  ```yaml
  volumes:
    - pgdata:/var/lib/postgresql/data
  ```
  — makes the container refuse to start on first run with `pgvector/pgvector:pg18`:
  ```
  Error: in 18+, these Docker images are configured to store database data in a
         format which is compatible with "pg_ctlcluster"...
         there appears to be PostgreSQL data in:
           /var/lib/postgresql/data (unused mount/volume)
  ```
  18+ images expect a single mount at **`/var/lib/postgresql`** (no `/data` suffix) and manage their own version-specific subdirectory underneath. Fix, plus clearing out whatever got written to the volume under the old (wrong) path before re-initializing:
  ```yaml
  volumes:
    - pgdata:/var/lib/postgresql
  ```
  ```bash
  docker compose down -v   # drops the named volume so it reinitializes cleanly
  ```
- **Migrating existing data from a native install into the container**, when you have real data you don't want to just re-ingest: pipe `pg_dump`/`psql` directly between the two, no intermediate file needed for a small dataset:
  ```powershell
  $env:PGPASSWORD = "<password>"
  & "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" -h localhost -p 5432 -U <user> -d nhtsa `
    | & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -p 5433 -U <user> -d nhtsa
  ```
  Works without extra setup because `pg_dump` includes `CREATE EXTENSION IF NOT EXISTS vector` automatically (since the source DB has it enabled), and the `pgvector/pgvector` image already ships that extension's shared library.
- For a project at this stage, re-running the existing ingestion pipeline against a fresh container is usually simpler than migrating — only reach for the `pg_dump`/`psql` route when the existing data is expensive or impossible to regenerate.

## 10. Non-root user + fresh mount points

Same root issue as `COPY --chown` in the Dockerfiles, showing up again for volumes: Docker auto-creates a mount point that doesn't yet exist in the image, but does so as **root**, regardless of what `USER` the container will run as. A non-root `appuser` trying to write into a freshly-mounted path (e.g. `/app/data` for saving fetched NHTSA JSON) hits a `PermissionError` unless the directory is pre-created and chowned *in the image* before the `USER` switch:

```dockerfile
RUN mkdir -p /app/data && chown appuser:appusergroup /app/data
USER appuser
```

Docker preserves a pre-existing directory's ownership when it initializes an empty volume/bind mount at that path — this only works if the `chown` happens before the mount is applied, i.e. at image build time.

## Useful commands

```bash
# bring up everything except one-shot job services
docker compose up -d

# bring up just one service
docker compose up -d postgres

# run a profiled one-shot job
docker compose --profile jobs run --rm ingestion

# tail logs for one service
docker compose logs -f retriever

# check why a container exited
docker logs <container-name>

# drop everything including named volumes (destructive — clears pgdata too)
docker compose down -v

# peek inside a named volume via a container that has it mounted
docker compose exec postgres sh -c "ls /var/lib/postgresql"
```
