# Auto Safety Assist

[![CI](https://github.com/shashankag14/auto-safety-assist/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/shashankag14/auto-safety-assist/actions/workflows/ci.yml)
[![Eval gate](https://github.com/shashankag14/auto-safety-assist/actions/workflows/eval.yml/badge.svg)](https://github.com/shashankag14/auto-safety-assist/actions/workflows/eval.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-ECS%20Fargate%20%7C%20ALB%20%7C%20RDS%20%7C%20ECR%20%7C%20S3-FF9900?logo=amazonwebservices&logoColor=white)
![pgvector](https://img.shields.io/badge/Postgres-pgvector-4169E1?logo=postgresql&logoColor=white)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)


Ask a plain-English question about your car's safety and get an answer backed by official records, with the recall or complaint number it came from.

The answers come from [NHTSA](https://www.nhtsa.gov/) (the US National Highway Traffic Safety Administration), which publishes two kinds of public records:

- **Recalls**: defects a manufacturer has officially acknowledged and will fix for free
- **Complaints**: problems reported by owners, which may or may not lead to a recall

### What you can ask

| You ask | What it does | Example answer (shortened) |
|---|---|---|
| *"Is there a recall on my 2018 BMW X5 for the charging cable catching fire?"* | Looks up **recalls** | Yes, for the plug-in hybrid X5 xDrive40e. **Recall 18V652000**: capacitors in the portable charger may fail, creating a shock or fire hazard. Dealers will replace it free of charge. |
| *"My Camry's wipers turn on by themselves. Has anyone else reported this?"* | Searches owner **complaints** | Yes. **Complaint 11744296** reports a Toyota Camry whose wipers turn on by themselves; the dealer couldn't find a problem. |
| *"How do car recalls work in general?"* | Answers from general knowledge, with no retrieval | A general explanation, with no recall or complaint numbers, since none were looked up |

Every record-based answer cites its source, so you can check it on nhtsa.gov instead of trusting the model. If no matching record is found, it falls back to a general answer and never makes up a record number.

**Coverage:** It's a project in progress, so it currently covers three vehicles: the 2018 BMW X5, the 2022 Toyota Camry and the 2022 Honda CR-V ([`TARGET_VEHICLES`](src/common/config.py)).

Under the hood, it's a retrieval-augmented generation (RAG) pipeline: it classifies the question, finds the most relevant records with vector search, then has an LLM write an answer using only those records.

## Architecture

Microservices, each independently deployable:

- **ingestion** — batch job that pulls NHTSA recall/complaint data ([nhtsa.gov](https://www.nhtsa.gov/), see [NHTSA datasets and APIs](https://www.nhtsa.gov/nhtsa-datasets-and-apis)), chunks it, embeds it, and loads it into Postgres.
- **intent-classifier** — FastAPI service that classifies whether a query needs the RAG pipeline or is a general question.
- **retriever** — FastAPI service that performs vector similarity search over embedded NHTSA data (pgvector).
- **response-generator** — FastAPI service that builds context from retrieved records and generates a cited LLM response (`/generate`), or answers from general knowledge when there are no records (`/answer`).

On AWS, each service runs as its own ECS service on Fargate behind one Application Load Balancer, which routes requests by path (`/classify`, `/retrieve`, `/generate`, …). Ingestion runs as a one-off ECS task. See [infra/README.md](infra/README.md) for the diagrams.


## Tech Stack

| Layer | Tools | Used for |
|---|---|---|
| **AI / RAG** | OpenAI API (`gpt-4o-mini` by default) | Classifying the question and writing the cited answer |
| | `sentence-transformers` (`all-MiniLM-L6-v2`, CPU) | Turning recall and complaint text into vectors |
| **Data** | PostgreSQL + `pgvector` | Storing the vectors and finding the closest matches |
| | pandas, psycopg2 | Cleaning NHTSA data and talking to Postgres |
| **Services** | Python 3.11+, FastAPI + Uvicorn | The three HTTP services |
| | loguru | Logging |
| **Quality** | pytest, ruff | Tests and linting |
| | RAGAS | Scoring answer quality with an LLM judge (see [evals/](evals/README.md)) |
| **Packaging** | `uv` + `pyproject.toml` | Dependencies and virtual environments |
| | Docker + Docker Compose | One image per service; `docker compose up` runs the whole stack locally |
| **CI/CD** | GitHub Actions | Lint, test and build images on every change; quality gate on PRs to `main` (see [docs/ci-workflows.md](docs/ci-workflows.md)) |
| **AWS** | ECS on Fargate (Spot) | Runs the three services and the one-off ingestion job |
| | Application Load Balancer (ALB) | One public entry point; routes each path to the right service and only sends traffic to tasks passing `/healthz` |
| | RDS for PostgreSQL + `pgvector` | Managed cloud database holding the embedded data. Private, reachable only from the ECS tasks |
| | VPC + security groups | Chained rules: your IP → ALB → services → database. Public subnets with no NAT gateway (to keep costs down) |
| | Secrets Manager | RDS password and the Cloud LLM key, injected into the containers at startup |
| | ECR (+ GHCR for now) | Container images tagged by git SHA (immutable), pushed from `main` |
| | S3 | Pinned eval data snapshot for the CI quality gate |
| | IAM + GitHub OIDC | CI logs in to AWS with short-lived credentials|
| | CloudWatch Logs | Container logs from every service (retention 7 days) |
|

## Running on AWS

```powershell
aws login --profile auto-safety
.\infra\aws\scripts\session-start.ps1    # start RDS, (re)create the ALB, scale services up; prints the app URL
.\infra\aws\scripts\session-stop.ps1     # scale services to 0, stop RDS
.\infra\aws\scripts\alb-down.ps1         # also delete the ALB, for longer breaks
```

Note: The ALB only accepts requests from the developer's IP, because the endpoints call the (paid) OpenAI API. See [infra/README.md](infra/README.md) for the AWS infra in detail.

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

## Docs

| Doc | What's in it |
|---|---|
| [Cloud infrastructure (AWS)](infra/README.md) | Architecture diagrams, costs, session scripts and where each infrastructure file lives |
| [CI workflows](docs/ci-workflows.md) | The two GitHub Actions workflows, what each runs and when |
| [Evals and the CI quality gate](docs/evals-and-quality-gate.md) | How answer quality is checked on PRs, and what to do when the data changes |
| [Evals](evals/README.md) | The golden dataset, and the metrics for each service's eval and how to read their reports |
