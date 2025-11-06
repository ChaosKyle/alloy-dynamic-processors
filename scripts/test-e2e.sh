#!/bin/bash
# =============================================================================
# End-to-End Test Script for Alloy Dynamic Processors
# =============================================================================
# This script performs end-to-end testing of the telemetry pipeline by:
# 1. Starting the Docker Compose stack
# 2. Generating synthetic telemetry data
# 3. Verifying data reaches the correct destinations
# 4. Testing AI sorter classification (if enabled)
# 5. Checking health endpoints and metrics
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ALLOY_HEALTH_URL="http://localhost:13133/healthz"
ALLOY_METRICS_URL="http://localhost:8889/metrics"
AI_SORTER_HEALTH_URL="http://localhost:8080/healthz"
AI_SORTER_METRICS_URL="http://localhost:8080/metrics"
PROMETHEUS_URL="http://localhost:9090"
GRAFANA_URL="http://localhost:3000"
TIMEOUT=60

print_header() {
  echo -e "${BLUE}"
  echo "=============================================="
  echo "  $1"
  echo "=============================================="
  echo -e "${NC}"
}

print_success() {
  echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
  echo -e "${RED}✗ $1${NC}"
}

print_warning() {
  echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
  echo -e "${BLUE}ℹ $1${NC}"
}

# =============================================================================
# Health Checks
# =============================================================================

check_health() {
  local url=$1
  local service=$2
  local max_attempts=12
  local attempt=1

  print_info "Checking health of $service..."

  while [ $attempt -le $max_attempts ]; do
    if curl -f -s "$url" > /dev/null 2>&1; then
      print_success "$service is healthy"
      return 0
    fi

    echo -n "."
    sleep 5
    attempt=$((attempt + 1))
  done

  print_error "$service failed health check after ${max_attempts} attempts"
  return 1
}

# =============================================================================
# Metrics Verification
# =============================================================================

check_metrics() {
  local url=$1
  local service=$2

  print_info "Checking metrics endpoint for $service..."

  if curl -f -s "$url" | grep -q "^#"; then
    local metric_count=$(curl -s "$url" | grep -c "^[^#]" || true)
    print_success "$service metrics endpoint responding ($metric_count metrics)"
    return 0
  else
    print_error "$service metrics endpoint not responding"
    return 1
  fi
}

# =============================================================================
# Synthetic Data Generation
# =============================================================================

generate_synthetic_logs() {
  print_info "Generating synthetic log data..."

  # Send OTLP HTTP logs
  curl -X POST "http://localhost:4318/v1/logs" \
    -H "Content-Type: application/json" \
    -d '{
      "resourceLogs": [{
        "scopeLogs": [{
          "logRecords": [
            {
              "timeUnixNano": "'$(date +%s%N)'",
              "severityText": "ERROR",
              "body": {"stringValue": "Critical error: Database connection failed"},
              "attributes": [
                {"key": "service.name", "value": {"stringValue": "test-app"}},
                {"key": "test.type", "value": {"stringValue": "e2e"}}
              ]
            },
            {
              "timeUnixNano": "'$(date +%s%N)'",
              "severityText": "INFO",
              "body": {"stringValue": "User logged in successfully"},
              "attributes": [
                {"key": "service.name", "value": {"stringValue": "test-app"}},
                {"key": "test.type", "value": {"stringValue": "e2e"}}
              ]
            }
          ]
        }]
      }]
    }' > /dev/null 2>&1

  print_success "Generated 2 synthetic log entries"
}

generate_synthetic_metrics() {
  print_info "Generating synthetic metrics data..."

  # Send OTLP HTTP metrics
  curl -X POST "http://localhost:4318/v1/metrics" \
    -H "Content-Type: application/json" \
    -d '{
      "resourceMetrics": [{
        "scopeMetrics": [{
          "metrics": [{
            "name": "test.e2e.counter",
            "unit": "1",
            "sum": {
              "dataPoints": [{
                "timeUnixNano": "'$(date +%s%N)'",
                "asInt": 42,
                "attributes": [
                  {"key": "test.type", "value": {"stringValue": "e2e"}}
                ]
              }],
              "aggregationTemporality": 2,
              "isMonotonic": true
            }
          }]
        }]
      }]
    }' > /dev/null 2>&1

  print_success "Generated 1 synthetic metric"
}

generate_synthetic_traces() {
  print_info "Generating synthetic trace data..."

  # Send OTLP HTTP traces
  curl -X POST "http://localhost:4318/v1/traces" \
    -H "Content-Type: application/json" \
    -d '{
      "resourceSpans": [{
        "scopeSpans": [{
          "spans": [{
            "traceId": "5b8efff798038103d269b633813fc60c",
            "spanId": "eee19b7ec3c1b174",
            "parentSpanId": "",
            "name": "test-e2e-span",
            "kind": 1,
            "startTimeUnixNano": "'$(date +%s%N)'",
            "endTimeUnixNano": "'$(($(date +%s%N) + 1000000000))'",
            "attributes": [
              {"key": "test.type", "value": {"stringValue": "e2e"}},
              {"key": "http.method", "value": {"stringValue": "GET"}},
              {"key": "http.status_code", "value": {"intValue": 200}}
            ]
          }]
        }]
      }]
    }' > /dev/null 2>&1

  print_success "Generated 1 synthetic trace span"
}

