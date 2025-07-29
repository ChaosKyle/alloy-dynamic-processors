"""
OpenAI Provider for Multi-Provider AI Sorter

Integrates with OpenAI's GPT models for intelligent telemetry data classification.
Supports GPT-4, GPT-3.5-turbo, and other OpenAI models with comprehensive error handling.
"""

import asyncio
import json
import time
from typing import List, Dict, Optional, Any
import structlog
import openai
from openai import AsyncOpenAI
from dataclasses import dataclass

from .base_provider import AIProvider, AIProviderConfig, AIResponse, AIProviderError
from ..models.requests import DataItem, SortedItem

logger = structlog.get_logger(__name__)


@dataclass
class OpenAIConfig(AIProviderConfig):
    """OpenAI-specific configuration"""
    api_key: str
    model: str = "gpt-4"
    temperature: float = 0.3
    max_tokens: int = 1000
    max_retries: int = 3
    request_timeout: int = 30
    organization: Optional[str] = None
    base_url: Optional[str] = None
    
    # Rate limiting
    requests_per_minute: int = 60
    tokens_per_minute: int = 10000
    
    # Cost optimization
    use_cheaper_model_fallback: bool = True
    cheaper_model: str = "gpt-3.5-turbo"
    
    # Response validation
    enforce_yaml_response: bool = True
    max_classification_attempts: int = 2


