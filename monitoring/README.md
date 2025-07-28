# Alloy Dynamic Processors - Monitoring Setup

This directory contains comprehensive monitoring configurations for enterprise-grade observability of Alloy Dynamic Processors.

## 📊 Dashboard Overview

### 1. Service Health Overview (`dashboards/service-health-overview.json`)
- **Purpose**: Real-time service status and key metrics
- **Key Metrics**: Service uptime, request rates, error rates, response times
- **Target Audience**: Operations teams, on-call engineers
- **Refresh Rate**: 30 seconds

### 2. Performance Metrics (`dashboards/performance-metrics.json`)
- **Purpose**: Deep performance analysis and SLA monitoring
- **Key Metrics**: Latency percentiles, throughput, resource efficiency
- **Target Audience**: Performance engineers, capacity planners
- **Refresh Rate**: 1 minute

### 3. Cost Analytics (`dashboards/cost-analytics.json`)
- **Purpose**: Resource cost tracking and optimization recommendations
- **Key Metrics**: CPU/memory costs, utilization rates, waste analysis
- **Target Audience**: FinOps teams, engineering managers
- **Refresh Rate**: 1 hour

### 4. Security Metrics (`dashboards/security-metrics.json`)
- **Purpose**: Security posture and compliance monitoring
- **Key Metrics**: Auth failures, vulnerabilities, compliance status
- **Target Audience**: Security teams, compliance officers
- **Refresh Rate**: 1 minute

## 🚨 Alert Configuration

### Alert Rules (`alerts/alert-rules.yaml`)

**Alert Categories:**
- **Service Health**: Service down, high error rates, pod crashes
- **Performance**: High latency, resource usage, queue backlogs
- **Security**: Unauthorized access, DDoS attacks, vulnerabilities
- **Cost**: Resource waste, budget overruns
- **SLA**: Availability violations, customer impact

**Severity Levels:**
- **Critical**: Immediate response required (pages on-call)
- **Warning**: Requires attention within business hours
- **Info**: Informational alerts for planning

## 🚀 Quick Setup

### Prerequisites
```bash
# Ensure Prometheus and Grafana are running
kubectl get pods -n monitoring

# Verify metrics endpoints are accessible
curl http://localhost:9090/api/v1/targets  # Prometheus targets
curl http://localhost:3000/api/health      # Grafana health
```

### 1. Import Dashboards
```bash
# Using Grafana API
for dashboard in monitoring/dashboards/*.json; do
  curl -X POST \
    -H "Authorization: Bearer $GRAFANA_API_KEY" \
    -H "Content-Type: application/json" \
    -d "@$dashboard" \
    http://grafana:3000/api/dashboards/db
done

# Or import manually through Grafana UI:
# Settings → Data Sources → Import → Upload JSON files
```

### 2. Configure Alert Rules
```bash
# Apply Prometheus alert rules
kubectl create configmap prometheus-alerts \
  --from-file=monitoring/alerts/alert-rules.yaml \
  -n monitoring

# Update Prometheus configuration to include rules
kubectl patch configmap prometheus-config \
  --patch '{"data":{"prometheus.yml":"rule_files:\n  - /etc/prometheus/rules/*.yaml"}}' \
  -n monitoring
```

### 3. Set Up Notification Channels
```bash
# Example: Slack integration
curl -X POST \
  -H "Authorization: Bearer $GRAFANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "alloy-alerts",
    "type": "slack",
    "settings": {
      "url": "'"$SLACK_WEBHOOK_URL"'",
      "channel": "#alerts",
      "title": "Alloy Alert",
      "text": "{{ range .Alerts }}{{ .Annotations.summary }}{{ end }}"
    }
  }' \
  http://grafana:3000/api/alert-notifications
```

## 📈 Metrics Reference

### Core Metrics Collected

#### Service Health
```prometheus
# Service availability
up{job="ai-sorter|alloy|otlp"}

# Request metrics
http_requests_total{job, status, method}
http_request_duration_seconds{job, method}

# AI Sorter specific
ai_sorter_classifications_total{category}
ai_sorter_api_calls_total{status}
ai_sorter_batch_processing_duration_seconds
```

