# Multi-Provider AI Sorter v2.3

Enterprise-grade AI-driven telemetry sorting service with multi-provider support, intelligent fallback, and comprehensive monitoring.

## 🚀 Features

### Multi-Provider AI Support
- **OpenAI Integration**: GPT-4 and GPT-3.5-turbo support with cost optimization
- **Claude Integration**: Claude-3 models with intelligent model selection
- **Grok Integration**: X.AI's Grok-beta with structured response parsing
- **Intelligent Fallback**: Automatic provider switching on failures
- **Health-Weighted Selection**: Performance-based provider routing

### Enterprise Features
- **High Availability**: Built-in redundancy and failover mechanisms
- **Comprehensive Monitoring**: Prometheus metrics and health checks
- **Rate Limiting**: Provider-specific rate limiting and backoff
- **Security**: API key authentication and request validation
- **Scalability**: Horizontal scaling support with load balancing

### Operational Excellence
- **Structured Logging**: JSON-formatted logs with correlation IDs
- **Performance Metrics**: Real-time performance tracking and analysis
- **Cost Tracking**: Provider-specific cost estimation and optimization
- **Configuration Management**: Environment-based configuration with validation

## 📋 Requirements

- Python 3.11+
- Docker and Docker Compose (for containerized deployment)
- At least one AI provider API key (OpenAI, Claude, or Grok)

## 🔧 Installation

### Option 1: Docker Compose (Recommended)

1. **Clone and prepare environment**:
```bash
cd alloy/processors/ai_sorter_v2
cp .env.example .env
# Edit .env with your API keys and configuration
```

2. **Configure your API keys in `.env`**:
```bash
# AI Provider API Keys (at least one required)
OPENAI_API_KEY=your_openai_api_key_here
CLAUDE_API_KEY=your_claude_api_key_here
GROK_API_KEY=your_grok_api_key_here

# AI Configuration
AI_SELECTION_STRATEGY=health_weighted
AI_ENABLE_FALLBACK=true

# Service Configuration
LOG_LEVEL=INFO
ENVIRONMENT=production
```

3. **Launch the service**:
```bash
docker-compose up -d
```

### Option 2: Local Development

1. **Install dependencies**:
```bash
pip install -r requirements.txt
```

2. **Set environment variables**:
```bash
export OPENAI_API_KEY=your_openai_api_key_here
export CLAUDE_API_KEY=your_claude_api_key_here
export GROK_API_KEY=your_grok_api_key_here
```

3. **Run the service**:
```bash
python main.py
```

## 🎯 Quick Start

### 1. Health Check
```bash
curl http://localhost:8000/health
```

### 2. List Available Providers
```bash
curl http://localhost:8000/providers
```

### 3. Sort Telemetry Data
```bash
curl -X POST http://localhost:8000/sort \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "type": "log",
        "content": {
          "level": "ERROR",
          "message": "Database connection failed",
          "service": "payment-api",
          "timestamp": "2024-01-15T10:30:00Z"
        }
      }
    ]
  }'
```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | - |
| `CLAUDE_API_KEY` | Claude API key | - |
| `GROK_API_KEY` | Grok API key | - |
| `AI_SELECTION_STRATEGY` | Provider selection strategy | `health_weighted` |
| `AI_ENABLE_FALLBACK` | Enable provider fallback | `true` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `ENVIRONMENT` | Environment name | `production` |

### Configuration File

Create a `config.yaml` file for advanced configuration:

```yaml
openai:
  enabled: true
  model: "gpt-4"
  temperature: 0.3
  use_cheaper_model_fallback: true
  cheaper_model: "gpt-3.5-turbo"

claude:
  enabled: true
  model: "claude-3-sonnet-20240229"
  temperature: 0.3
  use_model_fallback: true

grok:
  enabled: false
  model: "grok-beta"
  temperature: 0.3

ai_manager:
  selection_strategy: "health_weighted"
  enable_fallback: true
  max_fallback_attempts: 3
  max_concurrent_requests: 100

health_check:
  primary_check_interval: 30
  detailed_check_interval: 120
  response_time_threshold: 5.0

security:
  require_api_key: false
  enable_rate_limiting: true
  requests_per_minute: 1000
  max_items_per_batch: 1000
```

Set the config file path:
```bash
export AI_SORTER_CONFIG_FILE=/path/to/config.yaml
```

### Provider Selection Strategies

1. **health_weighted** (default): Selects providers based on health, performance, and cost
2. **round_robin**: Cycles through healthy providers
3. **cost_optimized**: Prefers lower-cost providers