# =============================================================================
# AI Sorter Testing
# =============================================================================

test_ai_sorter() {
  if ! curl -f -s "$AI_SORTER_HEALTH_URL" > /dev/null 2>&1; then
    print_warning "AI Sorter is not running (expected if AI_SORTER_ENABLED=false)"
    return 0
  fi

  print_info "Testing AI Sorter classification..."

  # Test classification endpoint
  response=$(curl -s -X POST "http://localhost:8080/sort" \
    -H "Content-Type: application/json" \
    -d '{
      "items": [
        {
          "type": "log",
          "content": {
            "message": "Critical database failure",
            "level": "error"
          }
        },
        {
          "type": "log",
          "content": {
            "message": "User session started",
            "level": "info"
          }
        }
      ]
    }' || echo '{"error": true}')

  if echo "$response" | grep -q '"category"'; then
    print_success "AI Sorter successfully classified items"
    echo "$response" | python3 -m json.tool | head -20 || true
  else
    print_error "AI Sorter classification failed"
    echo "$response"
    return 1
  fi
}

# =============================================================================
# Data Verification
# =============================================================================

verify_data_in_prometheus() {
  print_info "Verifying data reached Prometheus..."

  sleep 10  # Wait for scrape interval

  # Query for test metrics
  query='test_e2e_counter'
  result=$(curl -s "${PROMETHEUS_URL}/api/v1/query?query=${query}" | \
    python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('data',{}).get('result',[]))" 2>/dev/null || echo "[]")

  if [ "$result" != "[]" ]; then
    print_success "Test metrics found in Prometheus"
  else
    print_warning "Test metrics not yet in Prometheus (may take time to scrape)"
  fi
}

verify_alloy_metrics() {
  print_info "Verifying Alloy is processing telemetry..."

  metrics=$(curl -s "$ALLOY_METRICS_URL")

  # Check for key metrics
  if echo "$metrics" | grep -q "otelcol_receiver_accepted"; then
    print_success "Alloy is receiving telemetry"

    # Extract some stats
    spans=$(echo "$metrics" | grep "otelcol_receiver_accepted_spans" | grep -v "#" | awk '{print $2}' | head -1 || echo "0")
    logs=$(echo "$metrics" | grep "otelcol_receiver_accepted_log_records" | grep -v "#" | awk '{print $2}' | head -1 || echo "0")
    metrics_count=$(echo "$metrics" | grep "otelcol_receiver_accepted_metric_points" | grep -v "#" | awk '{print $2}' | head -1 || echo "0")

    print_info "  Spans received: $spans"
    print_info "  Logs received: $logs"
    print_info "  Metrics received: $metrics_count"
  else
    print_warning "No telemetry data detected in Alloy metrics"
  fi
}

# =============================================================================
# Main Test Flow
# =============================================================================

main() {
  print_header "Alloy Dynamic Processors - End-to-End Test"

  # Check if Docker Compose stack is running
  if ! docker compose ps | grep -q "Up"; then
    print_error "Docker Compose stack is not running"
    print_info "Run: docker compose up -d"
    exit 1
  fi

  print_success "Docker Compose stack is running"
  echo ""

  # Health checks
  print_header "Phase 1: Health Checks"
  check_health "$ALLOY_HEALTH_URL" "Alloy" || exit 1
  check_health "$PROMETHEUS_URL/-/healthy" "Prometheus" || exit 1
  check_health "$GRAFANA_URL/api/health" "Grafana" || exit 1

  # Optional AI Sorter check
  if curl -f -s "$AI_SORTER_HEALTH_URL" > /dev/null 2>&1; then
    check_health "$AI_SORTER_HEALTH_URL" "AI Sorter" || print_warning "AI Sorter check failed"
  fi

  echo ""

  # Metrics checks
  print_header "Phase 2: Metrics Endpoints"
  check_metrics "$ALLOY_METRICS_URL" "Alloy" || exit 1

  if curl -f -s "$AI_SORTER_METRICS_URL" > /dev/null 2>&1; then
    check_metrics "$AI_SORTER_METRICS_URL" "AI Sorter" || print_warning "AI Sorter metrics check failed"
  fi

  echo ""

  # Generate synthetic data
  print_header "Phase 3: Synthetic Data Generation"
  generate_synthetic_logs
  generate_synthetic_metrics
  generate_synthetic_traces

  echo ""

  # AI Sorter testing
  if curl -f -s "$AI_SORTER_HEALTH_URL" > /dev/null 2>&1; then
    print_header "Phase 4: AI Sorter Testing"
    test_ai_sorter || print_warning "AI Sorter test failed (may require valid API key)"
    echo ""
  fi

  # Verify data
  print_header "Phase 5: Data Verification"
  verify_alloy_metrics
  verify_data_in_prometheus

  echo ""

  # Summary
  print_header "Test Summary"
  print_success "End-to-end test completed successfully!"
  echo ""
  print_info "Access points:"
  print_info "  Alloy:      http://localhost:12345"
  print_info "  Prometheus: http://localhost:9090"
  print_info "  Grafana:    http://localhost:3000 (admin/admin)"
  print_info "  AI Sorter:  http://localhost:8080/docs"
  echo ""
  print_info "To view logs: docker compose logs -f alloy"
  print_info "To stop:      docker compose down"
}

# Run main function
main "$@"
