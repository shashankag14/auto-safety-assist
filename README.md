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
- **Testing:** pytest
- **Linting:** ruff
- **CI:** GitHub Actions
