"""
Claude Provider for Multi-Provider AI Sorter

Integrates with Anthropic's Claude models for intelligent telemetry data classification.
Supports Claude-3, Claude-2, and other Anthropic models with comprehensive error handling.
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
class ClaudeConfig(AIProviderConfig):
    """Claude-specific configuration"""
    api_key: str
    model: str = "claude-3-sonnet-20240229"
    max_tokens: int = 1000
    temperature: float = 0.3
    max_retries: int = 3
    request_timeout: int = 30
    api_base_url: str = "https://api.anthropic.com"
    
    # Rate limiting (Anthropic's limits)
    requests_per_minute: int = 50
    tokens_per_minute: int = 8000
    
    # Model fallbacks
    use_model_fallback: bool = True
    fallback_models: List[str] = None
    
    # Response validation
    enforce_structured_response: bool = True
    max_classification_attempts: int = 2
    
    def __post_init__(self):
        if self.fallback_models is None:
            self.fallback_models = [
                "claude-3-haiku-20240307",  # Faster, cheaper model
                "claude-2.1"  # Previous generation
            ]


class ClaudeProvider(AIProvider):
    """Claude provider implementation using Anthropic's API"""
    
    def __init__(self, config: ClaudeConfig):
        super().__init__("claude", config)
        self.config = config
        self.client: Optional[httpx.AsyncClient] = None
        
        # Rate limiting state
        self._request_times: List[float] = []
        self._token_usage: List[tuple] = []  # (timestamp, tokens_used)
        
        # Performance tracking per model
        self._model_performance: Dict[str, Dict[str, Any]] = {}
        
        # API headers
        self._headers = {
            "x-api-key": self.config.api_key,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01"
        }
    
    async def initialize(self) -> bool:
        """Initialize Claude HTTP client"""
        try:
            # Create async HTTP client with proper configuration
            self.client = httpx.AsyncClient(
                base_url=self.config.api_base_url,
                headers=self._headers,
                timeout=httpx.Timeout(self.config.request_timeout),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
            
            # Test connection
            await self._test_connection()
            
            logger.info("Claude provider initialized successfully",
                       model=self.config.model,
                       api_base_url=self.config.api_base_url)
            return True
            
        except Exception as e:
            logger.error("Failed to initialize Claude provider", error=str(e))
            return False
    
    async def _test_connection(self):
        """Test Claude API connection"""
        try:
            test_payload = {
                "model": self.config.model,
                "max_tokens": 10,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test connection. Reply with 'OK'."
                    }
                ]
            }
            
            response = await self.client.post("/v1/messages", json=test_payload)
            
            if response.status_code != 200:
                raise AIProviderError(f"Claude API test failed: {response.status_code} - {response.text}")
            
            data = response.json()
            if not data.get("content"):
                raise AIProviderError("Empty response from Claude API")
            
            logger.debug("Claude connection test successful")
            
        except httpx.RequestError as e:
            raise AIProviderError(f"Claude connection test failed: {e}")
        except Exception as e:
            raise AIProviderError(f"Claude connection test error: {e}")
    
    async def classify_batch(self, items: List[DataItem]) -> List[SortedItem]:
        """Classify a batch of telemetry items using Claude"""
        if not self.client:
            raise AIProviderError("Claude provider not initialized")
        
        if not items:
            return []
        
        start_time = time.time()
        model_used = self.config.model
        
        try:
            # Check rate limits before making request
            await self._check_rate_limits()
            
            # Build prompt for classification
            prompt = self._build_classification_prompt(items)
            
            # Choose optimal model based on complexity and performance
            model_used = await self._select_optimal_model(items)
            
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
                    provider="claude",
                    model=model_used
                ))
            
            # Update performance metrics
            duration = time.time() - start_time
            await self._update_performance_metrics(model_used, duration, len(items), True)
            
            logger.info("Claude classification completed",
                       items_processed=len(sorted_items),
                       model_used=model_used,
                       duration_seconds=duration)
            
            return sorted_items
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("Claude rate limit exceeded", error=str(e))
                raise AIProviderError(f"Rate limit exceeded: {e}")
            else:
                logger.error("Claude HTTP error", status_code=e.response.status_code, error=str(e))
                
                # Try fallback model if available
                if (self.config.use_model_fallback and 
                    model_used == self.config.model and 
                    self.config.fallback_models):
                    logger.info("Attempting fallback to alternative model")
                    try:
                        return await self._retry_with_fallback_model(items, prompt)
                    except Exception as fallback_error:
                        logger.error("Fallback model also failed", error=str(fallback_error))
                
                raise AIProviderError(f"Claude API error: {e}")
        
        except Exception as e:
            duration = time.time() - start_time
            await self._update_performance_metrics(model_used, duration, len(items), False)
            logger.error("Claude classification failed", error=str(e))
            raise AIProviderError(f"Classification failed: {e}")
    
    def _build_classification_prompt(self, items: List[DataItem]) -> str:
        """Build prompt for Claude classification"""
        
        # Claude works well with structured prompts and examples
        prompt = """You are an expert system for classifying observability telemetry data. Your task is to analyze each telemetry item and classify it according to specific rules.

CLASSIFICATION RULES:
1. Category Classification:
   - "critical": Errors, failures, alerts, security issues, system outages
   - "warning": Performance degradation, warnings, resource constraints, non-critical issues
   - "info": Normal operations, debug information, routine events, informational messages

2. Routing Classification:
   - "alerting": Critical items requiring immediate attention and notification
   - "storage": Warning items needing retention for analysis and trending
   - "archive": Info items for long-term storage and compliance

EXAMPLES:
Input: {"level": "ERROR", "message": "Database connection failed", "service": "user-auth"}
Output: {"category": "critical", "forward_to": "alerting", "confidence": 0.95}

Input: {"level": "WARN", "message": "High memory usage: 85%", "service": "api-gateway"}
Output: {"category": "warning", "forward_to": "storage", "confidence": 0.90}

Input: {"level": "INFO", "message": "User login successful", "service": "user-auth"}
Output: {"category": "info", "forward_to": "archive", "confidence": 0.85}

RESPONSE FORMAT:
Respond with a JSON array containing exactly one classification object per input item, in the same order as provided:

```json
[
  {"category": "critical", "forward_to": "alerting", "confidence": 0.95},
  {"category": "warning", "forward_to": "storage", "confidence": 0.88},
  {"category": "info", "forward_to": "archive", "confidence": 0.92}
]
```

TELEMETRY ITEMS TO CLASSIFY:
"""
        
        for i, item in enumerate(items):
            # Truncate content to avoid token limits while preserving important info
            content_str = json.dumps(item.content, indent=None, separators=(',', ':'))
            if len(content_str) > 400:
                # Try to preserve key fields like level, message, error
                try:
                    content_dict = item.content
                    important_fields = {}
                    for key in ['level', 'severity', 'message', 'error', 'exception', 'status', 'code']:
                        if key in content_dict:
                            important_fields[key] = content_dict[key]
                    
                    # Add a few more fields if space allows
                    remaining_space = 400 - len(json.dumps(important_fields))
                    for key, value in content_dict.items():
                        if key not in important_fields and remaining_space > 0:
                            field_str = json.dumps({key: value})
                            if len(field_str) < remaining_space:
                                important_fields[key] = value
                                remaining_space -= len(field_str)
                    
                    content_str = json.dumps(important_fields) + "..."
                except:
                    content_str = content_str[:400] + "..."
            
            prompt += f"\n{i+1}. Type: {item.type}\n   Content: {content_str}\n"
        
        prompt += f"\nAnalyze and classify these {len(items)} telemetry items. Respond with the JSON array only:"
        
        return prompt
    
    async def _select_optimal_model(self, items: List[DataItem]) -> str:
        """Select optimal model based on request complexity and performance"""
        
        # Calculate request complexity
        total_content_length = sum(len(str(item.content)) for item in items)
        item_count = len(items)
        
        # Check for complex content that might need the full model
        has_complex_content = any(
            isinstance(item.content, dict) and 
            any(key in str(item.content).lower() for key in ['error', 'exception', 'trace', 'stack'])
            for item in items
        )
        
        # Get performance metrics for model selection
        primary_performance = self._model_performance.get(self.config.model, {})
        
        # Use fallback model for simple requests or if primary model is underperforming
        if (not has_complex_content and 
            item_count <= 10 and 
            total_content_length < 2000 and
            self.config.fallback_models):
            
            # Check if fallback model has better performance
            fallback_model = self.config.fallback_models[0]
            fallback_performance = self._model_performance.get(fallback_model, {})
            
            if (primary_performance.get("error_rate", 0) > 0.1 and 
                fallback_performance.get("error_rate", 0) < 0.05):
                return fallback_model
        
        return self.config.model
    
    async def _make_api_request(self, prompt: str, model: str) -> Dict[str, Any]:
        """Make API request to Claude with error handling"""
        
        payload = {
            "model": model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        try:
            response = await self.client.post("/v1/messages", json=payload)
            response.raise_for_status()
            
            response_data = response.json()
            
            # Track token usage for rate limiting
            if "usage" in response_data:
                total_tokens = (response_data["usage"].get("input_tokens", 0) + 
                              response_data["usage"].get("output_tokens", 0))
                self._token_usage.append((time.time(), total_tokens))
            
            # Track request time for rate limiting
            self._request_times.append(time.time())
            
            return response_data
            
        except httpx.HTTPStatusError as e:
            logger.error("Claude API HTTP error", 
                        status_code=e.response.status_code,
                        response_text=e.response.text)
            raise
        except Exception as e:
            logger.error("Claude API request failed", model=model, error=str(e))
            raise
    
    async def _parse_response(self, response_data: Dict[str, Any], expected_count: int) -> List[Dict[str, Any]]:
        """Parse and validate Claude response"""
        try:
            if "content" not in response_data or not response_data["content"]:
                raise ValueError("Empty content in Claude response")
            
            # Claude returns content as a list of content blocks
            content_blocks = response_data["content"]
            if not content_blocks:
                raise ValueError("No content blocks in response")
            
            # Get the text content from the first block
            content_text = content_blocks[0].get("text", "")
            logger.debug("Claude raw response", content=content_text)
            
            # Parse JSON response
            try:
                # Try direct JSON parsing first
                classifications = json.loads(content_text)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code blocks
                import re
                json_match = re.search(r'```(?:json)?\n(.*?)\n```', content_text, re.DOTALL)
                if json_match:
                    classifications = json.loads(json_match.group(1))
                else:
                    # Try to find JSON array in the text
                    array_match = re.search(r'\[.*\]', content_text, re.DOTALL)
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
                    if category in ["error", "critical", "fatal", "severe"]:
                        cls["category"] = "critical"
                    elif category in ["warn", "warning", "caution"]:
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
            logger.error("Failed to parse Claude response", error=str(e))
            # Return default classifications as fallback
            return [{"category": "info", "forward_to": "storage", "confidence": 0.7} 
                   for _ in range(expected_count)]
    
    async def _retry_with_fallback_model(self, items: List[DataItem], prompt: str) -> List[SortedItem]:
        """Retry classification with fallback model"""
        for fallback_model in self.config.fallback_models:
            try:
                logger.info("Retrying with fallback model", fallback_model=fallback_model)
                
                response_data = await self._make_api_request(prompt, fallback_model)
                classifications = await self._parse_response(response_data, len(items))
                
                sorted_items = []
                for i, item in enumerate(items):
                    cls = classifications[i] if i < len(classifications) else {
                        "category": "info", "forward_to": "storage", "confidence": 0.7
                    }
                    
                    sorted_items.append(SortedItem(
                        item=item,
                        category=cls["category"],
                        forward_to=cls["forward_to"],
                        confidence=cls["confidence"],
                        provider="claude",
                        model=fallback_model
                    ))
                
                logger.info("Fallback model successful", fallback_model=fallback_model)
                return sorted_items
                
            except Exception as e:
                logger.warning("Fallback model failed", 
                             fallback_model=fallback_model, 
                             error=str(e))
                continue
        
        # If all fallback models failed, raise the original error
        raise AIProviderError("All fallback models failed")
    
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
        """Check Claude provider health"""
        if not self.client:
            return {
                "healthy": False,
                "error": "Client not initialized"
            }
        
        try:
            # Quick health check with minimal token usage
            start_time = time.time()
            
            # Use the fastest/cheapest model for health checks
            health_check_model = (self.config.fallback_models[0] 
                                if self.config.fallback_models 
                                else self.config.model)
            
            payload = {
                "model": health_check_model,
                "max_tokens": 5,
                "messages": [
                    {
                        "role": "user",
                        "content": "Health check. Respond: OK"
                    }
                ]
            }
            
            response = await self.client.post("/v1/messages", json=payload)
            response.raise_for_status()
            
            duration = time.time() - start_time
            response_data = response.json()
            
            if (response_data.get("content") and 
                len(response_data["content"]) > 0 and
                response_data["content"][0].get("text")):
                return {
                    "healthy": True,
                    "response_time_ms": duration * 1000,
                    "model": health_check_model,
                    "performance_metrics": self._model_performance
                }
            else:
                return {
                    "healthy": False,
                    "error": "Empty response from Claude"
                }
                
        except Exception as e:
            logger.error("Claude health check failed", error=str(e))
            return {
                "healthy": False,
                "error": str(e)
            }
    
    async def get_provider_info(self) -> Dict[str, Any]:
        """Get provider information and capabilities"""
        return {
            "name": self.name,
            "type": "claude",
            "models": {
                "primary": self.config.model,
                "fallbacks": self.config.fallback_models if self.config.use_model_fallback else []
            },
            "rate_limits": {
                "requests_per_minute": self.config.requests_per_minute,
                "tokens_per_minute": self.config.tokens_per_minute
            },
            "features": [
                "batch_classification",
                "confidence_scores",
                "model_fallback",
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
        
        logger.info("Claude provider shutdown completed")