#!/bin/bash

# Alloy Dynamic Processors Performance Benchmarking Suite
# This script runs comprehensive performance tests using K6

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Default URLs
AI_SORTER_URL="${AI_SORTER_URL:-http://localhost:8000}"
ALLOY_URL="${ALLOY_URL:-http://localhost:12345}"
OTLP_URL="${OTLP_URL:-http://localhost:4318}"

# Check if K6 is installed
check_k6() {
    if ! command -v k6 &> /dev/null; then
        echo -e "${RED}❌ K6 is not installed. Please install it first:${NC}"
        echo "   macOS: brew install k6"
        echo "   Linux: sudo gpg -k && sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69"
        echo "         echo 'deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main' | sudo tee /etc/apt/sources.list.d/k6.list"
        echo "         sudo apt-get update && sudo apt-get install k6"
        echo "   Windows: winget install k6"
        exit 1
    fi
}

# Print banner
print_banner() {
    echo -e "${BLUE}"
    echo "======================================================"
    echo "    Alloy Dynamic Processors Performance Testing"
    echo "======================================================"
    echo -e "${NC}"
    echo "📊 AI Sorter URL:    ${AI_SORTER_URL}"
    echo "⚙️  Alloy URL:        ${ALLOY_URL}"
    echo "📡 OTLP URL:         ${OTLP_URL}"
    echo "🔑 API Key:          ${GROK_API_KEY:+Configured}"
    echo "📁 Results Dir:      ${RESULTS_DIR}"
    echo ""
}

# Create results directory
setup_results_dir() {
    mkdir -p "${RESULTS_DIR}"
    echo -e "${GREEN}✅ Results directory created: ${RESULTS_DIR}${NC}"
}

# Health check services
health_check() {
    echo -e "${YELLOW}🔍 Performing health checks...${NC}"
    
    # Check AI Sorter
    if curl -s --max-time 5 "${AI_SORTER_URL}/health" > /dev/null; then
        echo -e "${GREEN}✅ AI Sorter is healthy${NC}"
    else
        echo -e "${RED}❌ AI Sorter health check failed${NC}"
        echo "   Make sure the service is running at ${AI_SORTER_URL}"
    fi
    
    # Check Alloy
    if curl -s --max-time 5 "${ALLOY_URL}/-/healthy" > /dev/null; then
        echo -e "${GREEN}✅ Alloy is healthy${NC}"
    else
        echo -e "${RED}❌ Alloy health check failed${NC}"
        echo "   Make sure the service is running at ${ALLOY_URL}"
    fi
    
    # Check OTLP endpoint
    if curl -s --max-time 5 -X POST "${OTLP_URL}/v1/traces" \
        -H "Content-Type: application/json" \
        -d '{"resourceSpans":[]}' > /dev/null; then
        echo -e "${GREEN}✅ OTLP endpoint is responding${NC}"
    else
        echo -e "${RED}❌ OTLP endpoint check failed${NC}"
        echo "   Make sure the service is running at ${OTLP_URL}"
    fi
    
    echo ""
}

# Run K6 test with specific configuration
run_k6_test() {
    local test_name="$1"
    local test_file="$2"
    local additional_options="$3"
    
    echo -e "${BLUE}🚀 Running ${test_name} test...${NC}"
    
    local output_file="${RESULTS_DIR}/${test_name}_${TIMESTAMP}.json"
    local html_file="${RESULTS_DIR}/${test_name}_${TIMESTAMP}.html"
    
    # Set environment variables for K6
    export AI_SORTER_URL
    export ALLOY_URL
    export OTLP_URL
    export GROK_API_KEY
    
    # Run K6 with JSON output
    if k6 run \
        --out json="${output_file}" \
        ${additional_options} \
        "${test_file}"; then
        
        echo -e "${GREEN}✅ ${test_name} test completed successfully${NC}"
        echo "📄 Results saved to: ${output_file}"
        
        # Generate HTML report if available
        if command -v k6-reporter &> /dev/null; then
            k6-reporter "${output_file}" --output "${html_file}"
            echo "📊 HTML report: ${html_file}"
        fi
        
    else
        echo -e "${RED}❌ ${test_name} test failed${NC}"
        return 1
    fi
    
    echo ""
}

# Run specific test scenarios
run_ai_sorter_test() {
    cat > "${SCRIPT_DIR}/ai-sorter-test.js" << 'EOF'
import { testAiSorter, setup, teardown } from './k6-load-test.js';

export { setup, teardown };

export const options = {
  scenarios: {
    ai_sorter_load: {
      executor: 'ramping-vus',
      exec: 'testAiSorter',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 5 },   // Ramp up
        { duration: '2m', target: 5 },    // Sustain
        { duration: '30s', target: 15 },  // Increase load
        { duration: '2m', target: 15 },   // Sustain higher load
        { duration: '30s', target: 0 },   // Ramp down
      ],
    },
  },
  thresholds: {
    'http_req_duration': ['p(95)<3000'],
    'http_req_failed': ['rate<0.05'],
  },
};

export { testAiSorter };
EOF
    
    run_k6_test "ai-sorter" "${SCRIPT_DIR}/ai-sorter-test.js"
    rm -f "${SCRIPT_DIR}/ai-sorter-test.js"
}

run_otlp_test() {
    cat > "${SCRIPT_DIR}/otlp-test.js" << 'EOF'
import { testOtlpIngestion, setup, teardown } from './k6-load-test.js';

export { setup, teardown };

export const options = {
  scenarios: {
    otlp_load: {
      executor: 'ramping-vus',
      exec: 'testOtlpIngestion',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 20 },  // Ramp up
        { duration: '3m', target: 20 },   // Sustain
        { duration: '30s', target: 50 },  // High load
        { duration: '2m', target: 50 },   // Sustain high load
        { duration: '30s', target: 0 },   // Ramp down
      ],
    },
  },
  thresholds: {
    'http_req_duration': ['p(95)<1000'],
    'http_req_failed': ['rate<0.02'],
  },
};

