# Stage 1: Builder - Installs project and dependencies using pip
FROM python:3.13-alpine AS builder

WORKDIR /app

# Install build dependencies (needed if any package requires compilation)
RUN apk add --no-cache build-base

# Copy build configuration, metadata, AND application code needed for build
COPY pyproject.toml README.md /app/
COPY ./grimwaves_api /app/grimwaves_api

# poetry.lock might not be strictly used by pip install ., but pyproject.toml is key

# Install the project and its main dependencies using pip
# Pip reads pyproject.toml and uses the specified build backend (poetry-core)
# Now it can find the 'grimwaves-api' package code
# We install into a target directory to easily copy it later
RUN pip install --no-cache-dir --prefix=/install .

# Stage 2: Final image
FROM python:3.13-alpine

WORKDIR /app

# Update OS packages, specifically sqlite-libs, to fix known vulnerabilities
# Needs to be in the final stage as this is where the OS packages are used
RUN apk update && apk upgrade sqlite-libs && rm -rf /var/cache/apk/*

# Copy installed dependencies from builder stage
COPY --from=builder /install /usr/local

# Copy application code, data, and README (from the host)
COPY ./grimwaves_api ./grimwaves_api
COPY ./data ./data
COPY pyproject.toml ./
COPY README.md ./

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV API_PORT=8000
ENV API_WORKERS=1

# Expose the port the app runs on
EXPOSE ${API_PORT}

# Run the application using environment variables for port and workers
CMD ["sh", "-c", "uvicorn grimwaves_api:app --host 0.0.0.0 --port ${API_PORT} --workers ${API_WORKERS}"] 