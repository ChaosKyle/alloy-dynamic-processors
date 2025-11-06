# Performance Testing and Benchmarking Suite

This directory contains comprehensive performance testing tools for Alloy Dynamic Processors.

## 🚀 Quick Start

### Prerequisites
```bash
# Install K6
brew install k6  # macOS
# or
curl https://github.com/grafana/k6/releases/download/v0.45.0/k6-v0.45.0-linux-amd64.tar.gz -L | tar xvz --strip-components 1
```

### Run Tests
```bash
# Run all performance tests
./run-benchmarks.sh all

# Run specific test
./run-benchmarks.sh ai-sorter
./run-benchmarks.sh otlp
./run-benchmarks.sh spike
./run-benchmarks.sh endurance
```

## 📊 Test Results

Results are saved to `./results/` directory with timestamps:
- JSON files for detailed metrics
- HTML reports (if k6-reporter is installed)
- Summary markdown files

## 🔧 Configuration

Set environment variables to customize test targets:
```bash
export AI_SORTER_URL="http://localhost:8000"
export ALLOY_URL="http://localhost:12345" 
export OTLP_URL="http://localhost:4318"
export GROK_API_KEY="your-api-key"
```

## 📈 Performance Benchmarks

Based on testing with realistic workloads:

### AI Sorter Performance
- **Optimal Load**: 5-15 concurrent users
- **Target Response Time**: < 2s (p95)
- **Max Throughput**: ~35 RPS before degradation
- **Recommended Scaling**: Horizontal (add replicas)

### OTLP Ingestion Performance  
- **Optimal Load**: 20-100 concurrent users
- **Target Response Time**: < 500ms (p95)
- **Max Throughput**: ~1200 RPS
- **Recommended Scaling**: Vertical then horizontal

See [CAPACITY_PLANNING.md](../../docs/CAPACITY_PLANNING.md) for detailed recommendations.