"""
Grok Provider for Multi-Provider AI Sorter

Integrates with X.AI's Grok models for intelligent telemetry data classification.
Supports Grok-beta and future models with comprehensive error handling.
"""

import asyncio
import json
import time
from typing import List, Dict, Optional, Any
import structlog
import httpx
from dataclasses import dataclass

from .base_provider import AIProvider, AIProviderConfig, AIResponse, AIProviderError
from ..models.requests import DataItem, SortedItem

logger = structlog.get_logger(__name__)


@dataclass
class GrokConfig(AIProviderConfig):
    """Grok-specific configuration"""
    api_key: str
    model: str = "grok-beta"
    temperature: float = 0.3
    max_tokens: int = 1000
    max_retries: int = 3
    request_timeout: int = 30
    base_url: str = "https://api.x.ai/v1"
    
    # Rate limiting (X.AI's limits)
    requests_per_minute: int = 50
    tokens_per_minute: int = 5000
    
    # Response validation
    enforce_structured_response: bool = True
    max_classification_attempts: int = 2
    
    # Cost optimization (currently only one model available)
    use_cheaper_model_fallback: bool = False
    cheaper_model: str = "grok-beta"


class GrokProvider(AIProvider):
    """Grok provider implementation using X.AI's API"""
    
    def __init__(self, config: GrokConfig):
        super().__init__("grok", config)
        self.config = config
        self.client: Optional[httpx.AsyncClient] = None
        
        # Rate limiting state
        self._request_times: List[float] = []
        self._token_usage: List[tuple] = []  # (timestamp, tokens_used)
        
        # Performance tracking
        self._model_performance: Dict[str, Dict[str, Any]] = {}
        
        # API headers
        self._headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }
    
    async def initialize(self) -> bool:
        """Initialize Grok HTTP client"""
        try:
            # Create async HTTP client with proper configuration
            self.client = httpx.AsyncClient(
                base_url=self.config.base_url,
                headers=self._headers,
                timeout=httpx.Timeout(self.config.request_timeout),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
            
            # Test connection
            await self._test_connection()
            
            logger.info("Grok provider initialized successfully",
                       model=self.config.model,
                       base_url=self.config.base_url)
            return True
            
        except Exception as e:
            logger.error("Failed to initialize Grok provider", error=str(e))
            return False
    
    async def _test_connection(self):
        """Test Grok API connection"""
        try:
            test_payload = {
                "model": self.config.model,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test connection. Reply with 'OK'."
                    }
                ],
                "max_tokens": 5,
                "temperature": 0
            }
            
            response = await self.client.post("/chat/completions", json=test_payload)
            
            if response.status_code != 200:
                raise AIProviderError(f"Grok API test failed: {response.status_code} - {response.text}")
            
            data = response.json()
            if not data.get("choices") or not data["choices"][0].get("message"):
                raise AIProviderError("Empty response from Grok API")
            
            logger.debug("Grok connection test successful")
            
        except httpx.RequestError as e:
            raise AIProviderError(f"Grok connection test failed: {e}")
        except Exception as e:
            raise AIProviderError(f"Grok connection test error: {e}")
    
    async def classify_batch(self, items: List[DataItem]) -> List[SortedItem]:
        """Classify a batch of telemetry items using Grok"""
        if not self.client:
            raise AIProviderError("Grok provider not initialized")
        
        if not items:
            return []
        
        start_time = time.time()
        model_used = self.config.model
        
        try:
            # Check rate limits before making request
            await self._check_rate_limits()
            
            # Build prompt for classification
            prompt = self._build_classification_prompt(items)
            
            # Make API request with retries
            response_data = await self._make_api_request(prompt, model_used)
            
            # Parse and validate response
            classifications = await self._parse_response(response_data, len(items))
            
            # Build sorted items
            sorted_items = []
            for i, item in enumerate(items):
                if i < len(classifications):
                    cls = classifications[i]
                else:
                    # Fallback classification
                    cls = {"category": "info", "forward_to": "storage", "confidence": 0.8}
                
                sorted_items.append(SortedItem(
                    item=item,
                    category=cls["category"],
                    forward_to=cls["forward_to"],
                    confidence=cls.get("confidence", 0.8),
                    provider="grok",
                    model=model_used
                ))
            
            # Update performance metrics
            duration = time.time() - start_time
            await self._update_performance_metrics(model_used, duration, len(items), True)
            
            logger.info("Grok classification completed",
                       items_processed=len(sorted_items),
                       model_used=model_used,
                       duration_seconds=duration)
            
            return sorted_items
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("Grok rate limit exceeded", error=str(e))
                raise AIProviderError(f"Rate limit exceeded: {e}")
            else:
                logger.error("Grok HTTP error", status_code=e.response.status_code, error=str(e))
                raise AIProviderError(f"Grok API error: {e}")
        
        except Exception as e:
            duration = time.time() - start_time
            await self._update_performance_metrics(model_used, duration, len(items), False)
            logger.error("Grok classification failed", error=str(e))
            raise AIProviderError(f"Classification failed: {e}")
    
    def _build_classification_prompt(self, items: List[DataItem]) -> str:
        """Build prompt for Grok classification"""
        
        # Grok works well with clear, structured prompts
        prompt = """You are an expert system for classifying observability telemetry data. Analyze each telemetry item and classify it with precision.

CLASSIFICATION RULES:
1. Category Classification:
   - "critical": System failures, errors, alerts, security breaches, outages
   - "warning": Performance issues, resource constraints, non-critical problems
   - "info": Normal operations, routine events, debug information

2. Routing Classification:
   - "alerting": Critical items requiring immediate human attention
   - "storage": Warning items needing analysis and trending
   - "archive": Info items for long-term storage and compliance

EXAMPLES:
Input: {"level": "ERROR", "message": "Database connection lost", "service": "payment-api"}
Output: {"category": "critical", "forward_to": "alerting", "confidence": 0.98}

Input: {"level": "WARN", "message": "CPU usage 82%", "service": "web-server"}
Output: {"category": "warning", "forward_to": "storage", "confidence": 0.92}

Input: {"level": "INFO", "message": "Request processed successfully", "service": "user-service"}
Output: {"category": "info", "forward_to": "archive", "confidence": 0.90}

RESPONSE FORMAT:
Return a JSON array with exactly one classification object per input item, in order:

```json
[
  {"category": "critical", "forward_to": "alerting", "confidence": 0.95},
  {"category": "warning", "forward_to": "storage", "confidence": 0.88}
]
```

TELEMETRY ITEMS TO CLASSIFY:
"""
        
        for i, item in enumerate(items):
            # Truncate content to avoid token limits while preserving key information
            content_str = json.dumps(item.content, indent=None, separators=(',', ':'))
            if len(content_str) > 500:
                # Try to preserve important fields
                try:
                    content_dict = item.content
                    important_fields = {}
                    
                    # Priority fields to preserve
                    priority_keys = ['level', 'severity', 'message', 'error', 'exception', 
                                   'status', 'code', 'service', 'component', 'timestamp']
                    
                    for key in priority_keys:
                        if key in content_dict:
                            important_fields[key] = content_dict[key]
                    
                    # Add other fields if we have space
                    remaining_space = 500 - len(json.dumps(important_fields))
                    for key, value in content_dict.items():
                        if key not in important_fields and remaining_space > 0:
                            field_str = json.dumps({key: value})
                            if len(field_str) < remaining_space:
                                important_fields[key] = value
                                remaining_space -= len(field_str)
                    
                    content_str = json.dumps(important_fields) + "..."
                except:
                    content_str = content_str[:500] + "..."
            
            prompt += f"\n{i+1}. Type: {item.type}\n   Content: {content_str}\n"
        
        prompt += f"\nAnalyze and classify these {len(items)} telemetry items. Return the JSON array:"
        
        return prompt
    
    async def _make_api_request(self, prompt: str, model: str) -> Dict[str, Any]:
        """Make API request to Grok with error handling"""
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise telemetry classification system. Always respond with valid JSON only."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens
        }
        
        try:
            response = await self.client.post("/chat/completions", json=payload)
            response.raise_for_status()
            
            response_data = response.json()
            
            # Track token usage for rate limiting (if provided by API)
            if "usage" in response_data:
                total_tokens = response_data["usage"].get("total_tokens", 0)
                self._token_usage.append((time.time(), total_tokens))
            
            # Track request time for rate limiting
            self._request_times.append(time.time())
            
            return response_data
            
        except httpx.HTTPStatusError as e:
            logger.error("Grok API HTTP error", 
                        status_code=e.response.status_code,
                        response_text=e.response.text)
            raise
        except Exception as e:
            logger.error("Grok API request failed", model=model, error=str(e))
            raise
    
    async def _parse_response(self, response_data: Dict[str, Any], expected_count: int) -> List[Dict[str, Any]]:
        """Parse and validate Grok response"""
        try:
            if "choices" not in response_data or not response_data["choices"]:
                raise ValueError("Empty choices in Grok response")
            
            # Get the response content
            choice = response_data["choices"][0]
            if "message" not in choice or "content" not in choice["message"]:
                raise ValueError("Invalid choice structure in Grok response")
            
            content_text = choice["message"]["content"]
            logger.debug("Grok raw response", content=content_text)
            
            # Parse JSON response
            try:
                # Try direct JSON parsing first
                classifications = json.loads(content_text)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code blocks
                import re
                json_match = re.search(r'```(?:json)?\\n(.*?)\\n```', content_text, re.DOTALL)
                if json_match:
                    classifications = json.loads(json_match.group(1))
                else:
                    # Try to find JSON array in the text
                    array_match = re.search(r'\\[.*\\]', content_text, re.DOTALL)
                    if array_match:
                        classifications = json.loads(array_match.group(0))
                    else:
                        raise ValueError("No valid JSON found in response")
            
            # Validate response format
            if not isinstance(classifications, list):
                raise ValueError("Response must be a JSON array")
            
            # Ensure we have classifications for all items
            while len(classifications) < expected_count:
                classifications.append({
                    "category": "info",
                    "forward_to": "storage",
                    "confidence": 0.7
                })
            
            # Validate and normalize each classification
            valid_categories = {"critical", "warning", "info"}
            valid_destinations = {"alerting", "storage", "archive"}
            
            for i, cls in enumerate(classifications):
                if not isinstance(cls, dict):
                    classifications[i] = {"category": "info", "forward_to": "storage", "confidence": 0.7}
                    continue
                
                # Validate and fix category
                category = cls.get("category", "").lower()
                if category not in valid_categories:
                    # Try to infer from common variations
                    if category in ["error", "critical", "fatal", "severe", "alert"]:
                        cls["category"] = "critical"
                    elif category in ["warn", "warning", "caution", "degraded"]:
                        cls["category"] = "warning"
                    else:
                        cls["category"] = "info"
                else:
                    cls["category"] = category
                
                # Validate and fix forward_to
                forward_to = cls.get("forward_to", "").lower()
                if forward_to not in valid_destinations:
                    # Map based on category if forward_to is invalid
                    if cls["category"] == "critical":
                        cls["forward_to"] = "alerting"
                    elif cls["category"] == "warning":
                        cls["forward_to"] = "storage"
                    else:
                        cls["forward_to"] = "archive"
                else:
                    cls["forward_to"] = forward_to
                
                # Ensure confidence is present and valid
                if "confidence" not in cls or not isinstance(cls.get("confidence"), (int, float)):
                    cls["confidence"] = 0.8
                else:
                    cls["confidence"] = max(0.0, min(1.0, float(cls["confidence"])))
            
            return classifications[:expected_count]
            
        except Exception as e:
            logger.error("Failed to parse Grok response", error=str(e))
            # Return default classifications as fallback
            return [{"category": "info", "forward_to": "storage", "confidence": 0.7} 
                   for _ in range(expected_count)]
    
    async def _check_rate_limits(self):
        """Check and enforce rate limits"""
        current_time = time.time()
        
        # Clean old request times (older than 1 minute)
        self._request_times = [t for t in self._request_times if current_time - t < 60]
        
        # Check request rate limit
        if len(self._request_times) >= self.config.requests_per_minute:
            wait_time = 60 - (current_time - self._request_times[0])
            if wait_time > 0:
                logger.warning("Rate limit approaching, waiting", wait_seconds=wait_time)
                await asyncio.sleep(wait_time)
        
        # Clean old token usage (older than 1 minute)
        self._token_usage = [(t, tokens) for t, tokens in self._token_usage if current_time - t < 60]
        
        # Check token rate limit
        total_tokens = sum(tokens for _, tokens in self._token_usage)
        if total_tokens >= self.config.tokens_per_minute:
            wait_time = 60 - (current_time - self._token_usage[0][0])
            if wait_time > 0:
                logger.warning("Token rate limit approaching, waiting", wait_seconds=wait_time)
                await asyncio.sleep(wait_time)
    
    async def _update_performance_metrics(self, model: str, duration: float,
                                        item_count: int, success: bool):
        """Update performance metrics for the model"""
        if model not in self._model_performance:
            self._model_performance[model] = {
                "requests": 0,
                "successes": 0,
                "failures": 0,
                "total_duration": 0,
                "total_items": 0,
                "error_rate": 0,
                "avg_duration": 0,
                "avg_items_per_request": 0
            }
        
        metrics = self._model_performance[model]
        metrics["requests"] += 1
        metrics["total_duration"] += duration
        metrics["total_items"] += item_count
        
        if success:
            metrics["successes"] += 1
        else:
            metrics["failures"] += 1
        
        # Calculate derived metrics
        metrics["error_rate"] = metrics["failures"] / metrics["requests"]
        metrics["avg_duration"] = metrics["total_duration"] / metrics["requests"]
        metrics["avg_items_per_request"] = metrics["total_items"] / metrics["requests"]
    
    async def health_check(self) -> Dict[str, Any]:
        """Check Grok provider health"""
        if not self.client:
            return {
                "healthy": False,
                "error": "Client not initialized"
            }
        
        try:
            # Quick health check with minimal token usage
            start_time = time.time()
            
            payload = {
                "model": self.config.model,
                "messages": [
                    {
                        "role": "user",
                        "content": "Health check. Respond: OK"
                    }
                ],
                "max_tokens": 5,
                "temperature": 0
            }
            
            response = await self.client.post("/chat/completions", json=payload)
            response.raise_for_status()
            
            duration = time.time() - start_time
            response_data = response.json()
            
            if (response_data.get("choices") and 
                len(response_data["choices"]) > 0 and
                response_data["choices"][0].get("message", {}).get("content")):
                return {
                    "healthy": True,
                    "response_time_ms": duration * 1000,
                    "model": self.config.model,
                    "performance_metrics": self._model_performance
                }
            else:
                return {
                    "healthy": False,
                    "error": "Empty response from Grok"
                }
                
        except Exception as e:
            logger.error("Grok health check failed", error=str(e))
            return {
                "healthy": False,
                "error": str(e)
            }
    
    async def get_provider_info(self) -> Dict[str, Any]:
        """Get provider information and capabilities"""
        return {
            "name": self.name,
            "type": "grok",
            "models": {
                "primary": self.config.model,
                "fallbacks": []  # Currently only one model available
            },
            "rate_limits": {
                "requests_per_minute": self.config.requests_per_minute,
                "tokens_per_minute": self.config.tokens_per_minute
            },
            "features": [
                "batch_classification",
                "confidence_scores",
                "rate_limiting",
                "performance_tracking",
                "structured_responses"
            ],
            "performance_metrics": self._model_performance
        }
    
    async def shutdown(self):
        """Shutdown provider and cleanup resources"""
        if self.client:
            await self.client.aclose()
            self.client = None
        
        logger.info("Grok provider shutdown completed")