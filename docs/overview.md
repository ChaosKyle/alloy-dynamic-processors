# Alloy Dynamic Processors - Overview

## Introduction

The Alloy Dynamic Processors project is a production-ready, enterprise-grade observability data processing platform built on Grafana Alloy. It provides advanced resource detection, intelligent labeling strategies, optional AI-driven sorting, and seamless integration with Grafana Cloud and the broader observability ecosystem.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Key Features](#key-features)
- [Component Architecture](#component-architecture)
- [Data Flow](#data-flow)
- [Deployment Models](#deployment-models)
- [Security Architecture](#security-architecture)
- [Integration Points](#integration-points)
- [Scalability & Performance](#scalability--performance)
- [Getting Started](#getting-started)

## Architecture Overview

### High-Level System Architecture

```mermaid
graph TB
    subgraph "Data Sources"
        APP[Applications]
        K8S[Kubernetes Clusters]
        INFRA[Infrastructure]
        CLOUD[Cloud Services]
    end

    subgraph "Ingestion Layer"
        OTLP_GRPC[OTLP gRPC<br/>:4317]
        OTLP_HTTP[OTLP HTTP<br/>:4318]
    end

    subgraph "Processing Layer - Grafana Alloy"
        RES_DET[Resource<br/>Detection]
        LABELING[Intelligent<br/>Labeling]
        BATCH[Batch<br/>Processor]
        MEM_LIM[Memory<br/>Limiter]

        subgraph "Optional AI Sorter Sidecar"
            AI_API[FastAPI<br/>Service]
            AI_CLASS[AI<br/>Classifier]
            AI_ROUTE[Smart<br/>Router]
        end
    end

    subgraph "Export Layer"
        PROM_EXP[Prometheus<br/>Exporter]
        LOKI_EXP[Loki<br/>Exporter]
        TEMPO_EXP[Tempo<br/>Exporter]
    end

    subgraph "Grafana Cloud / Local Stack"
        PROM[Prometheus]
        LOKI[Loki]
        TEMPO[Tempo]
        GRAFANA[Grafana<br/>Dashboards]
    end

    subgraph "Observability & Monitoring"
        HEALTH[Health<br/>Checks]
        METRICS[Metrics<br/>Endpoint]
        ALERTS[Alert<br/>Manager]
    end

    APP --> OTLP_GRPC
    K8S --> OTLP_GRPC
    INFRA --> OTLP_HTTP
    CLOUD --> OTLP_HTTP

    OTLP_GRPC --> RES_DET
    OTLP_HTTP --> RES_DET

    RES_DET --> LABELING
    LABELING --> MEM_LIM
    MEM_LIM --> BATCH

    BATCH -.->|Optional| AI_API
    AI_API --> AI_CLASS
    AI_CLASS --> AI_ROUTE
    AI_ROUTE --> BATCH

    BATCH --> PROM_EXP
    BATCH --> LOKI_EXP
    BATCH --> TEMPO_EXP

    PROM_EXP --> PROM
    LOKI_EXP --> LOKI
    TEMPO_EXP --> TEMPO

    PROM --> GRAFANA
    LOKI --> GRAFANA
    TEMPO --> GRAFANA

    GRAFANA -.-> ALERTS

    RES_DET -.-> HEALTH
    LABELING -.-> METRICS
    AI_API -.-> HEALTH

    classDef optional fill:#f9f,stroke:#333,stroke-width:2px,stroke-dasharray: 5 5
    class AI_API,AI_CLASS,AI_ROUTE optional
```

### Component Responsibilities

```mermaid
graph LR
    subgraph "Alloy Core Components"
        A[OTLP Receivers] -->|Raw Telemetry| B[Resource Detection]
        B -->|Enriched Data| C[Labeling Processor]
        C -->|Labeled Data| D[Memory Limiter]
        D -->|Controlled Flow| E[Batch Processor]
        E -->|Batched Data| F[Exporters]
    end

    subgraph "AI Sorter Sidecar (Optional)"
        G[FastAPI Server]
        H[AI Classification]
        I[Route Decision]

        G --> H
        H --> I
    end

    E -.->|Optional Classification| G
    I -.->|Routing Hints| E

    F --> J[Prometheus]
    F --> K[Loki]
    F --> L[Tempo]

    style G fill:#ffe6e6
    style H fill:#ffe6e6
    style I fill:#ffe6e6
```

## Key Features

### Core Capabilities

1. **Multi-Protocol Ingestion**
   - OTLP gRPC (port 4317)
   - OTLP HTTP (port 4318)
   - Support for logs, metrics, and traces

2. **Advanced Processing Pipeline**
   - Automatic resource detection (K8s, Docker, cloud providers)
   - Intelligent labeling and enrichment
   - Memory-aware buffering and batching
   - Performance optimization with configurable workers

3. **Optional AI-Driven Sorting** (Feature Flag: `AI_SORTER_ENABLED`)
   - AI-powered classification of telemetry data
   - Smart routing based on severity/priority
   - Integration with xAI Grok API
   - Fail-safe operation (defaults to standard routing if AI fails)

4. **Production-Ready Features**
   - Comprehensive health checks and readiness probes
   - Prometheus metrics for observability
   - Security hardening (non-root containers, read-only FS)
   - Multi-arch image support (amd64, arm64)
   - SBOM generation and image signing

5. **Flexible Deployment Options**
   - Local development with Docker Compose
   - Kubernetes via Helm charts
   - Support for Grafana Cloud and self-hosted stacks

## Component Architecture

### Alloy Processing Pipeline

```mermaid
flowchart TD
    START([Telemetry Data]) --> RECV{Receiver Type}

    RECV -->|gRPC| OTLP_G[OTLP gRPC<br/>Receiver]
    RECV -->|HTTP| OTLP_H[OTLP HTTP<br/>Receiver]

    OTLP_G --> RES[Resource<br/>Detection<br/>Processor]
    OTLP_H --> RES

    RES --> ATTR[Attributes<br/>Processor]

    ATTR --> MEM{Memory<br/>Limit OK?}

    MEM -->|Yes| BATCH[Batch<br/>Processor]
    MEM -->|No| DROP[Drop/Back<br/>Pressure]

    BATCH --> AI_CHECK{AI Sorter<br/>Enabled?}

    AI_CHECK -->|Yes| AI[AI Classification<br/>& Routing]
    AI_CHECK -->|No| ROUTE[Standard<br/>Routing]

    AI --> ROUTE

    ROUTE --> EXP_TYPE{Data Type}

    EXP_TYPE -->|Metrics| PROM[Prometheus<br/>Exporter]
    EXP_TYPE -->|Logs| LOKI[Loki<br/>Exporter]
    EXP_TYPE -->|Traces| TEMPO[Tempo<br/>Exporter]

    PROM --> DEST[Grafana Cloud /<br/>Local Stack]
    LOKI --> DEST
    TEMPO --> DEST

    style AI fill:#ffe6e6
    style AI_CHECK fill:#fff4e6
    style DROP fill:#ffe6e6
```

### AI Sorter Sidecar Architecture

```mermaid
flowchart TD
    START([Telemetry Batch]) --> VALIDATE[Input<br/>Validation]

    VALIDATE -->|Valid| EXTRACT[Feature<br/>Extraction]
    VALIDATE -->|Invalid| REJECT[Return<br/>Error]

    EXTRACT --> CACHE{Cache<br/>Hit?}

    CACHE -->|Yes| CACHED[Use Cached<br/>Classification]
    CACHE -->|No| AI_CALL[AI API<br/>Call]

    AI_CALL --> RETRY{Success?}

    RETRY -->|Yes| CLASSIFY[Classification<br/>Result]
    RETRY -->|No, Retries Left| BACKOFF[Exponential<br/>Backoff]
    RETRY -->|No, Max Retries| FALLBACK[Fallback<br/>Classification]

    BACKOFF --> AI_CALL

    CACHED --> CLASSIFY
    FALLBACK --> CLASSIFY

    CLASSIFY --> ROUTE[Generate<br/>Routing Hints]

    ROUTE --> LOG[Log Decision<br/>with PII Redaction]

    LOG --> METRICS[Update<br/>Metrics]

    METRICS --> RESPONSE([Return<br/>Classification])

    style AI_CALL fill:#e6f3ff
    style CACHE fill:#e6ffe6
    style FALLBACK fill:#ffe6e6
```

## Data Flow

### Telemetry Data Journey

```mermaid
sequenceDiagram
    participant App as Application
    participant Alloy as Grafana Alloy
    participant AI as AI Sorter<br/>(Optional)
    participant GC as Grafana Cloud
    participant Graf as Grafana UI

    App->>Alloy: Send telemetry (OTLP)
    activate Alloy

    Alloy->>Alloy: Resource detection
    Alloy->>Alloy: Labeling & enrichment
    Alloy->>Alloy: Memory limiting
    Alloy->>Alloy: Batching

    alt AI Sorter Enabled
        Alloy->>AI: Request classification
        activate AI
        AI->>AI: AI model inference
        AI-->>Alloy: Classification result
        deactivate AI
        Alloy->>Alloy: Apply routing hints
    else AI Sorter Disabled
        Alloy->>Alloy: Standard routing
    end

    Alloy->>GC: Export metrics (Prometheus)
    Alloy->>GC: Export logs (Loki)
    Alloy->>GC: Export traces (Tempo)

    deactivate Alloy

    GC->>Graf: Query data
    Graf-->>GC: Return results
    GC-->>App: Observability insights
```

## Deployment Models

### Local Development (Docker Compose)

```mermaid
graph TB
    subgraph "Docker Compose Stack"
        ALLOY[Grafana Alloy<br/>Container]
        AI[AI Sorter<br/>Container<br/><i>optional</i>]
        PROM[Prometheus<br/>Container]
        LOKI[Loki<br/>Container]
        TEMPO[Tempo<br/>Container]
        GRAFANA[Grafana<br/>Container]
    end

    ALLOY -.->|Optional| AI
    ALLOY --> PROM
    ALLOY --> LOKI
    ALLOY --> TEMPO

    PROM --> GRAFANA
    LOKI --> GRAFANA
    TEMPO --> GRAFANA

    style AI fill:#ffe6e6,stroke-dasharray: 5 5
```

### Kubernetes Production Deployment

```mermaid
graph TB
    subgraph "Kubernetes Cluster"
        subgraph "Monitoring Namespace"
            subgraph "Alloy Pod"
                ALLOY_C[Alloy<br/>Container]
                AI_C[AI Sorter<br/>Sidecar<br/><i>optional</i>]
            end

            SVC[Service]
            CM[ConfigMap]
            SEC[Secrets]
            HPA[Horizontal Pod<br/>Autoscaler]
            PDB[Pod Disruption<br/>Budget]
        end

        subgraph "Ingress"
            ING[Ingress<br/>Controller]
        end

        subgraph "Network Policies"
            NP_EGRESS[Egress to<br/>Grafana Cloud]
            NP_INGRESS[Ingress from<br/>Applications]
        end
    end

    subgraph "External"
        GC[Grafana Cloud]
    end

    ING --> SVC
    SVC --> ALLOY_C
    ALLOY_C -.->|Optional| AI_C
    CM --> ALLOY_C
    SEC --> ALLOY_C
    SEC --> AI_C

    HPA -.->|Scale| ALLOY_C

    ALLOY_C -->|Via Egress Policy| GC

    style AI_C fill:#ffe6e6,stroke-dasharray: 5 5
```

## Security Architecture

### Security Layers

```mermaid
graph TD
    subgraph "Container Security"
        A[Non-root User]
        B[Read-only Filesystem]
        C[Minimal Base Image]
        D[No Privileged Mode]
    end

    subgraph "Network Security"
        E[Network Policies]
        F[TLS Encryption]
        G[mTLS for Internal]
        H[Egress Restrictions]
    end

    subgraph "Secret Management"
        I[Kubernetes Secrets]
        J[External Secrets<br/>Operator]
        K[SOPS Encryption]
        L[No Hardcoded Creds]
    end

    subgraph "Runtime Security"
        M[SecurityContext]
        N[Pod Security Standards]
        O[Resource Limits]
        P[AppArmor/Seccomp]
    end

    subgraph "Image Security"
        Q[SBOM Generation]
        R[Image Signing<br/>cosign]
        S[Vulnerability Scanning<br/>Trivy]
        T[Multi-stage Builds]
    end

    style I fill:#e6f3ff
    style J fill:#e6f3ff
    style K fill:#e6f3ff
```

### Security Controls

| Layer | Control | Implementation |
|-------|---------|----------------|
| Container | Non-root execution | `runAsUser: 10001`, `runAsNonRoot: true` |
| Container | Read-only root FS | `readOnlyRootFilesystem: true` |
| Container | Drop capabilities | `drop: ["ALL"]` |
| Network | TLS for exporters | Configured in Alloy exporters |
| Network | Network policies | Restrict ingress/egress |
| Secrets | No plaintext secrets | Use Kubernetes Secrets or External Secrets |
| Secrets | API key rotation | Regular rotation policy |
| Supply Chain | Image signing | Cosign keyless OIDC |
| Supply Chain | SBOM | Syft generation in CI |
| Supply Chain | Vulnerability scanning | Trivy in CI pipeline |

## Integration Points

### Grafana Cloud Integration

```mermaid
graph LR
    ALLOY[Alloy<br/>Exporters] -->|Remote Write| PROM_GC[Grafana Cloud<br/>Prometheus]
    ALLOY -->|OTLP| TEMPO_GC[Grafana Cloud<br/>Tempo]
    ALLOY -->|Push API| LOKI_GC[Grafana Cloud<br/>Loki]

    PROM_GC --> GRAFANA[Grafana<br/>Dashboards]
    TEMPO_GC --> GRAFANA
    LOKI_GC --> GRAFANA

    GRAFANA --> ALERTS[Alert Manager]
    GRAFANA --> ONCALL[Grafana OnCall]
```

### Data Sources Integration

```mermaid
graph TB
    subgraph "Application Sources"
        APP1[Microservices<br/>OpenTelemetry SDK]
        APP2[Legacy Apps<br/>Log Files]
        APP3[Batch Jobs]
    end

    subgraph "Infrastructure Sources"
        INFRA1[Kubernetes<br/>kube-state-metrics]
        INFRA2[Node Exporter]
        INFRA3[System Logs]
    end

    subgraph "Cloud Sources"
        CLOUD1[AWS CloudWatch]
        CLOUD2[GCP Operations]
        CLOUD3[Azure Monitor]
    end

    APP1 -->|OTLP gRPC| ALLOY[Alloy]
    APP2 -->|Promtail/Fluent Bit| ALLOY
    APP3 -->|OTLP HTTP| ALLOY

    INFRA1 -->|Prometheus Scrape| ALLOY
    INFRA2 -->|Prometheus Scrape| ALLOY
    INFRA3 -->|Syslog/Journald| ALLOY

    CLOUD1 -->|CloudWatch Exporter| ALLOY
    CLOUD2 -->|GCP Exporter| ALLOY
    CLOUD3 -->|Azure Exporter| ALLOY
```

## Scalability & Performance

### Horizontal Scaling Strategy

```mermaid
graph TD
    LB[Load Balancer /<br/>Service] --> POD1[Alloy Pod 1]
    LB --> POD2[Alloy Pod 2]
    LB --> POD3[Alloy Pod N]

    HPA[Horizontal Pod<br/>Autoscaler] -.->|Monitor & Scale| POD1
    HPA -.->|Monitor & Scale| POD2
    HPA -.->|Monitor & Scale| POD3

    METRICS[Metrics<br/>CPU/Memory/Custom] --> HPA

    POD1 --> EXPORT[Exporters]
    POD2 --> EXPORT
    POD3 --> EXPORT
```

### Performance Characteristics

| Component | Throughput | Latency | Resource Usage |
|-----------|------------|---------|----------------|
| OTLP Receiver | ~50K spans/sec | < 10ms p95 | 500MB RAM |
| Batch Processor | Configurable | Batch timeout | Memory-limited |
| AI Sorter (optional) | ~1K req/sec | < 200ms p95 | 1GB RAM |
| Prometheus Exporter | 10K samples/sec | < 50ms p95 | Minimal |

## Getting Started

### Quick Start (Local)

1. **Clone and configure**
   ```bash
   git clone <repository-url>
   cd alloy-dynamic-processors
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. **Deploy with Docker Compose**
   ```bash
   make up
   # or
   docker-compose up -d
   ```

3. **Verify health**
   ```bash
   curl http://localhost:13133/healthz
   ```

### Production Deployment (Kubernetes)

1. **Prepare Helm values**
   ```bash
   cp alloy/helm/alloy-dynamic-processors/values.yaml my-values.yaml
   # Edit my-values.yaml
   ```

2. **Deploy with Helm**
   ```bash
   helm install alloy-processors ./alloy/helm/alloy-dynamic-processors \
     -f my-values.yaml \
     --namespace monitoring \
     --create-namespace
   ```

3. **Verify deployment**
   ```bash
   kubectl get pods -n monitoring
   kubectl port-forward -n monitoring svc/alloy-processors 13133:13133
   curl http://localhost:13133/healthz
   ```

## Next Steps

- [Detailed Architecture Documentation](./ARCHITECTURE.md)
- [Deployment Guide](./DEPLOYMENT_GUIDE.md)
- [Integration Patterns](./INTEGRATION_PATTERNS.md)
- [Security Best Practices](../SECURITY.md)
- [Contributing Guide](../CONTRIBUTING.md)

## Support

For issues, questions, or contributions, please refer to:
- GitHub Issues: [Report bugs or request features]
- Documentation: [Full documentation in `/docs`]
- Security: [See SECURITY.md for reporting vulnerabilities]