class OpenAIProvider(AIProvider):
    """OpenAI provider implementation"""
    
    def __init__(self, config: OpenAIConfig):
        super().__init__("openai", config)
        self.config = config
        self.client: Optional[AsyncOpenAI] = None
        
        # Rate limiting state
        self._request_times: List[float] = []
        self._token_usage: List[tuple] = []  # (timestamp, tokens_used)
        
        # Performance tracking
        self._model_performance: Dict[str, Dict[str, Any]] = {}
        
    async def initialize(self) -> bool:
        """Initialize OpenAI client"""
        try:
            # Create async OpenAI client
            client_kwargs = {
                "api_key": self.config.api_key,
                "timeout": self.config.request_timeout,
                "max_retries": self.config.max_retries
            }
            
            if self.config.organization:
                client_kwargs["organization"] = self.config.organization
            
            if self.config.base_url:
                client_kwargs["base_url"] = self.config.base_url
            
            self.client = AsyncOpenAI(**client_kwargs)
            
            # Test connection with a simple request
            await self._test_connection()
            
            logger.info("OpenAI provider initialized successfully",
                       model=self.config.model,
                       organization=self.config.organization)
            return True
            
        except Exception as e:
            logger.error("Failed to initialize OpenAI provider", error=str(e))
            return False
    
    async def _test_connection(self):
        """Test OpenAI API connection"""
        try:
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": "Test connection. Reply with 'OK'."}],
                max_tokens=10,
                temperature=0
            )
            
            if not response.choices:
                raise AIProviderError("Empty response from OpenAI API")
            
            logger.debug("OpenAI connection test successful")
            
        except openai.APIError as e:
            raise AIProviderError(f"OpenAI API error: {e}")
        except Exception as e:
            raise AIProviderError(f"OpenAI connection test failed: {e}")
    
    async def classify_batch(self, items: List[DataItem]) -> List[SortedItem]:
        """Classify a batch of telemetry items using OpenAI"""
        if not self.client:
            raise AIProviderError("OpenAI provider not initialized")
        
        if not items:
            return []
        
        start_time = time.time()
        
        try:
            # Check rate limits before making request
            await self._check_rate_limits()
            
            # Build prompt for classification
            prompt = self._build_classification_prompt(items)
            
            # Choose model based on request complexity and cost considerations
            model_to_use = await self._select_optimal_model(items)
            
            # Make API request with retries
            response = await self._make_api_request(prompt, model_to_use)
            
            # Parse and validate response
            classifications = await self._parse_response(response, len(items))
            
            # Build sorted items
            sorted_items = []
            for i, item in enumerate(items):
                if i < len(classifications):
                    cls = classifications[i]
                else:
                    # Fallback classification
                    cls = {"category": "info", "forward_to": "storage"}
                
                sorted_items.append(SortedItem(
                    item=item,
                    category=cls["category"],
                    forward_to=cls["forward_to"],
                    confidence=cls.get("confidence", 0.8),
                    provider="openai",
                    model=model_to_use
                ))
            
            # Update performance metrics
            duration = time.time() - start_time
            await self._update_performance_metrics(model_to_use, duration, len(items), True)
            
            logger.info("OpenAI classification completed",
                       items_processed=len(sorted_items),
                       model_used=model_to_use,
                       duration_seconds=duration)
            
            return sorted_items
            
        except openai.RateLimitError as e:
            logger.warning("OpenAI rate limit exceeded", error=str(e))
            raise AIProviderError(f"Rate limit exceeded: {e}")
        
        except openai.APIError as e:
            logger.error("OpenAI API error", error=str(e))
            
            # Try fallback model if available
            if (self.config.use_cheaper_model_fallback and 
                model_to_use != self.config.cheaper_model):
                logger.info("Attempting fallback to cheaper model")
                try:
                    return await self._retry_with_fallback_model(items, prompt)
                except Exception as fallback_error:
                    logger.error("Fallback model also failed", error=str(fallback_error))
            
            raise AIProviderError(f"OpenAI API error: {e}")
        
        except Exception as e:
            duration = time.time() - start_time
            await self._update_performance_metrics(model_to_use, duration, len(items), False)
            logger.error("OpenAI classification failed", error=str(e))
            raise AIProviderError(f"Classification failed: {e}")
    
    def _build_classification_prompt(self, items: List[DataItem]) -> str:
        """Build prompt for OpenAI classification"""
        prompt = """You are an expert system for classifying observability telemetry data. Analyze each item and classify it according to these rules:

CLASSIFICATION RULES:
- category: "critical" for errors, failures, alerts, high-severity issues
- category: "warning" for degraded performance, warnings, non-critical issues  
- category: "info" for normal operations, debug info, routine events

ROUTING RULES:
- forward_to: "alerting" for critical items requiring immediate attention
- forward_to: "storage" for warning items needing retention and analysis
- forward_to: "archive" for info items for long-term storage

RESPONSE FORMAT:
Return a JSON array with exactly one object per input item, in the same order:
```json
[
  {"category": "critical", "forward_to": "alerting", "confidence": 0.95},
  {"category": "info", "forward_to": "archive", "confidence": 0.85}
]
```

TELEMETRY ITEMS TO CLASSIFY:
"""
        
        for i, item in enumerate(items):
            # Truncate content to avoid token limits
            content_str = json.dumps(item.content)
            if len(content_str) > 500:
                content_str = content_str[:500] + "..."
            
            prompt += f"\n{i+1}. Type: {item.type}\n   Content: {content_str}\n"
        
        prompt += f"\nClassify these {len(items)} items and respond with the JSON array:"
        
        return prompt
    
    async def _select_optimal_model(self, items: List[DataItem]) -> str:
        """Select the optimal model based on request complexity and performance history"""
        
        # Calculate request complexity
        total_content_length = sum(len(str(item.content)) for item in items)
        item_count = len(items)
        
        # Check model performance history
        primary_model_performance = self._model_performance.get(self.config.model, {})
        fallback_model_performance = self._model_performance.get(self.config.cheaper_model, {})
        
        # Use cheaper model for simple requests or if primary model is underperforming
        if (item_count <= 5 and total_content_length < 1000) or \
           (primary_model_performance.get("error_rate", 0) > 0.1 and 
            fallback_model_performance.get("error_rate", 0) < 0.05):
            return self.config.cheaper_model
        
        return self.config.model
    
    async def _make_api_request(self, prompt: str, model: str) -> Any:
        """Make API request to OpenAI with error handling"""
        messages = [
            {
                "role": "system",
                "content": "You are a precise telemetry classification system. Always respond with valid JSON only."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                response_format={"type": "json_object"} if model.startswith("gpt-4") else None
            )
            
            # Track token usage for rate limiting
            if hasattr(response, 'usage') and response.usage:
                self._token_usage.append((time.time(), response.usage.total_tokens))
            
            # Track request time for rate limiting
            self._request_times.append(time.time())
            
            return response
            
        except Exception as e:
            logger.error("OpenAI API request failed", model=model, error=str(e))
            raise
    
    async def _parse_response(self, response: Any, expected_count: int) -> List[Dict[str, Any]]:
        """Parse and validate OpenAI response"""
        try:
            if not response.choices:
                raise ValueError("Empty response from OpenAI")
            
            content = response.choices[0].message.content
            logger.debug("OpenAI raw response", content=content)
            
            # Parse JSON response
            try:
                classifications = json.loads(content)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code blocks
                import re
                json_match = re.search(r'```(?:json)?\n(.*?)\n```', content, re.DOTALL)
                if json_match:
                    classifications = json.loads(json_match.group(1))
                else:
                    raise ValueError("No valid JSON found in response")
            
            # Validate response format
            if not isinstance(classifications, list):
                raise ValueError("Response must be a JSON array")
            
            # Ensure we have classifications for all items
            while len(classifications) < expected_count:
                # Add default classification for missing items
                classifications.append({
                    "category": "info",
                    "forward_to": "storage",
                    "confidence": 0.5
                })
            
            # Validate each classification
            valid_categories = {"critical", "warning", "info"}
            valid_destinations = {"alerting", "storage", "archive"}
            
            for i, cls in enumerate(classifications):
                if not isinstance(cls, dict):
                    classifications[i] = {"category": "info", "forward_to": "storage", "confidence": 0.5}
                    continue
                
                # Validate and fix category
                if cls.get("category") not in valid_categories:
                    cls["category"] = "info"
                
                # Validate and fix forward_to
                if cls.get("forward_to") not in valid_destinations:
                    cls["forward_to"] = "storage"
                
                # Ensure confidence is present and valid
                if "confidence" not in cls or not isinstance(cls["confidence"], (int, float)):
                    cls["confidence"] = 0.8
                else:
                    cls["confidence"] = max(0.0, min(1.0, float(cls["confidence"])))
            
            return classifications[:expected_count]  # Return only what we need
            
        except Exception as e:
            logger.error("Failed to parse OpenAI response", error=str(e))
            # Return default classifications as fallback
            return [{"category": "info", "forward_to": "storage", "confidence": 0.5} 
                   for _ in range(expected_count)]
    
    async def _retry_with_fallback_model(self, items: List[DataItem], prompt: str) -> List[SortedItem]:
        """Retry classification with fallback model"""
        logger.info("Retrying with fallback model", fallback_model=self.config.cheaper_model)
        
        response = await self._make_api_request(prompt, self.config.cheaper_model)
        classifications = await self._parse_response(response, len(items))
        
        sorted_items = []
        for i, item in enumerate(items):
            cls = classifications[i] if i < len(classifications) else {
                "category": "info", "forward_to": "storage", "confidence": 0.5
            }
            
            sorted_items.append(SortedItem(
                item=item,
                category=cls["category"],
                forward_to=cls["forward_to"],
                confidence=cls["confidence"],
                provider="openai",
                model=self.config.cheaper_model
            ))
        
        return sorted_items
    
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
        """Check OpenAI provider health"""
        if not self.client:
            return {
                "healthy": False,
                "error": "Client not initialized"
            }
        
        try:
            # Quick health check with minimal token usage
            start_time = time.time()
            
            response = await self.client.chat.completions.create(
                model=self.config.cheaper_model,  # Use cheaper model for health checks
                messages=[{"role": "user", "content": "Health check. Respond: OK"}],
                max_tokens=5,
                temperature=0
            )
            
            duration = time.time() - start_time
            
            if response.choices and response.choices[0].message.content:
                return {
                    "healthy": True,
                    "response_time_ms": duration * 1000,
                    "model": self.config.cheaper_model,
                    "performance_metrics": self._model_performance
                }
            else:
                return {
                    "healthy": False,
                    "error": "Empty response from OpenAI"
                }
                
        except Exception as e:
            logger.error("OpenAI health check failed", error=str(e))
            return {
                "healthy": False,
                "error": str(e)
            }
    
    async def get_provider_info(self) -> Dict[str, Any]:
        """Get provider information and capabilities"""
        return {
            "name": self.name,
            "type": "openai",
            "models": {
                "primary": self.config.model,
                "fallback": self.config.cheaper_model if self.config.use_cheaper_model_fallback else None
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
                "performance_tracking"
            ],
            "performance_metrics": self._model_performance
        }
    
    async def shutdown(self):
        """Shutdown provider and cleanup resources"""
        if self.client:
            await self.client.close()
            self.client = None
        
        logger.info("OpenAI provider shutdown completed")