#### Resource Usage
```prometheus
# CPU and Memory
container_cpu_usage_seconds_total{pod}
container_memory_usage_bytes{pod}
kube_pod_container_resource_requests{resource, pod}

# Storage
kubelet_volume_stats_capacity_bytes{persistentvolumeclaim}
kubelet_volume_stats_used_bytes{persistentvolumeclaim}
```

#### Security Metrics
```prometheus
# Authentication
authentication_attempts_total{result}
http_requests_total{status="401|403"}

# Vulnerabilities
security_scan_findings{severity, cve_id}
compliance_check_passed{standard}
```

### Custom Metrics Implementation

Add these metrics to your application:

```python
# Python example
from prometheus_client import Counter, Histogram, Gauge

# AI Sorter metrics
CLASSIFICATIONS_TOTAL = Counter(
    'ai_sorter_classifications_total',
    'Total number of classifications',
    ['category', 'confidence_level']
)

PROCESSING_DURATION = Histogram(
    'ai_sorter_batch_processing_duration_seconds',
    'Time spent processing batches',
    ['batch_size_range']
)

ACTIVE_REQUESTS = Gauge(
    'ai_sorter_active_requests',
    'Number of currently active requests'
)
```

## 🔧 Configuration Templates

### Prometheus ServiceMonitor
```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: alloy-dynamic-processors
  namespace: monitoring
spec:
  selector:
    matchLabels:
      app: alloy-dynamic-processors
  endpoints:
  - port: metrics
    interval: 30s
    path: /metrics
```

### Grafana Provisioning
```yaml
# provisioning/dashboards/alloy.yaml
apiVersion: 1

providers:
- name: 'alloy-dashboards'
  orgId: 1
  folder: 'Alloy Dynamic Processors'
  type: file
  disableDeletion: false
  updateIntervalSeconds: 30
  options:
    path: /var/lib/grafana/dashboards/alloy
```

## 📋 Monitoring Checklist

### Initial Setup
- [ ] Prometheus configured with service discovery
- [ ] Grafana datasource connected to Prometheus
- [ ] All dashboards imported successfully
- [ ] Alert rules loaded in Prometheus
- [ ] Notification channels configured
- [ ] Test alerts are firing correctly

### Validation
- [ ] Metrics are being collected (check Prometheus targets)
- [ ] Dashboards display data correctly
- [ ] Alerts trigger as expected
- [ ] Notification channels receive alerts
- [ ] Runbook links are accessible

### Ongoing Maintenance
- [ ] Regular review of alert thresholds
- [ ] Dashboard updates for new features
- [ ] Quarterly monitoring review meetings
- [ ] Alert rule optimization based on noise

## 🎯 SLA Targets

| Service | Availability | Response Time (p95) | Error Rate |
|---------|-------------|-------------------|------------|
| AI Sorter | 99.9% | < 2000ms | < 2% |
| OTLP Ingestion | 99.95% | < 500ms | < 1% |
| Alloy Management | 99.99% | < 100ms | < 0.5% |

## 📚 Additional Resources

- [Prometheus Configuration Guide](https://prometheus.io/docs/prometheus/latest/configuration/)
- [Grafana Dashboard Best Practices](https://grafana.com/docs/grafana/latest/best-practices/)
- [Alert Manager Configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [PromQL Query Language](https://prometheus.io/docs/prometheus/latest/querying/)

## 🆘 Troubleshooting

### Common Issues

#### Metrics Not Appearing
```bash
# Check if targets are up
curl http://prometheus:9090/api/v1/targets

# Verify service endpoints
kubectl get endpoints -n monitoring

# Check pod logs
kubectl logs -l app=ai-sorter -n monitoring
```

#### Dashboards Not Loading
```bash
# Check Grafana logs
kubectl logs -l app=grafana -n monitoring

# Verify data source configuration
curl -H "Authorization: Bearer $GRAFANA_API_KEY" \
  http://grafana:3000/api/datasources
```

#### Alerts Not Firing
```bash
# Check alert rule syntax
promtool check rules monitoring/alerts/alert-rules.yaml

# Verify alert manager configuration
curl http://alertmanager:9093/api/v1/status
```

---

**Last Updated**: January 24, 2024  
**Version**: 1.9.0  
**Maintained By**: Platform Team