# =============================================================================
# Grafana Alloy - Production Dockerfile
# =============================================================================
# Security-hardened Dockerfile for Grafana Alloy with dynamic processors
# Features:
# - Official Grafana Alloy base image
# - Non-root user execution
# - Pinned versions for reproducibility
# - Custom configuration inclusion
# - Health and metrics endpoints
# =============================================================================

# Use official Grafana Alloy image with pinned version
# Check for latest stable version at: https://github.com/grafana/alloy/releases
ARG ALLOY_VERSION=v1.0.0
FROM grafana/alloy:${ALLOY_VERSION}

# Set labels for metadata
LABEL org.opencontainers.image.title="Grafana Alloy Dynamic Processors" \
      org.opencontainers.image.description="Grafana Alloy with dynamic processing capabilities" \
      org.opencontainers.image.vendor="Alloy Dynamic Processors" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/ChaosKyle/alloy-dynamic-processors"

# Create configuration directory
USER root
RUN mkdir -p /etc/alloy /var/lib/alloy && \
    chown -R alloy:alloy /etc/alloy /var/lib/alloy

# Copy Alloy configurations
COPY --chown=alloy:alloy alloy/configs/*.alloy /etc/alloy/
COPY --chown=alloy:alloy alloy/configs/*.river /etc/alloy/

# Switch back to non-root alloy user
USER alloy:alloy

# Set working directory
WORKDIR /etc/alloy

# Expose ports
# HTTP API and UI
EXPOSE 12345
# gRPC API
EXPOSE 12346
# Health check endpoint
EXPOSE 13133
# Prometheus metrics
EXPOSE 8889
# OTLP gRPC receiver
EXPOSE 4317
# OTLP HTTP receiver
EXPOSE 4318

# Health check
HEALTHCHECK --interval=30s \
            --timeout=10s \
            --start-period=15s \
            --retries=3 \
    CMD curl -f http://localhost:13133/healthz || exit 1

# Default configuration file
ENV ALLOY_CONFIG=/etc/alloy/main.alloy

# Run Alloy with configuration
# Note: Override ALLOY_CONFIG via environment variable or command args
# Example: docker run -e ALLOY_CONFIG=/etc/alloy/enhanced-with-sort.alloy ...
ENTRYPOINT ["/bin/alloy"]
CMD ["run", "${ALLOY_CONFIG}", \
     "--server.http.listen-addr=0.0.0.0:12345", \
     "--storage.path=/var/lib/alloy"]

# Security notes:
# - Runs as non-root 'alloy' user (from base image)
# - Use with read-only root filesystem
# - Mount /var/lib/alloy as volume for persistence
# - No additional capabilities required
# - Based on official Grafana image
