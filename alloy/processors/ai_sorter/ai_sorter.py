"""
AI Sorter - Production-Hardened FastAPI Service

Features:
- Pydantic v2 models with comprehensive validation
- Circuit breaker pattern for LLM API resilience
- Exponential backoff retry logic
- Rate limiting (token bucket)
- Concurrency controls
- PII redaction in logging
- Structured logging with structlog
- Prometheus metrics
- Graceful shutdown
- Health and readiness endpoints
"""

import asyncio
import os
import re
import signal
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx
import structlog
import yaml
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field, field_validator
from pyrate_limiter import Duration, Limiter, RequestRate
from starlette.responses import Response
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# =============================================================================
# Configuration
# =============================================================================

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Environment variables
GROK_API_URL = os.getenv("GROK_API_URL", "https://api.x.ai/v1/chat/completions")
GROK_API_KEY = os.getenv("GROK_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "grok-beta")
AI_SORTER_TIMEOUT = int(os.getenv("AI_SORTER_TIMEOUT", "30"))
AI_SORTER_RATE_LIMIT = int(os.getenv("AI_SORTER_RATE_LIMIT", "60"))
AI_SORTER_MAX_RETRIES = int(os.getenv("AI_SORTER_MAX_RETRIES", "3"))
AI_SORTER_CONCURRENCY = int(os.getenv("AI_SORTER_CONCURRENCY", "10"))

# =============================================================================
# Metrics
# =============================================================================

# Counters
requests_total = Counter(
    "ai_sorter_requests_total",
    "Total number of classification requests",
    ["status"],
)
items_classified_total = Counter(
    "ai_sorter_items_classified_total",
    "Total number of items classified",
    ["category"],
)
api_calls_total = Counter(
    "ai_sorter_api_calls_total",
    "Total number of AI API calls",
    ["status"],
)
circuit_breaker_opens = Counter(
    "ai_sorter_circuit_breaker_opens_total",
    "Total number of circuit breaker opens",
)

# Histograms
request_duration = Histogram(
    "ai_sorter_request_duration_seconds",
    "Request duration in seconds",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)
api_call_duration = Histogram(
    "ai_sorter_api_call_duration_seconds",
    "AI API call duration in seconds",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# Gauges
active_requests = Gauge(
    "ai_sorter_active_requests",
    "Number of active requests",
)
circuit_breaker_state = Gauge(
    "ai_sorter_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open)",
)

# =============================================================================
# Circuit Breaker
# =============================================================================


class CircuitBreakerState(Enum):
    CLOSED = 0
    OPEN = 1
    HALF_OPEN = 2


class CircuitBreaker:
    """Simple circuit breaker implementation"""

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 60,
        expected_exception: type = Exception,
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = CircuitBreakerState.CLOSED
        self._lock = asyncio.Lock()

    async def call(self, func, *args, **kwargs):
        async with self._lock:
            if self.state == CircuitBreakerState.OPEN:
                if self.last_failure_time and (
                    datetime.now().timestamp() - self.last_failure_time > self.timeout
                ):
                    logger.info("circuit_breaker_half_open")
                    self.state = CircuitBreakerState.HALF_OPEN
                    circuit_breaker_state.set(2)
                else:
                    logger.warning("circuit_breaker_blocking_call")
                    raise HTTPException(
                        status_code=503,
                        detail="Service temporarily unavailable (circuit breaker open)",
                    )

        try:
            result = await func(*args, **kwargs)
            async with self._lock:
                if self.state == CircuitBreakerState.HALF_OPEN:
                    logger.info("circuit_breaker_closed")
                    self.state = CircuitBreakerState.CLOSED
                    self.failure_count = 0
                    circuit_breaker_state.set(0)
            return result
        except self.expected_exception as e:
            async with self._lock:
                self.failure_count += 1
                self.last_failure_time = datetime.now().timestamp()

                if self.failure_count >= self.failure_threshold:
                    logger.error(
                        "circuit_breaker_opened",
                        failure_count=self.failure_count,
                        threshold=self.failure_threshold,
                    )
                    self.state = CircuitBreakerState.OPEN
                    circuit_breaker_opens.inc()
                    circuit_breaker_state.set(1)
            raise


# Global circuit breaker
circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60)

# =============================================================================
# Rate Limiter
# =============================================================================

# Rate limiter: AI_SORTER_RATE_LIMIT requests per minute
rate_limiter = Limiter(RequestRate(AI_SORTER_RATE_LIMIT, Duration.MINUTE))

# Concurrency semaphore
concurrency_semaphore = asyncio.Semaphore(AI_SORTER_CONCURRENCY)

# =============================================================================
# PII Redaction
# =============================================================================

PII_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
    "phone": re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
    "ip_address": re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    "api_key": re.compile(r"(api[_-]?key|token|secret)[\"']?\s*[:=]\s*[\"']?([a-zA-Z0-9_\-]{20,})", re.IGNORECASE),
}