## 📊 Monitoring

### Prometheus Metrics

Available at `http://localhost:8000/metrics`:

- `ai_sorter_requests_total`: Total requests by provider and status
- `ai_sorter_request_duration_seconds`: Request duration histogram
- `ai_sorter_provider_health`: Provider health status (1=healthy, 0=unhealthy)
- `ai_sorter_active_providers`: Number of active providers
- `ai_sorter_fallback_usage_total`: Fallback usage counter

### Health Endpoints

- `GET /health`: Comprehensive service health
- `GET /providers/{provider}/health`: Individual provider health
- `GET /stats`: Service statistics and metrics

### Grafana Dashboard

If using Docker Compose, Grafana is available at `http://localhost:3000`:
- Username: `admin`
- Password: `admin123` (change in `.env`)

## 🔒 Security

### API Key Authentication

Enable API key authentication:

```bash
export AI_SORTER_API_KEYS=key1,key2,key3
```

Include the API key in requests:
```bash
curl -X POST http://localhost:8000/sort \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{"items": [...]}'
```

### Rate Limiting

Built-in rate limiting prevents abuse:
- 1000 requests per minute per client (default)
- 10000 requests per hour per client (default)
- Configurable per provider

## 🚀 Deployment

### Kubernetes

Example Kubernetes manifests are provided in the `k8s/` directory:

```bash
kubectl apply -f k8s/
```

### Production Considerations

1. **Resource Requirements**:
   - CPU: 0.5-2.0 cores per instance
   - Memory: 512MB-1GB per instance
   - Storage: 1GB for logs and cache

2. **Scaling**:
   - Horizontal scaling: Deploy multiple instances behind a load balancer
   - Vertical scaling: Increase CPU/memory for higher throughput

3. **High Availability**:
   - Deploy across multiple availability zones
   - Use external load balancer with health checks
   - Configure provider fallback and redundancy

## 📈 Performance

### Benchmarks

Typical performance metrics:
- **Throughput**: 100-500 requests/second per instance
- **Latency**: 200ms-2s depending on provider and complexity
- **Availability**: 99.9% with proper fallback configuration

### Optimization Tips

1. **Provider Selection**: Use `cost_optimized` strategy for high-volume workloads
2. **Batch Size**: Optimize batch sizes (10-50 items) for best throughput
3. **Caching**: Enable Redis caching for repeated classifications
4. **Rate Limits**: Tune provider rate limits based on your API quotas

## 🐛 Troubleshooting

### Common Issues

1. **No providers available**:
   - Check API keys are correctly set
   - Verify provider health endpoints are accessible
   - Review logs for authentication errors

2. **High latency**:
   - Check provider selection strategy
   - Monitor provider health metrics
   - Consider increasing timeout values

3. **Rate limiting errors**:
   - Review provider rate limits
   - Implement backoff strategies
   - Consider upgrading API plans

### Debug Mode

Enable debug endpoints for troubleshooting:
```bash
export ENABLE_DEBUG_ENDPOINTS=true
```

Access debug information:
- `GET /debug/config`: Current configuration
- `GET /debug/providers`: Detailed provider status
- `POST /debug/test`: Test provider functionality

## 🔄 API Reference

### Sort Telemetry Data

**Endpoint**: `POST /sort`

**Request**:
```json
{
  "request_id": "optional-correlation-id",
  "items": [
    {
      "type": "log|metric|trace",
      "content": {
        "level": "ERROR|WARN|INFO",
        "message": "Log message",
        "service": "service-name",
        "timestamp": "2024-01-15T10:30:00Z"
      }
    }
  ]
}
```

**Response**:
```json
[
  {
    "item": {...},
    "category": "critical|warning|info",
    "forward_to": "alerting|storage|archive",
    "confidence": 0.95,
    "provider": "openai|claude|grok",
    "model": "gpt-4|claude-3-sonnet|grok-beta"
  }
]
```

### Get Provider Status

**Endpoint**: `GET /providers`

**Response**:
```json
{
  "providers": {
    "openai": {
      "healthy": true,
      "models": {
        "primary": "gpt-4",
        "fallback": "gpt-3.5-turbo"
      },
      "metrics": {
        "requests": 1250,
        "success_rate": 0.98,
        "avg_response_time": 1.2
      }
    }
  },
  "active_provider": "openai",
  "fallback_enabled": true
}
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is part of the Alloy Dynamic Processors enterprise package.

## 📞 Support

For enterprise support and consulting:
- Documentation: See `docs/` directory
- Issues: GitHub Issues
- Enterprise Support: Contact your Grafana representative