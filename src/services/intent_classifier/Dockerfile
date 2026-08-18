# ---- Stage 1: Builder ----
FROM python:3.13-slim AS builder

# copy uv binaries from a uv image to /bin
# More info: https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
COPY --from=docker.io/astral/uv:latest /uv /uvx /usr/local/bin/

# Set the working directory
WORKDIR /app

# copy the dependency files
COPY pyproject.toml uv.lock ./

# create the venv using uv sync to ONLY isntall dependencies. 
# We dont install the project here yet
RUN uv sync --frozen --no-dev --no-install-project --group intent-classifier

# copy the required source code to run the service
COPY /src/services/intent_classifier /app/src/services/intent_classifier
COPY /src/common/config.py /app/src/common/config.py

# again perform uv sync to install project
# performing a uv sync before avoids additionaly package installation everytime the soruce code is changed (layer caching)
RUN uv sync --frozen --no-dev --group intent-classifier

# ---- Stage 2: Runtime ----
FROM python:3.13-slim AS runtime

WORKDIR /app

# Create a non-root user
RUN groupadd -r appusergroup && useradd -r -g appusergroup appuser

# copy the source files from builder stage
# give the permission to appuser to write files in the dirs below
COPY --from=builder --chown=appuser:appusergroup /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appusergroup /app/src /app/src

# Place executables in the environment at the front of the path
# NOTE: in debian/alpine, uv creates the executable inside .venv/bin (unlike in windows --> .venv/Scripts)
ENV PATH="/app/.venv/bin:$PATH"

# expose the port to be used for documentation
EXPOSE 8000

# set the appuser now
USER appuser

ENTRYPOINT ["uvicorn", "src.services.intent_classifier.classifier:classifier_api", "--host", "0.0.0.0"]
CMD ["--port", "8000"]
