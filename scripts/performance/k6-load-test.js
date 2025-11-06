import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const aiSorterErrors = new Rate('ai_sorter_errors');
const otlpErrors = new Rate('otlp_errors');
const alloyErrors = new Rate('alloy_errors');
const aiSorterResponseTime = new Trend('ai_sorter_response_time');
const otlpResponseTime = new Trend('otlp_response_time');
const alloyResponseTime = new Trend('alloy_response_time');
const totalRequests = new Counter('total_requests');

// Configuration
const AI_SORTER_URL = __ENV.AI_SORTER_URL || 'http://localhost:8000';
const ALLOY_URL = __ENV.ALLOY_URL || 'http://localhost:12345';
const OTLP_URL = __ENV.OTLP_URL || 'http://localhost:4318';
const API_KEY = __ENV.GROK_API_KEY || '';

// Test scenarios
export const options = {
  scenarios: {
    // AI Sorter load test
    ai_sorter_load: {
      executor: 'ramping-vus',
      exec: 'testAiSorter',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 10 },  // Ramp up
        { duration: '2m', target: 10 },   // Stay at 10 users
        { duration: '30s', target: 20 },  // Ramp up to 20
        { duration: '2m', target: 20 },   // Stay at 20 users
        { duration: '30s', target: 0 },   // Ramp down
      ],
    },
    
    // OTLP ingestion load test
    otlp_load: {
      executor: 'ramping-vus',
      exec: 'testOtlpIngestion',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 20 },  // Ramp up
        { duration: '3m', target: 20 },   // Stay at 20 users
        { duration: '30s', target: 50 },  // Ramp up to 50
        { duration: '2m', target: 50 },   // Stay at 50 users
        { duration: '30s', target: 0 },   // Ramp down
      ],
    },
    
    // Alloy management endpoints
    alloy_health: {
      executor: 'constant-vus',
      exec: 'testAlloyHealth',
      vus: 5,
      duration: '6m',
    },
    
    // Spike test for AI Sorter
    ai_sorter_spike: {
      executor: 'ramping-vus',
      exec: 'testAiSorter',
      startVUs: 0,
      stages: [
        { duration: '10s', target: 50 },  // Fast ramp up
        { duration: '30s', target: 50 },  // Stay high
        { duration: '10s', target: 0 },   // Fast ramp down
      ],
      startTime: '7m', // Start after other tests
    },
  },
  
  thresholds: {
    // AI Sorter thresholds
    'ai_sorter_response_time': ['p(95)<2000'], // 95% under 2s
    'ai_sorter_errors': ['rate<0.05'],         // Error rate under 5%
    
    // OTLP thresholds
    'otlp_response_time': ['p(95)<500'],       // 95% under 0.5s
    'otlp_errors': ['rate<0.01'],              // Error rate under 1%
    
    // Alloy thresholds
    'alloy_response_time': ['p(95)<100'],      // 95% under 0.1s
    'alloy_errors': ['rate<0.01'],             // Error rate under 1%
    
    // Overall thresholds
    'http_req_duration': ['p(95)<1000'],       // 95% under 1s
    'http_req_failed': ['rate<0.02'],          // Overall error rate under 2%
  },
};

// Generate realistic telemetry data
function generateTelemetryBatch(size = 10) {
  const items = [];
  const types = ['trace', 'metric', 'log', 'error', 'event'];
  const services = ['user-service', 'payment-service', 'api-gateway', 'database', 'cache'];
  
  for (let i = 0; i < size; i++) {
    const type = types[Math.floor(Math.random() * types.length)];
    const service = services[Math.floor(Math.random() * services.length)];
    
    let content = {};
    
    switch (type) {
      case 'error':
        content = {
          message: `Error in ${service}: Connection timeout`,
          severity: ['low', 'medium', 'high', 'critical'][Math.floor(Math.random() * 4)],
          service: service,
          timestamp: new Date().toISOString(),
          error_code: Math.floor(Math.random() * 200) + 400
        };
        break;
        
      case 'metric':
        content = {
          name: ['cpu_usage', 'memory_usage', 'disk_io', 'network_latency'][Math.floor(Math.random() * 4)],
          value: Math.round(Math.random() * 100 * 100) / 100,
          unit: ['percent', 'bytes', 'milliseconds'][Math.floor(Math.random() * 3)],
          service: service,
          host: `host-${Math.floor(Math.random() * 10) + 1}`
        };
        break;
        
      case 'trace':
        content = {
          span_name: `${service}_request`,
          duration_ms: Math.floor(Math.random() * 5000) + 10,
          status: ['ok', 'error', 'timeout'][Math.floor(Math.random() * 3)],
          service: service,
          trace_id: `trace-${Math.floor(Math.random() * 900000) + 100000}`
        };
        break;
        
      case 'log':
        content = {
          level: ['DEBUG', 'INFO', 'WARN', 'ERROR'][Math.floor(Math.random() * 4)],
          message: `Operation completed in ${service}`,
          service: service,
          timestamp: new Date().toISOString()
        };
        break;
        
      case 'event':
        content = {
          event_type: ['user_login', 'payment_processed', 'api_call'][Math.floor(Math.random() * 3)],
          service: service,
          user_id: `user-${Math.floor(Math.random() * 9000) + 1000}`,
          timestamp: new Date().toISOString()
        };
        break;
    }
    
    items.push({ type, content });
  }
  
  return { items };
}

