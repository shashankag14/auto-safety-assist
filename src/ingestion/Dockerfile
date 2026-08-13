# ---- Stage 1: Builder ----
FROM python:3.13-slim AS builder

# copy uv binaries from a uv image to /bin
# More info: https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
COPY --from=docker.io/astral/uv:latest /uv /uvx /usr/local/bin/

# Set the working directory
WORKDIR /app

# copy the dependency files
COPY pyproject.toml uv.lock ./

# required for psycopg2 package
RUN apt-get update && apt-get -y install libpq-dev gcc

# create the venv using uv sync to ONLY install dependencies. 
# We dont install the project here yet
RUN uv sync --frozen --no-dev --no-install-project --group retriever --group ingestion

# performing a uv sync before avoids additionaly package installation everytime the soruce code is changed (layer caching)
COPY /src/ingestion /app/src/ingestion
COPY /src/common /app/src/common

# again perform uv sync to install project
# performing a uv sync before avoids additionaly package installation everytime the soruce code is changed (layer caching)
RUN uv sync --frozen --no-dev --group retriever --group ingestion

# download the hugging face model and store in cache
ENV HF_HOME=/app/.cache/huggingface

# download the model and save it in cache directory in the container
RUN uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2', device='cpu');"

# ---- Stage 2: Runtime ----
FROM python:3.13-slim AS runtime

WORKDIR /app

# Install smaller version - libpq5, enough for psychopg2 to run and delete unnecessary files installed
RUN apt-get update && apt-get -y install --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN groupadd -r appusergroup && useradd -r -g appusergroup appuser

# copy the source files from builder stage
# give the permission to appuser to write files in the dirs below
COPY --from=builder --chown=appuser:appusergroup /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appusergroup /app/src /app/src
COPY --from=builder --chown=appuser:appusergroup /app/.cache /app/.cache

# to store the ingested data from nhtsa web API
RUN mkdir -p /app/data && chown appuser:appusergroup /app/data

ENV HF_HOME=/app/.cache/huggingface

# forces a failure by going offline rather than silently downloading the model over internet in case cache hit misses
ENV HF_HUB_OFFLINE=1

# Place executables in the environment at the front of the path
# NOTE: in debian/alpine, uv creates the executable inside .venv/bin (unlike in windows --> .venv/Scripts)
ENV PATH="/app/.venv/bin:$PATH"

# set the appuser now
USER appuser

# run the scripts
ENTRYPOINT ["sh", "-c", "python -m src.ingestion.ingestion && python -m src.ingestion.build_index"]

