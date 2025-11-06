# Architecture Decision Records (ADRs)

This document records significant architectural and design decisions made in the Alloy Dynamic Processors project.

## Format

Each ADR follows this structure:
- **Status**: Accepted | Deprecated | Superseded
- **Context**: The issue motivating this decision
- **Decision**: The change being proposed
- **Consequences**: Impact of the decision

---

## ADR-001: Choice of Grafana Alloy over OpenTelemetry Collector

**Status**: Accepted

**Date**: 2024-07

**Context**:
Need to choose between OpenTelemetry Collector and Grafana Alloy for telemetry processing. Requirements include:
- Native Grafana Cloud integration
- Modern configuration language
- Resource efficiency
- Vendor-agnostic distribution
- Active community support

**Decision**:
Adopt Grafana Alloy as the primary telemetry processor because:
1. Built on OTel Collector but optimized for Grafana ecosystem
2. River configuration language is more readable than YAML
3. Better resource utilization in production
4. Official Grafana support and roadmap alignment
5. Seamless Grafana Cloud integration

**Consequences**:
- **Positive**: Better Grafana Cloud integration, cleaner configs, official support
- **Negative**: Learning curve for River syntax, smaller ecosystem than OTel
- **Mitigation**: Provide migration guide, include OTel comparison docs

---

## ADR-002: AI Sorter as Optional Sidecar

**Status**: Accepted

**Date**: 2024-07

**Context**:
AI-powered classification adds value but has costs:
- External API dependencies (xAI Grok)
- Additional latency (200-500ms)
- API costs per request
- Complexity in deployment

**Decision**:
Make AI Sorter optional via feature flag (`AI_SORTER_ENABLED`) with:
- Default: OFF (standard routing only)
- Sidecar pattern (not inline in Alloy)
- Fail-safe operation (falls back to standard routing)
- Clear cost/benefit documentation

**Consequences**:
- **Positive**: Users control costs, optional complexity, graceful degradation
- **Negative**: Two deployment modes to test, conditional logic complexity
- **Mitigation**: Comprehensive testing of both modes, clear documentation

---

## ADR-003: Circuit Breaker Pattern for AI API

**Status**: Accepted

**Date**: 2024-12

**Context**:
AI API (xAI Grok) is external dependency with potential failures:
- Network issues
- Rate limiting
- API downtime
- Cost overruns

**Decision**:
Implement circuit breaker pattern with:
- States: CLOSED → OPEN → HALF_OPEN
- Failure threshold: 5 consecutive failures
- Timeout: 60 seconds
- Fallback: Standard classification (info/storage)

**Consequences**:
- **Positive**: Prevents cascading failures, automatic recovery, cost protection
- **Negative**: Additional complexity, state management overhead
- **Mitigation**: Comprehensive metrics, clear state visibility, documented tuning

---

## ADR-004: Structured Logging with JSON

**Status**: Accepted

**Date**: 2024-12

**Context**:
Need machine-readable logs for:
- Centralized logging (Loki)
- Log analysis and alerting
- Debugging in production
- Compliance and audit trails

**Decision**:
Use structlog with JSON output format:
- ISO timestamps
- Log levels
- Structured fields
- Request IDs for tracing

**Consequences**:
- **Positive**: Machine-readable, easy parsing, better observability
- **Negative**: Less human-readable in console, slightly larger log volume
- **Mitigation**: Local dev can use logfmt, log aggregation handles JSON well

---

## ADR-005: Pydantic v2 for Data Validation

**Status**: Accepted

**Date**: 2024-12

**Context**:
Need robust input validation for AI Sorter API:
- Type safety
- Request/response validation
- OpenAPI schema generation
- Performance

**Decision**:
Use Pydantic v2 for all API models:
- Field validators for business logic
- Type-safe enums
- Automatic OpenAPI docs
- Performance improvements over v1

**Consequences**:
- **Positive**: Type safety, auto-docs, validation errors, performance
- **Negative**: Pydantic v2 breaking changes from v1, learning curve
- **Mitigation**: Pin to v2.x, comprehensive examples in code

