# Auto Safety Assist

Ask your car what's wrong. It answers with citations using NHTSA recalls and complaints, no guessing.

A Retrieval-Augmented Generation (RAG) system that classifies a user's question about their vehicle, retrieves relevant NHTSA recall/complaint records via vector search, and generates a grounded, cited response.

## Architecture

Microservices, each independently deployable:

- **ingestion** — batch job that pulls NHTSA recall/complaint data ([nhtsa.gov](https://www.nhtsa.gov/), see [NHTSA datasets and APIs](https://www.nhtsa.gov/nhtsa-datasets-and-apis)), chunks it, embeds it, and loads it into Postgres.
- **intent-classifier** — FastAPI service that classifies whether a query needs the RAG pipeline or is a general question.
- **retriever** — FastAPI service that performs vector similarity search over embedded NHTSA data (pgvector).
- **response-generator** — FastAPI service that builds context from retrieved records and generates a cited LLM response.
- **pipeline** — thin orchestrator that calls the services in sequence: ingest → classify intent → retrieve → generate.

## Tech Stack

- **Language:** Python 3.11+
- **API framework:** FastAPI + Uvicorn
- **Database:** PostgreSQL with `pgvector` for vector search
- **Embeddings:** `sentence-transformers`, PyTorch (CPU)
- **LLM:** OpenAI API (intent classification, response generation)
- **DB access:** psycopg2
- **Data processing:** pandas
- **Packaging/deps:** `uv` / `pyproject.toml`
- **Logging:** loguru
- **Containerization:** Docker + Docker Compose (per-service Dockerfiles, orchestrated via `docker-compose.yml`)
- **Container registry:** GitHub Container Registry (GHCR) for eco-system simplicity
- **Testing:** pytest
- **Linting:** ruff
- **CI/CD:** GitHub Actions (lint, test, build & push each service's image to GHCR)

## Running Locally

Requires Docker + Docker Compose, and a `.env` file at the repo root with your Postgres and OpenAI credentials (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `DATABASE_NAME`, `OPENAI_API_KEY`, etc. — see `src/common/config.py` for the full list of env vars each service reads).

### 1. Ingest data

Pulls recall/complaint data from NHTSA, embeds it, and loads it into Postgres. The `ingestion` service is compose-profiled so it doesn't run on every `up` — invoke it explicitly as a one-off job:

```bash
docker compose --profile jobs run --rm ingestion
```

This starts Postgres (if not already running) and runs the ingestion + indexing pipeline once, then exits.

### 2. Run the services

```bash
docker compose up
```

Starts Postgres and the three FastAPI services:

| Service | Port | Docs |
|---|---|---|
| intent-classifier | 8000 | http://localhost:8000/docs |
| retriever | 8001 | http://localhost:8001/docs |
| response-generator | 8002 | http://localhost:8002/docs |

Each service exposes a `/healthz` endpoint you can hit to confirm it's up, and interactive Swagger docs at `/docs`.
