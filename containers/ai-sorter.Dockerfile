# =============================================================================
# AI Sorter FastAPI Sidecar - Production Dockerfile
# =============================================================================
# Multi-stage, security-hardened Dockerfile for the AI sorting sidecar
# Features:
# - Multi-stage build for minimal final image
# - Non-root user execution
# - Read-only root filesystem
# - Pinned base image versions
# - Comprehensive health checks
# - Minimal attack surface
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder
# -----------------------------------------------------------------------------
FROM python:3.11.9-slim-bookworm AS builder

# Set build-time environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install dependencies
COPY alloy/processors/ai_sorter/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# -----------------------------------------------------------------------------
# Stage 2: Runtime
# -----------------------------------------------------------------------------
FROM python:3.11.9-slim-bookworm AS runtime

# Set runtime labels for metadata
LABEL org.opencontainers.image.title="Alloy AI Sorter" \
      org.opencontainers.image.description="AI-powered telemetry classification sidecar" \
      org.opencontainers.image.vendor="Alloy Dynamic Processors" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/ChaosKyle/alloy-dynamic-processors"

# Install runtime dependencies only
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        tini \
        && rm -rf /var/lib/apt/lists/* \
        && apt-get clean

# Create non-root user and group
RUN groupadd -r -g 10001 appuser && \
    useradd -r -u 10001 -g appuser -m -d /app -s /sbin/nologin \
        -c "AI Sorter Application User" appuser

# Copy virtual environment from builder
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# Set up application directory
WORKDIR /app

# Create necessary directories with correct permissions
RUN mkdir -p /app/logs /app/tmp /tmp/ai-sorter && \
    chown -R appuser:appuser /app /tmp/ai-sorter

# Copy application code
COPY --chown=appuser:appuser alloy/processors/ai_sorter/ai_sorter.py /app/

# Set runtime environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app" \
    # Application settings
    AI_SORTER_HOST=0.0.0.0 \
    AI_SORTER_PORT=8080 \
    AI_SORTER_WORKERS=2 \
    AI_SORTER_LOG_LEVEL=info \
    # Security settings
    TMPDIR=/tmp/ai-sorter

# Switch to non-root user
USER appuser:appuser

# Expose application port
EXPOSE 8080

# Health check configuration
HEALTHCHECK --interval=30s \
            --timeout=10s \
            --start-period=10s \
            --retries=3 \
    CMD curl -f http://localhost:8080/healthz || exit 1

# Readiness check endpoint is /readyz
# Metrics endpoint is /metrics

# Use tini as init system for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

# Run application with production settings
CMD ["uvicorn", "ai_sorter:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--workers", "2", \
     "--log-level", "info", \
     "--access-log", \
     "--no-server-header"]

# Security notes:
# - Runs as non-root user (UID 10001)
# - Use with read-only root filesystem (add --read-only flag)
# - Mount /tmp/ai-sorter as tmpfs in production
# - No capabilities required
# - Minimal base image (slim-bookworm)