export { testOtlpIngestion };
EOF
    
    run_k6_test "otlp" "${SCRIPT_DIR}/otlp-test.js"
    rm -f "${SCRIPT_DIR}/otlp-test.js"
}

run_spike_test() {
    cat > "${SCRIPT_DIR}/spike-test.js" << 'EOF'
import { testAiSorter, testOtlpIngestion, setup, teardown } from './k6-load-test.js';

export { setup, teardown };

export const options = {
  scenarios: {
    spike_test: {
      executor: 'ramping-vus',
      exec: 'spikeTest',
      startVUs: 0,
      stages: [
        { duration: '10s', target: 5 },   // Normal load
        { duration: '10s', target: 100 }, // Spike!
        { duration: '30s', target: 100 }, // Sustain spike
        { duration: '10s', target: 5 },   // Back to normal
        { duration: '30s', target: 5 },   // Sustain normal
      ],
    },
  },
  thresholds: {
    'http_req_duration': ['p(95)<5000'], // More lenient during spike
    'http_req_failed': ['rate<0.1'],     // Allow higher error rate
  },
};

export function spikeTest() {
  // Alternate between AI Sorter and OTLP tests
  if (Math.random() < 0.6) {
    testAiSorter();
  } else {
    testOtlpIngestion();
  }
}
EOF
    
    run_k6_test "spike" "${SCRIPT_DIR}/spike-test.js"
    rm -f "${SCRIPT_DIR}/spike-test.js"
}

run_endurance_test() {
    cat > "${SCRIPT_DIR}/endurance-test.js" << 'EOF'
import { testAiSorter, testOtlpIngestion, testAlloyHealth, setup, teardown } from './k6-load-test.js';

export { setup, teardown };

export const options = {
  scenarios: {
    endurance: {
      executor: 'constant-vus',
      exec: 'enduranceTest',
      vus: 10,
      duration: '10m', // Long running test
    },
  },
  thresholds: {
    'http_req_duration': ['p(95)<2000'],
    'http_req_failed': ['rate<0.03'],
  },
};

export function enduranceTest() {
  const rand = Math.random();
  if (rand < 0.5) {
    testAiSorter();
  } else if (rand < 0.8) {
    testOtlpIngestion();
  } else {
    testAlloyHealth();
  }
}
EOF
    
    run_k6_test "endurance" "${SCRIPT_DIR}/endurance-test.js"
    rm -f "${SCRIPT_DIR}/endurance-test.js"
}

# Generate summary report
generate_summary() {
    echo -e "${BLUE}📊 Generating performance summary...${NC}"
    
    local summary_file="${RESULTS_DIR}/performance_summary_${TIMESTAMP}.md"
    
    cat > "${summary_file}" << EOF
# Alloy Dynamic Processors Performance Test Summary

**Test Date:** $(date)
**Test Environment:**
- AI Sorter URL: ${AI_SORTER_URL}
- Alloy URL: ${ALLOY_URL}
- OTLP URL: ${OTLP_URL}

## Test Results

### Files Generated
EOF
    
    # List all result files
    for file in "${RESULTS_DIR}"/*_${TIMESTAMP}.*; do
        if [[ -f "$file" ]]; then
            echo "- $(basename "$file")" >> "${summary_file}"
        fi
    done
    
    cat >> "${summary_file}" << EOF

## Quick Analysis

To analyze the results, use:

\`\`\`bash
# View K6 results
k6 run --summary-export=summary.json your-test.js

# Or analyze JSON output with jq
jq '.metrics' results.json
\`\`\`

## Performance Recommendations

Based on the test results:

1. **AI Sorter Performance**
   - Monitor response times under load
   - Consider horizontal scaling if p95 > 2s
   - Implement circuit breakers for AI API calls

2. **OTLP Ingestion Performance**
   - Batch size optimization may be needed
   - Monitor memory usage during high throughput
   - Consider async processing for large payloads

3. **Resource Planning**
   - CPU: Monitor during sustained load
   - Memory: Watch for memory leaks in long-running tests
   - Network: Ensure adequate bandwidth for data ingestion

EOF
    
    echo -e "${GREEN}✅ Summary generated: ${summary_file}${NC}"
}

# Main function
main() {
    local test_type="${1:-all}"
    
    print_banner
    check_k6
    setup_results_dir
    health_check
    
    case "$test_type" in
        "ai-sorter")
            run_ai_sorter_test
            ;;
        "otlp")
            run_otlp_test
            ;;
        "spike")
            run_spike_test
            ;;
        "endurance")
            run_endurance_test
            ;;
        "all")
            echo -e "${YELLOW}🎯 Running comprehensive test suite...${NC}"
            run_ai_sorter_test
            run_otlp_test
            run_spike_test
            # Skip endurance test in 'all' mode (too long)
            echo -e "${YELLOW}ℹ️  Skipping endurance test (use './run-benchmarks.sh endurance' to run separately)${NC}"
            ;;
        *)
            echo -e "${RED}❌ Unknown test type: $test_type${NC}"
            echo "Usage: $0 [ai-sorter|otlp|spike|endurance|all]"
            exit 1
            ;;
    esac
    
    generate_summary
    
    echo -e "${GREEN}🎉 Performance testing completed!${NC}"
    echo -e "${BLUE}📁 Check results in: ${RESULTS_DIR}${NC}"
}

# Handle script arguments
main "$@"