// Generate OTLP traces payload
function generateOtlpTraces() {
  const traceId = Math.floor(Math.random() * 1e16).toString(16).padStart(32, '0');
  const spanCount = Math.floor(Math.random() * 5) + 1;
  
  const spans = [];
  for (let i = 0; i < spanCount; i++) {
    spans.push({
      traceId: traceId,
      spanId: Math.floor(Math.random() * 1e8).toString(16).padStart(16, '0'),
      name: `test-span-${i}`,
      startTimeUnixNano: (Date.now() * 1000000).toString(),
      endTimeUnixNano: ((Date.now() + Math.random() * 1000) * 1000000).toString(),
      attributes: [
        {
          key: 'http.method',
          value: { stringValue: ['GET', 'POST', 'PUT', 'DELETE'][Math.floor(Math.random() * 4)] }
        },
        {
          key: 'http.status_code',
          value: { intValue: Math.floor(Math.random() * 200) + 200 }
        }
      ]
    });
  }
  
  return {
    resourceSpans: [
      {
        resource: {
          attributes: [
            {
              key: 'service.name',
              value: { stringValue: `test-service-${Math.floor(Math.random() * 5) + 1}` }
            },
            {
              key: 'service.version',
              value: { stringValue: '1.0.0' }
            }
          ]
        },
        scopeSpans: [{ spans }]
      }
    ]
  };
}

// Test AI Sorter endpoints
export function testAiSorter() {
  totalRequests.add(1);
  
  // 10% health checks, 90% classification requests
  if (Math.random() < 0.1) {
    // Health check
    const response = http.get(`${AI_SORTER_URL}/health`);
    
    check(response, {
      'AI Sorter health status is 200': (r) => r.status === 200,
      'AI Sorter health response contains status': (r) => JSON.parse(r.body).status === 'healthy',
    });
    
    aiSorterErrors.add(response.status !== 200);
    aiSorterResponseTime.add(response.timings.duration);
    
  } else {
    // Classification request
    const payload = generateTelemetryBatch(Math.floor(Math.random() * 20) + 5);
    
    const params = {
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY,
      },
    };
    
    const response = http.post(`${AI_SORTER_URL}/sort`, JSON.stringify(payload), params);
    
    const checksResult = check(response, {
      'AI Sorter classification status is 200': (r) => r.status === 200,
      'AI Sorter response is valid JSON': (r) => {
        try {
          JSON.parse(r.body);
          return true;
        } catch {
          return false;
        }
      },
      'AI Sorter response contains sorted items': (r) => {
        if (r.status === 200) {
          const data = JSON.parse(r.body);
          return Array.isArray(data) && data.length > 0;
        }
        return false;
      },
    });
    
    aiSorterErrors.add(response.status !== 200);
    aiSorterResponseTime.add(response.timings.duration);
    
    // Log errors for debugging
    if (response.status !== 200) {
      console.log(`AI Sorter error: ${response.status} - ${response.body}`);
    }
  }
  
  sleep(Math.random() * 0.5); // Random sleep 0-0.5s
}