---

## ADR-006: HPA with CPU and Memory Metrics

**Status**: Accepted

**Date**: 2024-12

**Context**:
Need autoscaling for:
- Variable telemetry load
- Cost optimization
- High availability
- Resource efficiency

**Decision**:
Implement HPA with both CPU and memory targets:
- CPU target: 70%
- Memory target: 80%
- Min replicas: 2 (HA)
- Max replicas: 10
- Custom metrics support (future)

**Consequences**:
- **Positive**: Automatic scaling, cost efficiency, handles spikes
- **Negative**: Requires metrics-server, tuning needed per environment
- **Mitigation**: Conservative defaults, detailed tuning guide

---

## ADR-007: NetworkPolicy for Zero-Trust Security

**Status**: Accepted

**Date**: 2024-12

**Context**:
Security requirements:
- Principle of least privilege
- Network segmentation
- Compliance (PCI, HIPAA)
- Defense in depth

**Decision**:
Implement NetworkPolicies for all components:
- Default deny all
- Explicit allow rules
- Separate policies per component
- Egress restrictions

**Consequences**:
- **Positive**: Strong security posture, compliance-ready, blast radius limitation
- **Negative**: Requires CNI with NetworkPolicy support, debugging complexity
- **Mitigation**: Optional flag in Helm, detailed troubleshooting docs

---

## ADR-008: Multi-Arch Image Support

**Status**: Accepted

**Date**: 2024-12

**Context**:
Need to support diverse infrastructure:
- Intel/AMD (amd64)
- ARM-based systems (Graviton, M1/M2, Raspberry Pi)
- Cost optimization (ARM often cheaper)

**Decision**:
Build and publish multi-arch images for:
- linux/amd64
- linux/arm64

**Consequences**:
- **Positive**: Broader compatibility, ARM cost savings, future-proof
- **Negative**: Longer CI build times, larger registry storage
- **Mitigation**: Parallel builds, image retention policies

---

## ADR-009: Cosign Keyless Signing

**Status**: Accepted

**Date**: 2024-12

**Context**:
Need image signing for supply chain security:
- Verify image authenticity
- Prevent tampering
- Compliance requirements
- No key management overhead

**Decision**:
Use cosign with keyless OIDC signing:
- GitHub Actions OIDC token
- No private keys to manage
- Transparency log (Rekor)
- Easy verification

**Consequences**:
- **Positive**: No key management, audit trail, industry standard
- **Negative**: Requires internet for verification, trust in Sigstore
- **Mitigation**: Document offline verification, provide fallback

---

## ADR-010: Helm as Primary Kubernetes Deployment

**Status**: Accepted

**Date**: 2024-12

**Context**:
Need flexible Kubernetes deployment:
- Multiple environments (dev/staging/prod)
- Configuration management
- Version management
- Easy customization

**Decision**:
Use Helm charts as primary Kubernetes deployment method:
- Single chart for all components
- Values files per environment
- Feature flags for optional components
- Comprehensive NOTES.txt

**Consequences**:
- **Positive**: Industry standard, templating power, easy upgrades
- **Negative**: Helm complexity, template debugging challenges
- **Mitigation**: Extensive testing, examples, helm lint in CI

---

## ADR-011: Prometheus for Metrics

**Status**: Accepted

**Date**: 2024-12

**Context**:
Need metrics collection and alerting:
- Time-series data
- Alerting capabilities
- Grafana integration
- Open source

**Decision**:
Use Prometheus as metrics backend:
- Pull-based scraping
- ServiceMonitor for discovery
- Alert rules in YAML
- Native Grafana support

**Consequences**:
- **Positive**: Industry standard, rich ecosystem, battle-tested
- **Negative**: Pull model (not always ideal), cardinality concerns
- **Mitigation**: Metric relabeling, cardinality limits, documentation

---

## ADR-012: PII Redaction in Logs

**Status**: Accepted

**Date**: 2024-12

