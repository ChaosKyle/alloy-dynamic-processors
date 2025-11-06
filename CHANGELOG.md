# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial production-ready release with comprehensive features
- Apache 2.0 LICENSE
- Complete repository governance (CODEOWNERS, .editorconfig, issue templates)
- Comprehensive .env.example with 100+ documented variables
- Detailed architecture documentation with Mermaid diagrams

### Changed
- N/A (initial release)

### Deprecated
- N/A (initial release)

### Removed
- N/A (initial release)

### Fixed
- N/A (initial release)

### Security
- All containers run as non-root users
- Read-only filesystem support
- Network policies for zero-trust architecture
- No hardcoded secrets
- Image signing with cosign
- SBOM generation with syft

## [1.0.0] - TBD

### Added

#### Repository & Governance
- Apache 2.0 LICENSE for open source distribution
- CODEOWNERS file for automated PR review assignments
- .editorconfig for consistent coding styles across editors
- Comprehensive pull request template with security checklist
- Four issue templates: bug report, feature request, security vulnerability, documentation
- .env.example with complete environment variable documentation
- docs/overview.md with detailed Mermaid architecture diagrams

#### CI/CD & Automation
- Enhanced pre-commit hooks (shellcheck, shfmt, ruff, bandit)
- GitHub Actions CI workflow with matrix builds (Python 3.11/3.12)
- Shell script linting and formatting
- Code coverage reporting with codecov
- Docker Compose smoke tests
- Comprehensive release workflow with:
  - Multi-arch image builds (amd64, arm64)
  - Keyless image signing with cosign (OIDC)
  - SBOM generation with syft
  - Vulnerability scanning with Trivy
  - Automated GitHub release creation
  - Helm chart version auto-updates

#### Container & Runtime
- Production-hardened Dockerfiles for AI Sorter and Alloy
- Multi-stage builds for minimal final images
- Non-root user execution (UID 10001 for AI Sorter)
- Read-only filesystem support
- Pinned base image versions
- Comprehensive health checks
- Security labels and OCI annotations
- Full docker-compose.yaml stack with Prometheus, Loki, Tempo, Grafana
- .dockerignore for efficient builds
- Comprehensive Makefile with 60+ targets

#### Kubernetes & Helm
- Production-ready Helm chart with:
  - HorizontalPodAutoscaler (CPU/memory/custom metrics)
  - PodDisruptionBudget for high availability
  - NetworkPolicies for zero-trust security
  - ServiceAccount and RBAC
  - ServiceMonitor for Prometheus
  - Comprehensive NOTES.txt with access instructions
  - ConfigMap and Secret management
  - PVC for persistence

#### AI Sorter Service
- Complete rewrite with production-grade features:
  - Pydantic v2 models with comprehensive validation
  - Circuit breaker pattern (CLOSED/OPEN/HALF_OPEN states)
  - Exponential backoff retry logic with tenacity
  - Token bucket rate limiting
  - Semaphore-based concurrency controls
  - PII redaction in logs and prompts
  - Structured logging with structlog (JSON output)
  - Prometheus metrics (7 metrics: counters, histograms, gauges)
  - Health endpoints (/healthz, /readyz, /metrics)
  - Graceful shutdown with signal handlers
  - OpenAPI documentation (/docs, /redoc)
  - Type hints throughout (775 lines)

#### Observability & Monitoring
- Two production-ready Grafana dashboards:
  - Alloy pipeline health (6 panels)
  - AI Sorter performance (8 panels)
- 20+ Prometheus alert rules across 4 groups:
  - Alloy pipeline alerts
  - AI Sorter alerts
  - Resource utilization
  - Data quality
- Grafana provisioning for datasources and dashboards
- Prometheus scrape configuration
- End-to-end test script (280+ lines) with:
  - Health checks
  - Metrics verification
  - Synthetic telemetry generation
  - AI Sorter testing
  - Data flow verification

#### Documentation
- Comprehensive README with quick start guides
- Architecture overview with detailed diagrams
- Production readiness checklist
- Troubleshooting guide
- Release process documentation
- ADR-style decision records
- Migration guide from OTel Collector
- Scaling guidance
- Cost optimization recommendations

### Technical Details

#### Dependencies
- FastAPI 0.115.0
- Pydantic 2.9.2
- httpx 0.27.2
- tenacity 9.0.0
- pyrate-limiter 3.7.0
- structlog 24.4.0
- prometheus-client 0.20.0

#### Metrics Exposed
- `ai_sorter_requests_total` - Total requests by status
- `ai_sorter_items_classified_total` - Items by category
- `ai_sorter_api_calls_total` - AI API calls by status
- `ai_sorter_circuit_breaker_opens_total` - Circuit breaker opens
- `ai_sorter_request_duration_seconds` - Request latency histogram
- `ai_sorter_api_call_duration_seconds` - AI API latency histogram
- `ai_sorter_active_requests` - Active request gauge
- `ai_sorter_circuit_breaker_state` - Circuit breaker state gauge

#### Security Features
- Non-root container execution
- Read-only root filesystem support
- Network policies with egress controls
- PII redaction (email, SSN, credit cards, phone, IP, API keys)
- Secret management via Kubernetes Secrets
- Image signing with cosign keyless OIDC
- SBOM generation in SPDX format
- Vulnerability scanning with Trivy
- No hardcoded credentials

#### Performance
- Circuit breaker prevents cascading failures
- Rate limiting: 60 requests/minute (configurable)
- Concurrency limit: 10 concurrent requests (configurable)
- Retry with exponential backoff (3 attempts max)
- Batch processing optimizations
- Memory limiting to prevent OOM

### Breaking Changes
- N/A (initial release)

### Migration Notes
- See [Migration Guide](docs/MIGRATION.md) for moving from OTel Collector to Alloy

### Known Issues
- AI Sorter requires valid API key for classification (falls back gracefully)
- Helm chart requires Kubernetes 1.21+
- NetworkPolicies require CNI plugin support

### Contributors
- @ChaosKyle - Initial implementation and production hardening

---

## Release Process

1. Update CHANGELOG.md with release notes
2. Update version in:
   - `alloy/helm/alloy-dynamic-processors/Chart.yaml`
   - AI Sorter version string
3. Create git tag: `git tag -a v1.0.0 -m "Release v1.0.0"`
4. Push tag: `git push origin v1.0.0`
5. GitHub Actions will automatically:
   - Build multi-arch images
   - Sign with cosign
   - Generate SBOM
   - Scan for vulnerabilities
   - Create GitHub release
   - Publish to GHCR

---

[Unreleased]: https://github.com/ChaosKyle/alloy-dynamic-processors/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/ChaosKyle/alloy-dynamic-processors/releases/tag/v1.0.0