def redact_pii(text: str) -> str:
    """Redact PII from text"""
    if not text:
        return text

    redacted = text
    for pii_type, pattern in PII_PATTERNS.items():
        if pii_type == "api_key":
            redacted = pattern.sub(f"\\1=[REDACTED_{pii_type.upper()}]", redacted)
        else:
            redacted = pattern.sub(f"[REDACTED_{pii_type.upper()}]", redacted)

    return redacted


# =============================================================================
# Pydantic Models
# =============================================================================


class TelemetryType(str, Enum):
    """Supported telemetry types"""

    LOG = "log"
    METRIC = "metric"
    TRACE = "trace"
    EVENT = "event"


class SeverityCategory(str, Enum):
    """Classification categories"""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class ForwardDestination(str, Enum):
    """Forward destinations"""

    ALERTING = "alerting"
    STORAGE = "storage"
    ARCHIVE = "archive"


class DataItem(BaseModel):
    """Individual telemetry data item"""

    type: TelemetryType
    content: Dict[str, Any]
    timestamp: Optional[datetime] = Field(default_factory=datetime.now)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if not v:
            raise ValueError("content cannot be empty")
        return v

    model_config = {"json_schema_extra": {"examples": [{"type": "log", "content": {"message": "Error occurred", "level": "error"}}]}}


class BatchRequest(BaseModel):
    """Batch classification request"""

    items: List[DataItem] = Field(..., min_length=1, max_length=100)
    request_id: Optional[str] = None

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: List[DataItem]) -> List[DataItem]:
        if len(v) > 100:
            raise ValueError("Maximum 100 items per batch")
        return v


class Classification(BaseModel):
    """Classification result"""

    category: SeverityCategory
    forward_to: ForwardDestination
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    reasoning: Optional[str] = None


class SortedItem(BaseModel):
    """Classified item with routing information"""

    item: DataItem
    classification: Classification
    processing_time_ms: float


class BatchResponse(BaseModel):
    """Batch classification response"""

    items: List[SortedItem]
    request_id: Optional[str] = None
    total_processing_time_ms: float
    success_count: int
    failure_count: int


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    timestamp: datetime
    version: str = "1.0.0"
    checks: Dict[str, bool]


# =============================================================================
# AI API Client
# =============================================================================


