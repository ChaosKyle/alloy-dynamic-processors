# Migration Guide: OpenTelemetry Collector to Grafana Alloy

This guide helps you migrate from the OpenTelemetry Collector to Grafana Alloy for the dynamic processors implementation.

## Table of Contents

- [Why Migrate](#why-migrate)
- [Key Differences](#key-differences)
- [Migration Steps](#migration-steps)
- [Configuration Conversion](#configuration-conversion)
- [Feature Parity](#feature-parity)
- [Troubleshooting](#troubleshooting)

## Why Migrate

### Benefits of Grafana Alloy

- **Grafana Cloud Optimized**: Native integration with Grafana Cloud services
- **Modern Configuration**: River language is more readable than YAML
- **Better Performance**: Optimized for resource efficiency
- **Vendor-Agnostic**: Built on OTel Collector, maintains compatibility
- **Active Development**: Part of Grafana's core observability strategy
- **Simplified Operations**: Fewer moving parts, easier debugging

### When to Migrate

✅ **Good candidates for migration:**
- New deployments starting fresh
- Grafana Cloud users
- Teams wanting simpler configuration
- Projects valuing Grafana ecosystem integration

⚠️ **Consider carefully:**
- Production systems with complex OTel configurations
- Heavy customization with OTel contrib components
- Teams with deep OTel expertise
- Multi-vendor observability backends

## Key Differences

### Configuration Language

**OTel Collector** uses YAML:
```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 10s
    send_batch_size: 1024

exporters:
  otlp:
    endpoint: https://tempo.example.com:443
```

**Grafana Alloy** uses River (HCL-like):
```river
otelcol.receiver.otlp "default" {
  grpc {
    endpoint = "0.0.0.0:4317"
  }
  http {
    endpoint = "0.0.0.0:4318"
  }
  output {
    metrics = [otelcol.processor.batch.default.input]
    logs    = [otelcol.processor.batch.default.input]
    traces  = [otelcol.processor.batch.default.input]
  }
}

otelcol.processor.batch "default" {
  timeout          = "10s"
  send_batch_size  = 1024

  output {
    metrics = [otelcol.exporter.otlp.tempo.input]
    logs    = [otelcol.exporter.otlp.tempo.input]
    traces  = [otelcol.exporter.otlp.tempo.input]
  }
}

otelcol.exporter.otlp "tempo" {
  client {
    endpoint = "https://tempo.example.com:443"
  }
}
```

### Component Model

| Aspect | OTel Collector | Grafana Alloy |
|--------|---------------|---------------|
| **Config Format** | YAML | River (HCL-like) |
| **Component IDs** | Implicit from config | Explicit (e.g., `"default"`) |
| **Pipeline Definition** | service.pipelines | output { } blocks |
| **Extensions** | Separate section | Integrated components |
| **Reload** | SIGHUP signal | Auto-reload on change |

### Binary & Deployment

| Feature | OTel Collector | Grafana Alloy |
|---------|---------------|---------------|
| **Binary Name** | `otelcol` or `otelcol-contrib` | `alloy` |
| **Default Config** | `/etc/otelcol/config.yaml` | `/etc/alloy/config.alloy` |
| **Default Port (UI)** | 13133 (health), 8888 (metrics) | 12345 (UI), 13133 (health) |
| **Docker Image** | `otel/opentelemetry-collector-contrib` | `grafana/alloy` |

## Migration Steps

### Step 1: Assess Current Configuration

```bash
# Review your current OTel Collector config
cat /etc/otelcol/config.yaml

# Document components used:
# - Receivers (OTLP, Prometheus, Jaeger, etc.)
# - Processors (batch, attributes, resource, etc.)
# - Exporters (OTLP, Prometheus, Loki, etc.)
# - Extensions (health_check, pprof, etc.)
```

### Step 2: Install Grafana Alloy

**Docker:**
```bash
docker pull grafana/alloy:latest
```

**Kubernetes (Helm):**
```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
helm install alloy grafana/alloy
```

**Binary (Linux):**
```bash
# Download from https://github.com/grafana/alloy/releases
curl -LO https://github.com/grafana/alloy/releases/download/v1.0.0/alloy-linux-amd64
chmod +x alloy-linux-amd64
sudo mv alloy-linux-amd64 /usr/local/bin/alloy
```

### Step 3: Convert Configuration

Use the examples in this repository as templates:
- `alloy/configs/main.alloy` - Basic configuration
- `alloy/configs/enhanced-with-sort.alloy` - With AI sorting
- `alloy/examples/grafana-cloud-production.alloy` - Grafana Cloud

**Conversion tool (if available):**
```bash
# Alloy may provide conversion tool in future
alloy convert --input /etc/otelcol/config.yaml --output /etc/alloy/config.alloy
```

**Manual conversion pattern:**

1. **Receivers** → `otelcol.receiver.*`
2. **Processors** → `otelcol.processor.*`
3. **Exporters** → `otelcol.exporter.*`
4. **Extensions** → Alloy components (e.g., `prometheus.exporter.*`)

### Step 4: Test in Parallel

Run both collectors side-by-side initially:

```bash
# OTel Collector on ports 4317/4318
# Alloy on ports 14317/14318 (temp)

# Docker Compose example
services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    ports: ["4317:4317", "4318:4318"]

  alloy:
    image: grafana/alloy:latest
    ports: ["14317:4317", "14318:4318", "12345:12345"]
```

Send test traffic to both and compare:
```bash
# Send to OTel Collector
curl -X POST http://localhost:4318/v1/traces -d '{...}'

# Send to Alloy
curl -X POST http://localhost:14318/v1/traces -d '{...}'

# Compare metrics
curl http://otel-collector:8888/metrics | grep otelcol_receiver
curl http://alloy:8889/metrics | grep otelcol_receiver
```

### Step 5: Gradual Traffic Migration

Use DNS/load balancer to shift traffic gradually:

```yaml
# Kubernetes Service example
apiVersion: v1
kind: Service
metadata:
  name: telemetry-collector
spec:
  selector:
    app: alloy  # Change from 'otel-collector'
  ports:
  - name: otlp-grpc
    port: 4317
  - name: otlp-http
    port: 4318
```

Traffic split example (Istio):
```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: telemetry-collector
spec:
  hosts:
  - telemetry-collector
  http:
  - route:
    - destination:
        host: otel-collector
      weight: 50
    - destination:
        host: alloy
      weight: 50
```

### Step 6: Monitor and Validate

```bash
# Compare key metrics
kubectl logs -l app=alloy -n monitoring
kubectl logs -l app=otel-collector -n monitoring

# Check for errors
alloy metrics | grep error
otelcol metrics | grep error

# Validate data in backends
# - Prometheus: query rate(otelcol_receiver_accepted_spans[5m])
# - Grafana: check dashboards
# - Loki: verify log ingestion
```

### Step 7: Complete Cutover

Once confident:
```bash
# Stop OTel Collector
docker stop otel-collector
# or
kubectl scale deployment otel-collector --replicas=0

# Update DNS/services to point to Alloy
# Remove OTel Collector from infrastructure
```

## Configuration Conversion

### Common Patterns

#### OTLP Receiver

**OTel Collector:**
```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
        tls:
          cert_file: /certs/server.crt
          key_file: /certs/server.key
      http:
        endpoint: 0.0.0.0:4318
```

**Grafana Alloy:**
```river
otelcol.receiver.otlp "default" {
  grpc {
    endpoint = "0.0.0.0:4317"
    tls {
      cert_file = "/certs/server.crt"
      key_file  = "/certs/server.key"
    }
  }

  http {
    endpoint = "0.0.0.0:4318"
  }

  output {
    metrics = [otelcol.processor.batch.default.input]
    logs    = [otelcol.processor.batch.default.input]
    traces  = [otelcol.processor.batch.default.input]
  }
}
```

#### Batch Processor

**OTel Collector:**
```yaml
processors:
  batch:
    timeout: 10s
    send_batch_size: 1024
    send_batch_max_size: 2048
```

**Grafana Alloy:**
```river
otelcol.processor.batch "default" {
  timeout             = "10s"
  send_batch_size     = 1024
  send_batch_max_size = 2048

  output {
    metrics = [otelcol.exporter.otlp.grafana_cloud.input]
    logs    = [otelcol.exporter.otlp.grafana_cloud.input]
    traces  = [otelcol.exporter.otlp.grafana_cloud.input]
  }
}
```

#### Attributes Processor

**OTel Collector:**
```yaml
processors:
  attributes:
    actions:
      - key: environment
        value: production
        action: insert
      - key: sensitive_field
        action: delete
```

**Grafana Alloy:**
```river
otelcol.processor.attributes "default" {
  action {
    key    = "environment"
    value  = "production"
    action = "insert"
  }

  action {
    key    = "sensitive_field"
    action = "delete"
  }

  output {
    metrics = [otelcol.processor.batch.default.input]
    logs    = [otelcol.processor.batch.default.input]
    traces  = [otelcol.processor.batch.default.input]
  }
}
```

#### Prometheus Exporter

**OTel Collector:**
```yaml
exporters:
  prometheus:
    endpoint: 0.0.0.0:8889
```

**Grafana Alloy:**
```river
prometheus.exporter.otelcol "default" {
  # Alloy automatically exposes OTel metrics at its metrics endpoint
}

# Or use OTLP exporter to Prometheus
otelcol.exporter.otlp "prometheus" {
  client {
    endpoint = "http://prometheus:9090"
  }
}
```

#### Grafana Cloud Exporters

**OTel Collector:**
```yaml
exporters:
  otlp/grafana_cloud_traces:
    endpoint: ${GRAFANA_CLOUD_TEMPO_URL}
    headers:
      authorization: Basic ${GRAFANA_CLOUD_AUTH}

  loki:
    endpoint: ${GRAFANA_CLOUD_LOKI_URL}
    headers:
      authorization: Basic ${GRAFANA_CLOUD_AUTH}

  prometheusremotewrite:
    endpoint: ${GRAFANA_CLOUD_PROMETHEUS_URL}
    headers:
      authorization: Basic ${GRAFANA_CLOUD_AUTH}
```

**Grafana Alloy:**
```river
otelcol.exporter.otlp "grafana_cloud_traces" {
  client {
    endpoint = env("GRAFANA_CLOUD_TEMPO_URL")
    auth     = otelcol.auth.basic.grafana_cloud.handler
  }
}

otelcol.exporter.loki "grafana_cloud" {
  forward_to = [loki.write.grafana_cloud.receiver]
}

loki.write "grafana_cloud" {
  endpoint {
    url = env("GRAFANA_CLOUD_LOKI_URL")
    basic_auth {
      username = env("GRAFANA_CLOUD_USERNAME")
      password = env("GRAFANA_CLOUD_API_KEY")
    }
  }
}

prometheus.remote_write "grafana_cloud" {
  endpoint {
    url = env("GRAFANA_CLOUD_PROMETHEUS_URL")
    basic_auth {
      username = env("GRAFANA_CLOUD_USERNAME")
      password = env("GRAFANA_CLOUD_API_KEY")
    }
  }
}

otelcol.auth.basic "grafana_cloud" {
  username = env("GRAFANA_CLOUD_USERNAME")
  password = env("GRAFANA_CLOUD_API_KEY")
}
```

## Feature Parity

### Fully Supported

✅ OTLP receivers (gRPC, HTTP)
✅ Batch processor
✅ Attributes processor
✅ Resource processor
✅ Memory limiter processor
✅ OTLP exporters
✅ Prometheus exporters
✅ Loki exporters

### Requires Alternative Approach

⚠️ **Tail Sampling Processor**
- Alloy: Not directly supported, use probabilistic sampling

⚠️ **Span Metrics Processor**
- Alloy: Use Tempo's native span metrics

⚠️ **Some Contrib Receivers**
- Check Alloy documentation for equivalents

### Not Yet Supported

❌ Some exotic processors from contrib
❌ Some legacy receivers

**Workaround**: Run OTel Collector for unsupported components, forward to Alloy

## Troubleshooting

### Configuration Validation

```bash
# Validate Alloy config
alloy fmt --verify /etc/alloy/config.alloy

# Test run without starting
alloy run /etc/alloy/config.alloy --dry-run

# Check syntax
alloy fmt /etc/alloy/config.alloy
```

### Common Issues

**Issue**: "Component not found"
```
Solution: Check component name and type
- otelcol.receiver.otlp (not just otlp)
- Use quotes for component IDs: "default"
```

**Issue**: "No output defined"
```
Solution: Every component needs output block
output {
  metrics = [next_component.input]
  logs    = [next_component.input]
  traces  = [next_component.input]
}
```

**Issue**: "Port already in use"
```
Solution: Check for OTel Collector still running
lsof -i :4317
kill <pid>
```

### Debug Mode

```bash
# Run Alloy with debug logging
alloy run /etc/alloy/config.alloy --log.level=debug

# View component graph
alloy graph /etc/alloy/config.alloy
```

### Comparison Checklist

- [ ] All receivers configured
- [ ] All processors in place
- [ ] All exporters connected
- [ ] Health checks working
- [ ] Metrics endpoint accessible
- [ ] Data flowing to backends
- [ ] Performance comparable
- [ ] Error rates same or lower

## Resources

- [Alloy Documentation](https://grafana.com/docs/alloy/)
- [River Language Spec](https://grafana.com/docs/alloy/latest/concepts/configuration-language/)
- [OTel→Alloy Examples](../alloy/examples/)
- [Community Slack](https://grafana.slack.com/)

## Need Help?

- GitHub Issues: [Create an issue](https://github.com/ChaosKyle/alloy-dynamic-processors/issues)
- Grafana Community: [Forum](https://community.grafana.com/)
- Commercial Support: [Grafana Labs](https://grafana.com/contact/)