**Context**:
Regulatory compliance requirements:
- GDPR, CCPA compliance
- PCI DSS for payment data
- HIPAA for health data
- Security best practices

**Decision**:
Implement automatic PII redaction:
- Email addresses
- Social Security Numbers
- Credit card numbers
- Phone numbers
- IP addresses
- API keys/tokens

**Consequences**:
- **Positive**: Compliance-ready, security by default, prevents leaks
- **Negative**: May redact legitimate data, regex performance overhead
- **Mitigation**: Configurable patterns, performance testing, clear docs

---

## ADR-013: Makefile for Developer Experience

**Status**: Accepted

**Date**: 2024-12

**Context**:
Need consistent developer workflows:
- Build, test, deploy commands
- Cross-platform compatibility
- Self-documenting
- Reduce cognitive load

**Decision**:
Create comprehensive Makefile with:
- 60+ organized targets
- Help documentation (make help)
- Color-coded output
- Consistent naming

**Consequences**:
- **Positive**: Excellent DX, easy onboarding, consistent workflows
- **Negative**: Makefile syntax complexity, GNU make dependency
- **Mitigation**: Extensive comments, help target, examples

---

## ADR-014: Docker Compose for Local Development

**Status**: Accepted

**Date**: 2024-12

**Context**:
Need local development environment:
- Full observability stack
- Fast iteration
- No cloud dependencies
- Easy testing

**Decision**:
Provide docker-compose.yaml with:
- Full stack (Alloy, Prometheus, Loki, Tempo, Grafana)
- Optional AI Sorter (profile flag)
- Volume persistence
- Health checks

**Consequences**:
- **Positive**: Fast local testing, no cloud costs, complete stack
- **Negative**: Resource intensive locally, not production equivalent
- **Mitigation**: Profile flags for optional components, clear resource docs

---

## ADR-015: Conventional Commits

**Status**: Accepted

**Date**: 2024-12

**Context**:
Need consistent commit history:
- Automated changelog generation
- Semantic versioning automation
- Clear change categories
- Better collaboration

**Decision**:
Enforce Conventional Commits format:
- Types: feat, fix, docs, style, refactor, test, chore
- Scope: optional component identifier
- Pre-commit hook enforcement
- CI validation

**Consequences**:
- **Positive**: Automated changelog, clear history, better tooling
- **Negative**: Learning curve, rejected commits on format errors
- **Mitigation**: Examples in CONTRIBUTING.md, clear error messages

---

## Superseded Decisions

### ADR-000: Original OTel Collector Choice

**Status**: Superseded by ADR-001

**Date**: 2024-06

**Context**: Initial project used OTel Collector directly.

**Decision**: Switched to Grafana Alloy for better Grafana integration.

**Reason for Change**: Grafana Alloy provides better ecosystem integration while maintaining OTel compatibility.

---

## Future Considerations

### Under Discussion

1. **Kustomize Alternative**: Consider Kustomize alongside Helm for simpler deployments
2. **Service Mesh Integration**: Evaluate Istio/Linkerd integration
3. **Alternative AI Providers**: Support OpenAI, Anthropic, local models
4. **GitOps Integration**: ArgoCD/Flux integration examples
5. **Cost Attribution**: Per-tenant cost tracking and attribution

### Rejected (For Now)

1. **Inline AI Processing in Alloy**: Too complex, sidecar pattern better
2. **MongoDB for State**: Overkill, in-memory state sufficient
3. **gRPC API**: HTTP/JSON simpler, gRPC unnecessary overhead
4. **Multiple AI Models**: Single model simpler, can revisit

---

**Maintenance**: Review this document quarterly or when making significant architectural changes.

**Template for New ADRs**:
```markdown
## ADR-XXX: Title

**Status**: Proposed | Accepted | Deprecated | Superseded

**Date**: YYYY-MM

**Context**:
What is the issue/challenge?

**Decision**:
What are we doing about it?

**Consequences**:
- **Positive**: Benefits
- **Negative**: Drawbacks
- **Mitigation**: How we address drawbacks
```