class AIClient:
    """HTTP client for AI API with retry logic"""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(AI_SORTER_TIMEOUT))

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(AI_SORTER_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def classify_batch(self, items: List[DataItem]) -> List[Classification]:
        """Classify a batch of items using AI API"""
        start_time = datetime.now()

        # Build prompt
        prompt = self._build_prompt(items)

        # Make API call
        try:
            logger.info("ai_api_call_start", item_count=len(items))

            response = await self.client.post(
                GROK_API_URL,
                headers={
                    "Authorization": f"Bearer {GROK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": AI_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 1000,
                },
            )

            duration = (datetime.now() - start_time).total_seconds()
            api_call_duration.observe(duration)

            if response.status_code != 200:
                api_calls_total.labels(status="error").inc()
                logger.error(
                    "ai_api_error",
                    status_code=response.status_code,
                    response=redact_pii(response.text[:500]),
                )
                raise httpx.HTTPError(f"AI API error: {response.status_code}")

            api_calls_total.labels(status="success").inc()

            # Parse response
            ai_output = response.json()["choices"][0]["message"]["content"]
            logger.info("ai_api_call_success", duration=duration)

            classifications = self._parse_ai_output(ai_output, len(items))
            return classifications

        except httpx.TimeoutException:
            api_calls_total.labels(status="timeout").inc()
            logger.error("ai_api_timeout")
            raise
        except Exception as e:
            api_calls_total.labels(status="error").inc()
            logger.error("ai_api_exception", error=str(e))
            raise

    def _build_prompt(self, items: List[DataItem]) -> str:
        """Build classification prompt"""
        prompt = """Classify these telemetry items and respond with YAML format:

Instructions:
- Analyze each telemetry item
- Assign category: critical, warning, or info
- Assign forward_to: alerting, storage, or archive
- Critical items with errors/failures should go to alerting
- Warning items should go to storage
- Info items should go to archive

Telemetry items:
"""
        for i, item in enumerate(items):
            # Redact PII before sending to AI
            content_str = str(item.content)[:200]
            content_str = redact_pii(content_str)
            prompt += f"{i + 1}. Type: {item.type}, Content: {content_str}...\n"

        prompt += """
Respond with YAML in this exact format:
```yaml
classifications:
  - category: critical
    forward_to: alerting
  - category: info
    forward_to: storage
```
"""
        return prompt

    def _parse_ai_output(self, output: str, expected_count: int) -> List[Classification]:
        """Parse AI output to extract classifications"""
        try:
            # Extract YAML from markdown code blocks
            yaml_match = re.search(r"```(?:yaml)?\n(.*?)\n```", output, re.DOTALL)
            if yaml_match:
                yaml_content = yaml_match.group(1)
            else:
                yaml_content = output

            parsed = yaml.safe_load(yaml_content)

            if isinstance(parsed, dict) and "classifications" in parsed:
                classifications_data = parsed["classifications"]
            elif isinstance(parsed, list):
                classifications_data = parsed
            else:
                logger.warning("unexpected_ai_output_format")
                classifications_data = []

            # Convert to Classification objects
            classifications = []
            for cls_data in classifications_data:
                try:
                    classification = Classification(
                        category=SeverityCategory(cls_data.get("category", "info")),
                        forward_to=ForwardDestination(cls_data.get("forward_to", "storage")),
                        confidence=cls_data.get("confidence"),
                        reasoning=cls_data.get("reasoning"),
                    )
                    classifications.append(classification)
                except (ValueError, KeyError) as e:
                    logger.warning("invalid_classification", error=str(e))
                    classifications.append(self._fallback_classification())

            # Ensure we have enough classifications
            while len(classifications) < expected_count:
                classifications.append(self._fallback_classification())

            return classifications[:expected_count]

        except yaml.YAMLError as e:
            logger.error("yaml_parsing_error", error=str(e))
            return [self._fallback_classification() for _ in range(expected_count)]
        except Exception as e:
            logger.error("classification_parsing_error", error=str(e))
            return [self._fallback_classification() for _ in range(expected_count)]

    def _fallback_classification(self) -> Classification:
        """Fallback classification when AI fails"""
        return Classification(
            category=SeverityCategory.INFO,
            forward_to=ForwardDestination.STORAGE,
            confidence=0.0,
            reasoning="Fallback classification due to AI API failure",
        )

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Global AI client
ai_client: Optional[AIClient] = None

# =============================================================================
# Application Lifecycle
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global ai_client

    # Startup
    logger.info("ai_sorter_starting")
    ai_client = AIClient()

    # Register signal handlers for graceful shutdown
    def handle_shutdown(signum, frame):
        logger.info("shutdown_signal_received", signal=signum)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    logger.info("ai_sorter_ready")

    yield

    # Shutdown
    logger.info("ai_sorter_shutting_down")
    if ai_client:
        await ai_client.close()
    logger.info("ai_sorter_stopped")


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="AI Sorter",
    description="Production-hardened AI-driven intelligent sorting for telemetry data",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


# =============================================================================
# Middleware
# =============================================================================


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with PII redaction"""
    start_time = datetime.now()
    request_id = request.headers.get("X-Request-ID", "unknown")

    logger.info(
        "request_started",
        method=request.method,
        path=redact_pii(str(request.url.path)),
        request_id=request_id,
    )

    response = await call_next(request)

    duration = (datetime.now() - start_time).total_seconds()

    logger.info(
        "request_completed",
        method=request.method,
        path=redact_pii(str(request.url.path)),
        status_code=response.status_code,
        duration=duration,
        request_id=request_id,
    )

    return response


# =============================================================================
# Health Endpoints
# =============================================================================


@app.get("/healthz", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint (liveness probe)

    Returns basic health status without checking dependencies
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(),
        checks={"server": True},
    )


@app.get("/readyz", response_model=HealthResponse, tags=["Health"])
async def readiness_check():
    """
    Readiness check endpoint (readiness probe)

    Checks if service is ready to accept traffic
    """
    checks = {
        "server": True,
        "api_key_configured": bool(GROK_API_KEY),
        "circuit_breaker": circuit_breaker.state == CircuitBreakerState.CLOSED,
    }

    is_ready = all(checks.values())
    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content=HealthResponse(
            status="ready" if is_ready else "not_ready",
            timestamp=datetime.now(),
            checks=checks,
        ).model_dump(),
    )


@app.get("/metrics", tags=["Monitoring"])
async def metrics():
    """
    Prometheus metrics endpoint
    """
    return Response(content=generate_latest(), media_type="text/plain")


# =============================================================================
# Classification Endpoint
# =============================================================================


@app.post("/sort", response_model=BatchResponse, tags=["Classification"])
async def sort_data(batch: BatchRequest):
    """
    Sort and classify telemetry data using AI

    This endpoint:
    - Validates input
    - Applies rate limiting
    - Controls concurrency
    - Uses circuit breaker for resilience
    - Retries with exponential backoff
    - Redacts PII in logs
    - Records metrics
    """
    start_time = datetime.now()
    request_id = batch.request_id or f"req-{datetime.now().timestamp()}"

    # Check API key
    if not GROK_API_KEY:
        logger.error("api_key_missing")
        requests_total.labels(status="error").inc()
        raise HTTPException(status_code=500, detail="API key not configured")

    # Rate limiting
    try:
        rate_limiter.try_acquire("global")
    except Exception:
        logger.warning("rate_limit_exceeded")
        requests_total.labels(status="rate_limited").inc()
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # Concurrency control
    if not concurrency_semaphore.locked():
        async with concurrency_semaphore:
            return await _process_batch(batch, request_id, start_time)
    else:
        logger.warning("concurrency_limit_reached")
        requests_total.labels(status="concurrency_limited").inc()
        raise HTTPException(status_code=503, detail="Service at capacity, try again later")


async def _process_batch(batch: BatchRequest, request_id: str, start_time: datetime) -> BatchResponse:
    """Internal batch processing with metrics"""
    active_requests.inc()

    try:
        logger.info("processing_batch", request_id=request_id, item_count=len(batch.items))

        # Classify with circuit breaker
        classifications = await circuit_breaker.call(ai_client.classify_batch, batch.items)

        # Build response
        sorted_items = []
        success_count = 0
        failure_count = 0

        for item, classification in zip(batch.items, classifications):
            item_start = datetime.now()
            processing_time = (datetime.now() - item_start).total_seconds() * 1000

            sorted_item = SortedItem(
                item=item,
                classification=classification,
                processing_time_ms=processing_time,
            )
            sorted_items.append(sorted_item)

            if classification.confidence and classification.confidence > 0.5:
                success_count += 1
            else:
                failure_count += 1

            # Record metrics
            items_classified_total.labels(category=classification.category.value).inc()

        total_duration = (datetime.now() - start_time).total_seconds()
        request_duration.observe(total_duration)
        requests_total.labels(status="success").inc()

        logger.info(
            "batch_processed",
            request_id=request_id,
            success_count=success_count,
            failure_count=failure_count,
            duration=total_duration,
        )

        return BatchResponse(
            items=sorted_items,
            request_id=request_id,
            total_processing_time_ms=total_duration * 1000,
            success_count=success_count,
            failure_count=failure_count,
        )

    except HTTPException:
        requests_total.labels(status="error").inc()
        raise
    except Exception as e:
        logger.error("batch_processing_error", error=str(e), request_id=request_id)
        requests_total.labels(status="error").inc()
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        active_requests.dec()


# =============================================================================
# Error Handlers
# =============================================================================


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(
        "unhandled_exception",
        error=str(exc),
        path=redact_pii(str(request.url.path)),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "ai_sorter:app",
        host="0.0.0.0",
        port=8080,
        log_config=None,  # Use structlog instead
        access_log=False,  # Handled by middleware
    )