// Test OTLP ingestion
export function testOtlpIngestion() {
  totalRequests.add(1);
  
  const payload = generateOtlpTraces();
  
  const params = {
    headers: {
      'Content-Type': 'application/json',
    },
  };
  
  const response = http.post(`${OTLP_URL}/v1/traces`, JSON.stringify(payload), params);
  
  check(response, {
    'OTLP traces status is 200': (r) => r.status === 200,
    'OTLP response time under 1s': (r) => r.timings.duration < 1000,
  });
  
  otlpErrors.add(response.status !== 200);
  otlpResponseTime.add(response.timings.duration);
  
  // Also test metrics endpoint occasionally
  if (Math.random() < 0.3) {
    const metricsPayload = {
      resourceMetrics: [
        {
          resource: {
            attributes: [
              {
                key: 'service.name',
                value: { stringValue: 'test-service' }
              }
            ]
          },
          scopeMetrics: [
            {
              metrics: [
                {
                  name: 'test_counter',
                  description: 'Test counter metric',
                  unit: '1',
                  sum: {
                    dataPoints: [
                      {
                        timeUnixNano: (Date.now() * 1000000).toString(),
                        asInt: Math.floor(Math.random() * 100)
                      }
                    ]
                  }
                }
              ]
            }
          ]
        }
      ]
    };
    
    const metricsResponse = http.post(`${OTLP_URL}/v1/metrics`, JSON.stringify(metricsPayload), params);
    check(metricsResponse, {
      'OTLP metrics status is 200': (r) => r.status === 200,
    });
    
    otlpErrors.add(metricsResponse.status !== 200);
    otlpResponseTime.add(metricsResponse.timings.duration);
  }
  
  sleep(Math.random() * 0.2); // Random sleep 0-0.2s
}

// Test Alloy health endpoints
export function testAlloyHealth() {
  totalRequests.add(1);
  
  // Test health endpoint
  const healthResponse = http.get(`${ALLOY_URL}/-/healthy`);
  
  check(healthResponse, {
    'Alloy health status is 200': (r) => r.status === 200,
    'Alloy health response time under 100ms': (r) => r.timings.duration < 100,
  });
  
  alloyErrors.add(healthResponse.status !== 200);
  alloyResponseTime.add(healthResponse.timings.duration);
  
  // Test readiness endpoint
  const readyResponse = http.get(`${ALLOY_URL}/-/ready`);
  
  check(readyResponse, {
    'Alloy ready status is 200': (r) => r.status === 200,
  });
  
  alloyErrors.add(readyResponse.status !== 200);
  alloyResponseTime.add(readyResponse.timings.duration);
  
  // Test metrics endpoint occasionally
  if (Math.random() < 0.2) {
    const metricsResponse = http.get(`${ALLOY_URL}/metrics`);
    
    check(metricsResponse, {
      'Alloy metrics status is 200': (r) => r.status === 200,
      'Alloy metrics contains prometheus data': (r) => r.body.includes('# HELP'),
    });
    
    alloyErrors.add(metricsResponse.status !== 200);
    alloyResponseTime.add(metricsResponse.timings.duration);
  }
  
  sleep(Math.random() * 1); // Random sleep 0-1s
}

// Setup function
export function setup() {
  console.log('Starting Alloy Dynamic Processors Performance Test');
  console.log(`AI Sorter URL: ${AI_SORTER_URL}`);
  console.log(`Alloy URL: ${ALLOY_URL}`);
  console.log(`OTLP URL: ${OTLP_URL}`);
  console.log(`API Key configured: ${API_KEY ? 'Yes' : 'No'}`);
  
  // Verify services are running
  const aiSorterHealth = http.get(`${AI_SORTER_URL}/health`);
  const alloyHealth = http.get(`${ALLOY_URL}/-/healthy`);
  
  if (aiSorterHealth.status !== 200) {
    console.log(`Warning: AI Sorter health check failed (${aiSorterHealth.status})`);
  }
  
  if (alloyHealth.status !== 200) {
    console.log(`Warning: Alloy health check failed (${alloyHealth.status})`);
  }
  
  return {
    aiSorterHealthy: aiSorterHealth.status === 200,
    alloyHealthy: alloyHealth.status === 200,
  };
}

// Teardown function
export function teardown(data) {
  console.log('Performance test completed');
  console.log(`AI Sorter was healthy: ${data.aiSorterHealthy}`);
  console.log(`Alloy was healthy: ${data.alloyHealthy}`);
}