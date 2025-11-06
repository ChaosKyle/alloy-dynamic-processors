# Alloy Dynamic Processors

[![CI](https://github.com/ChaosKyle/alloy-dynamic-processors/actions/workflows/ci.yml/badge.svg)](https://github.com/ChaosKyle/alloy-dynamic-processors/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Kubernetes](https://img.shields.io/badge/kubernetes-%23326ce5.svg?style=flat&logo=kubernetes&logoColor=white)](https://kubernetes.io/)

Production-ready **Grafana Alloy** telemetry processing with advanced resource detection, intelligent labeling strategies, optional AI-powered classification, and seamless Grafana Cloud integration.

## 🎯 Features

### Core Capabilities
- **Grafana Alloy Pipeline**: Vendor-agnostic OpenTelemetry distribution with River configuration language
- **Multi-Protocol Support**: OTLP (gRPC/HTTP), Prometheus, Loki ingestion
- **Dynamic Processing**: Intelligent routing, filtering, and transformation of telemetry data
- **AI-Powered Classification** *(Optional)*: Automatic severity detection and intelligent categorization via Grok API
- **Grafana Cloud Native**: Optimized for Grafana Cloud (Tempo, Loki, Prometheus, Mimir)

### Production-Ready
- ✅ **Multi-arch Docker Images** (amd64, arm64) with signed containers (cosign)
- ✅ **Kubernetes Helm Chart** with HPA, PDB, NetworkPolicy, RBAC
- ✅ **Circuit Breaker Pattern** for AI API resilience
- ✅ **Comprehensive Observability**: 2 Grafana dashboards, 20+ Prometheus alerts
- ✅ **Security Hardened**: Non-root containers, read-only filesystem, PII redaction
- ✅ **Zero-Trust Networking**: NetworkPolicies for ingress/egress control
- ✅ **SBOM & Vulnerability Scanning**: Automated supply chain security
- ✅ **End-to-End Tests**: Full integration test suite with synthetic telemetry

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [Overview](docs/overview.md) | Architecture diagrams, component details, data flows |
| [Migration Guide](docs/MIGRATION.md) | Moving from OpenTelemetry Collector to Alloy |
| [Release Process](docs/release.md) | Release checklist, versioning, hotfix procedures |
| [Architecture Decisions](docs/DECISIONS.md) | ADRs documenting key technical decisions |
| [CHANGELOG](CHANGELOG.md) | Detailed release notes and version history |
| [Contributing](CONTRIBUTING.md) | Development guidelines and PR process |
| [Security Policy](SECURITY.md) | Vulnerability reporting and security practices |

## 🚀 Quick Start

### Prerequisites

- **Docker** & **Docker Compose** (for local deployment)
- **Kubernetes 1.21+** with **Helm 3.8+** (for Kubernetes deployment)
- **Grafana Cloud account** (optional, for cloud integration)
- **xAI Grok API key** (optional, for AI classification)

### Local Development with Docker Compose

1. **Clone and configure**:
   ```bash
   git clone https://github.com/ChaosKyle/alloy-dynamic-processors.git
   cd alloy-dynamic-processors
   cp .env.example .env
   # Edit .env with your credentials (optional for local testing)
   ```

2. **Start the stack** (Alloy + Prometheus + Loki + Tempo + Grafana):
   ```bash
   make up
   # Or: docker compose up -d
   ```

3. **With AI Sorter enabled** (requires API key):
   ```bash
   make up-ai
   # Or: docker compose --profile ai up -d
   ```

4. **Verify health**:
   ```bash
   make health
   # Or manually:
   curl http://localhost:13133/healthz  # Alloy
   curl http://localhost:9090/-/healthy # Prometheus
   curl http://localhost:3100/ready     # Loki
   ```

5. **Access UIs**:
   - **Alloy UI**: http://localhost:12345
   - **Grafana**: http://localhost:3000 (admin/admin)
   - **Prometheus**: http://localhost:9090
   - **AI Sorter Docs** *(if enabled)*: http://localhost:8080/docs

6. **Run end-to-end tests**:
   ```bash
   make test-e2e
   ```

7. **Stop the stack**:
   ```bash
   make down
   ```

### Kubernetes Deployment with Helm

1. **Install to Kubernetes**:
   ```bash
   helm install alloy-processors ./alloy/helm/alloy-dynamic-processors \
     --namespace monitoring \
     --create-namespace \
     --set grafanaCloud.enabled=true \
     --set grafanaCloud.instanceId=YOUR_INSTANCE_ID \
     --set grafanaCloud.apiKey=YOUR_API_KEY
   ```

2. **With AI Sorter enabled**:
   ```bash
   helm install alloy-processors ./alloy/helm/alloy-dynamic-processors \
     --namespace monitoring \
     --create-namespace \
     --set aiSorter.enabled=true \
     --set aiSorter.apiKey=YOUR_GROK_API_KEY \
     --set grafanaCloud.enabled=true \
     --set grafanaCloud.instanceId=YOUR_INSTANCE_ID \
     --set grafanaCloud.apiKey=YOUR_API_KEY
   ```

3. **Verify deployment**:
   ```bash
   kubectl get pods -n monitoring
   kubectl logs -n monitoring -l app.kubernetes.io/name=alloy-dynamic-processors
   ```

4. **Access services** (via port-forward):
   ```bash
   # Alloy UI
   kubectl port-forward -n monitoring svc/alloy-processors 12345:12345

   # AI Sorter (if enabled)
   kubectl port-forward -n monitoring svc/alloy-processors-ai-sorter 8080:8080
   ```

5. **Upgrade release**:
   ```bash
   helm upgrade alloy-processors ./alloy/helm/alloy-dynamic-processors \
     --namespace monitoring
   ```

6. **Uninstall**:
   ```bash
   helm uninstall alloy-processors --namespace monitoring
   ```

## 📋 Production Readiness Checklist

Before deploying to production, verify:

### Security
- [ ] **Secrets Management**: All credentials stored in Kubernetes Secrets or external secret manager
- [ ] **No Hardcoded Credentials**: Verified `.env.example` used, no real secrets committed
- [ ] **Container Security**: Images scanned with Trivy, no critical/high vulnerabilities
- [ ] **Image Signing**: Verify cosign signatures on all images
- [ ] **RBAC**: ServiceAccount with least-privilege permissions configured
- [ ] **NetworkPolicy**: Zero-trust networking enabled (if CNI supports)
- [ ] **Non-Root Execution**: All containers run as non-root users
- [ ] **PII Redaction**: Sensitive data patterns configured for your use case

### Reliability
- [ ] **High Availability**: HPA configured with appropriate min/max replicas (≥2 for HA)
- [ ] **PodDisruptionBudget**: Set to prevent full outages during maintenance
- [ ] **Resource Limits**: CPU/memory requests and limits tuned per environment
- [ ] **Health Checks**: Liveness and readiness probes configured
- [ ] **Circuit Breaker**: AI Sorter circuit breaker thresholds tuned (if enabled)
- [ ] **Retry Logic**: Exponential backoff configured for external dependencies
- [ ] **Graceful Shutdown**: SIGTERM handling tested

### Observability
- [ ] **Metrics Scraping**: Prometheus ServiceMonitor configured and scraping
- [ ] **Dashboards**: Grafana dashboards imported and displaying data
- [ ] **Alerts**: Prometheus alert rules configured and routing to Alertmanager
- [ ] **Log Aggregation**: Logs flowing to Loki/centralized logging
- [ ] **Distributed Tracing**: Traces flowing to Tempo/backend
- [ ] **SLOs Defined**: Service level objectives established for key metrics

### Operations
- [ ] **Backups**: Persistent data (if any) backed up regularly
- [ ] **Disaster Recovery**: Recovery procedures documented and tested
- [ ] **Runbooks**: Operational procedures documented for common issues
- [ ] **On-Call**: Team trained on troubleshooting and escalation
- [ ] **Cost Monitoring**: Cloud costs tracked and alerts configured
- [ ] **Release Process**: Automated CI/CD pipeline tested end-to-end

### Performance
- [ ] **Load Testing**: System tested at expected peak load (2-5x normal)
- [ ] **Latency Benchmarks**: p95/p99 latencies within acceptable thresholds
- [ ] **Batch Sizing**: Alloy batch processor tuned for throughput vs latency
- [ ] **Rate Limiting**: AI Sorter rate limits configured appropriately
- [ ] **Memory Limits**: Memory settings prevent OOM while allowing headroom
- [ ] **Auto-Scaling**: HPA tested and scaling appropriately under load

### Compliance
- [ ] **Data Retention**: Policies configured per compliance requirements
- [ ] **Audit Logging**: Access and changes logged for audit trail
- [ ] **Data Residency**: Telemetry stored in compliant regions
- [ ] **Encryption**: TLS enabled for all external communication
- [ ] **Access Controls**: RBAC and NetworkPolicy enforce least privilege

## 📊 Architecture

```
┌─────────────────┐
│  Applications   │ (Instrumented with OTel SDKs)
└────────┬────────┘
         │ OTLP (gRPC/HTTP)
         ▼
┌─────────────────────────────────────────────────┐
│           Grafana Alloy (Collector)             │
│  ┌──────────────┐  ┌─────────────────────────┐ │
│  │   Receivers  │→ │     Processors          │ │
│  │  OTLP, Prom  │  │  Batch, Attributes,     │ │
│  │              │  │  Resource, Transform    │ │
│  └──────────────┘  └────────┬────────────────┘ │
└───────────────────────────────┼──────────────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         ▼                      ▼                      ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  AI Sorter      │   │  Grafana Cloud  │   │  Local Stack    │
│  (Optional)     │   │  - Tempo        │   │  - Prometheus   │
│  - Grok API     │   │  - Loki         │   │  - Loki         │
│  - Classification│   │  - Prometheus   │   │  - Tempo        │
└─────────────────┘   └─────────────────┘   └─────────────────┘
```

See [docs/overview.md](docs/overview.md) for detailed architecture diagrams and component descriptions.

## 🛠️ Development

### Setup Development Environment

```bash
make setup
```

This will:
- Create `.env` from `.env.example`
- Install pre-commit hooks
- Install Python dependencies

### Common Development Tasks

```bash
make help           # Show all available targets
make fmt            # Format all code (Alloy configs, Python, Shell)
make lint           # Lint all code
make test           # Run all tests
make test-coverage  # Run tests with coverage report
make build          # Build all Docker images
make scan           # Scan images for vulnerabilities
make ci             # Run full CI pipeline locally
```

### Pre-Commit Hooks

Pre-commit hooks automatically run on `git commit`:
- **Alloy configs**: Format with `alloy fmt`
- **Python**: Format with `black`, `isort`, lint with `ruff`
- **Shell scripts**: Lint with `shellcheck`, format with `shfmt`
- **YAML/JSON**: Validate syntax
- **Secrets**: Detect with `detect-secrets`

To run manually:
```bash
make pre-commit
# Or: pre-commit run --all-files
```

## 🐛 Troubleshooting

### Common Issues

**Issue**: Alloy fails to start with "port already in use"
```bash
# Solution: Check for existing processes
lsof -i :4317
lsof -i :4318
# Kill conflicting processes or change ports in docker-compose.yaml
```

**Issue**: AI Sorter circuit breaker is OPEN
```bash
# Solution: Check AI Sorter logs and Grok API status
docker compose logs ai-sorter
# Verify API key is valid
curl -H "Authorization: Bearer $GROK_API_KEY" https://api.x.ai/v1/chat/completions
# Circuit breaker will auto-recover after timeout (default 60s)
```

**Issue**: No metrics in Prometheus
```bash
# Solution: Verify Prometheus scrape targets
curl http://localhost:9090/api/v1/targets
# Check Alloy metrics endpoint
curl http://localhost:8889/metrics
# Check ServiceMonitor in Kubernetes
kubectl get servicemonitor -n monitoring
```

**Issue**: Grafana dashboards show "No data"
```bash
# Solution: Verify data sources configured
curl http://localhost:3000/api/datasources
# Send test telemetry
make test-e2e
```

**Issue**: NetworkPolicy blocks traffic in Kubernetes
```bash
# Solution: Temporarily disable to test
helm upgrade alloy-processors ./alloy/helm/alloy-dynamic-processors \
  --set networkPolicy.enabled=false
# Check CNI plugin supports NetworkPolicy
kubectl get nodes -o wide
```

See [docs/overview.md#troubleshooting](docs/overview.md#troubleshooting) for comprehensive troubleshooting guide.

## 🔐 Security

### Reporting Vulnerabilities

Please report security vulnerabilities via the [Security Policy](SECURITY.md).

### Security Features

- **Container Hardening**: Non-root users, read-only filesystem, minimal base images
- **Supply Chain Security**: Signed images (cosign), SBOM generation (syft), vulnerability scanning (Trivy)
- **Network Security**: NetworkPolicy for zero-trust networking, TLS for external communication
- **Secret Management**: Kubernetes Secrets, no hardcoded credentials
- **PII Redaction**: Automatic redaction of emails, SSNs, credit cards, API keys in logs
- **Dependency Scanning**: Automated security scanning in CI/CD

## 📈 Monitoring & Alerting

### Grafana Dashboards

- **Alloy Pipeline Health** (`monitoring/grafana/dashboards/alloy-pipeline-health.json`)
  - Telemetry ingestion rate (spans, metrics, logs)
  - Drop rate and export errors
  - Memory usage and batch processing latency

- **AI Sorter Performance** (`monitoring/grafana/dashboards/ai-sorter-performance.json`)
  - Circuit breaker state
  - Request rate and latency percentiles
  - Items classified by category
  - API call success rate

### Prometheus Alerts

20+ production-ready alerts in 4 groups (`monitoring/alerts/alloy-alerts.yaml`):
- **Alloy Pipeline**: High drop rate, export failures, receiver errors
- **AI Sorter**: Circuit breaker open, high latency, classification failures
- **Resource Utilization**: High CPU/memory, pod not ready
- **Data Quality**: Missing critical labels, high error log rate

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Code of conduct
- Development workflow
- PR guidelines
- Coding standards
- Testing requirements

## 📦 Release Process

Releases follow [Semantic Versioning](https://semver.org/) and are automated via GitHub Actions:

1. Create release tag: `git tag -a v1.0.0 -m "Release v1.0.0"`
2. Push tag: `git push origin v1.0.0`
3. GitHub Actions automatically:
   - Builds multi-arch images (amd64, arm64)
   - Scans for vulnerabilities with Trivy
   - Generates SBOM with syft
   - Signs images with cosign (keyless OIDC)
   - Pushes to GitHub Container Registry (GHCR)
   - Creates GitHub Release with notes

See [docs/release.md](docs/release.md) for detailed release procedures, checklists, and rollback procedures.

## 📝 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Grafana Alloy](https://grafana.com/docs/alloy/) - Vendor-agnostic OTel distribution
- [OpenTelemetry](https://opentelemetry.io/) - Observability framework
- [xAI Grok](https://x.ai/) - AI-powered classification (optional integration)
- [Grafana Cloud](https://grafana.com/products/cloud/) - Managed observability platform

## 📞 Support

- **GitHub Issues**: [Create an issue](https://github.com/ChaosKyle/alloy-dynamic-processors/issues)
- **Documentation**: [docs/overview.md](docs/overview.md)
- **Grafana Community**: [Forum](https://community.grafana.com/)
- **Commercial Support**: [Grafana Labs](https://grafana.com/contact/)

---

**Built with ❤️ by the Alloy Dynamic Processors community**
