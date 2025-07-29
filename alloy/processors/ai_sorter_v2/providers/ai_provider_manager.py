"""
AI Provider Manager for Multi-Provider Support

Manages multiple AI providers with intelligent failover, health checking,
and load balancing capabilities. Provides enterprise-grade reliability
and performance optimization.
"""

import asyncio
import time
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import structlog

from .base_provider import AIProvider, AIProviderError
from ..models.requests import DataItem, SortedItem, BatchRequest

logger = structlog.get_logger(__name__)


@dataclass
class AIManagerConfig:
    """Configuration for AI provider manager"""
    # Provider selection strategy
    selection_strategy: str = "health_weighted"  # health_weighted, round_robin, cost_optimized
    
    # Health checking
    health_check_interval: int = 30  # seconds
    health_check_timeout: int = 10  # seconds
    unhealthy_threshold: int = 3  # consecutive failures before marking unhealthy
    recovery_check_interval: int = 60  # seconds for checking unhealthy providers
    
    # Fallback behavior
    enable_fallback: bool = True
    max_fallback_attempts: int = 3
    fallback_timeout: int = 30  # seconds
    
    # Performance optimization
    prefer_faster_providers: bool = True
    performance_weight: float = 0.3  # weight of performance in provider selection
    cost_weight: float = 0.2  # weight of cost in provider selection
    health_weight: float = 0.5  # weight of health in provider selection
    
    # Request routing
    max_concurrent_requests: int = 100
    request_queue_timeout: int = 60


class AIProviderManager:
    """Manages multiple AI providers with intelligent failover"""
    
    def __init__(self, providers: List[AIProvider], config: AIManagerConfig):
        self.providers = {provider.name: provider for provider in providers}
        self.config = config
        
        # Provider health tracking
        self._provider_health: Dict[str, Dict[str, Any]] = {}
        self._provider_metrics: Dict[str, Dict[str, Any]] = {}
        self._current_provider_index = 0
        
        # Request management
        self._request_semaphore = asyncio.Semaphore(config.max_concurrent_requests)
        self._request_count = 0
        self._start_time = time.time()
        
        # Health checking
        self._health_check_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        logger.info("AI Provider Manager initialized",
                   providers=list(self.providers.keys()),
                   strategy=config.selection_strategy)
    
    async def initialize(self) -> bool:
        """Initialize all providers and start health checking"""
        try:
            # Initialize all providers
            initialization_results = {}
            for name, provider in self.providers.items():
                try:
                    success = await provider.initialize()
                    initialization_results[name] = success
                    
                    # Initialize health tracking
                    self._provider_health[name] = {
                        "healthy": success,
                        "consecutive_failures": 0 if success else 1,
                        "last_check": time.time(),
                        "last_success": time.time() if success else None,
                        "last_error": None if success else "Initialization failed"
                    }
                    
                    # Initialize metrics tracking
                    self._provider_metrics[name] = {
                        "requests": 0,
                        "successes": 0,
                        "failures": 0,
                        "total_duration": 0,
                        "avg_response_time": 0,
                        "last_request_time": None,
                        "error_rate": 0
                    }
                    
                except Exception as e:
                    logger.error("Failed to initialize provider",
                               provider=name, error=str(e))
                    initialization_results[name] = False
                    self._provider_health[name] = {
                        "healthy": False,
                        "consecutive_failures": 1,
                        "last_check": time.time(),
                        "last_success": None,
                        "last_error": str(e)
                    }
            
            # Check if we have at least one healthy provider
            healthy_providers = [name for name, result in initialization_results.items() if result]
            if not healthy_providers:
                logger.error("No providers initialized successfully")
                return False
            
            # Start health checking
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            
            logger.info("AI Provider Manager initialization completed",
                       healthy_providers=healthy_providers,
                       failed_providers=[name for name, result in initialization_results.items() if not result])
            
            return True
            
        except Exception as e:
            logger.error("AI Provider Manager initialization failed", error=str(e))
            return False
    
    async def sort_batch(self, batch: BatchRequest) -> List[SortedItem]:
        """Sort batch using the best available provider with fallback"""
        if not batch.items:
            return []
        
        async with self._request_semaphore:
            start_time = time.time()
            attempts = 0
            last_error = None
            
            # Get ordered list of providers to try
            provider_order = await self._get_provider_order(batch)
            
            for provider_name in provider_order:
                if attempts >= self.config.max_fallback_attempts:
                    break
                
                attempts += 1
                provider = self.providers[provider_name]
                
                try:
                    logger.debug("Attempting classification",
                               provider=provider_name,
                               attempt=attempts,
                               items_count=len(batch.items))
                    
                    # Track request start
                    await self._record_request_start(provider_name)
                    
                    # Execute classification
                    sorted_items = await asyncio.wait_for(
                        provider.classify_batch(batch.items),
                        timeout=self.config.fallback_timeout
                    )
                    
                    # Track successful request
                    duration = time.time() - start_time
                    await self._record_request_success(provider_name, duration, len(batch.items))
                    
                    logger.info("Batch classification successful",
                               provider=provider_name,
                               items_processed=len(sorted_items),
                               duration_seconds=duration,
                               attempts=attempts)
                    
                    return sorted_items
                    
                except asyncio.TimeoutError:
                    error_msg = f"Provider {provider_name} timed out"
                    logger.warning(error_msg, timeout=self.config.fallback_timeout)
                    last_error = error_msg
                    await self._record_request_failure(provider_name, time.time() - start_time, error_msg)
                    
                except AIProviderError as e:
                    error_msg = f"Provider {provider_name} error: {e}"
                    logger.warning("Provider error, trying fallback", 
                                 provider=provider_name, error=str(e))
                    last_error = error_msg
                    await self._record_request_failure(provider_name, time.time() - start_time, error_msg)
                    
                except Exception as e:
                    error_msg = f"Unexpected error with provider {provider_name}: {e}"
                    logger.error("Unexpected provider error", 
                               provider=provider_name, error=str(e))
                    last_error = error_msg
                    await self._record_request_failure(provider_name, time.time() - start_time, error_msg)
            
            # All providers failed
            total_duration = time.time() - start_time
            logger.error("All providers failed",
                        attempts=attempts,
                        duration_seconds=total_duration,
                        last_error=last_error)
            
            raise AIProviderError(f"All AI providers failed after {attempts} attempts. Last error: {last_error}")
    
    async def _get_provider_order(self, batch: BatchRequest) -> List[str]:
        """Get ordered list of providers based on selection strategy"""
        healthy_providers = [name for name, health in self._provider_health.items() 
                           if health["healthy"]]
        
        if not healthy_providers:
            # If no healthy providers, try all providers as last resort
            logger.warning("No healthy providers available, trying all providers")
            return list(self.providers.keys())
        
        if self.config.selection_strategy == "round_robin":
            # Simple round-robin selection
            self._current_provider_index = (self._current_provider_index + 1) % len(healthy_providers)
            selected = healthy_providers[self._current_provider_index]
            # Return selected provider first, then others as fallback
            fallback_providers = [p for p in healthy_providers if p != selected]
            return [selected] + fallback_providers
            
        elif self.config.selection_strategy == "cost_optimized":
            # Select based on cost efficiency (simulated based on model types)
            return sorted(healthy_providers, key=self._get_provider_cost_score)
            
        else:  # health_weighted (default)
            # Select based on weighted score of health, performance, and cost
            return sorted(healthy_providers, key=self._get_provider_weighted_score, reverse=True)
    
    def _get_provider_cost_score(self, provider_name: str) -> float:
        """Get cost score for provider (lower is better)"""
        provider = self.providers[provider_name]
        
        # Simple cost scoring based on provider type and model
        if provider_name == "openai":
            model = getattr(provider.config, 'model', 'gpt-4')
            if 'gpt-4' in model:
                return 3.0  # Higher cost
            else:
                return 1.0  # Lower cost (gpt-3.5-turbo)
        elif provider_name == "claude":
            model = getattr(provider.config, 'model', 'claude-3-sonnet')
            if 'claude-3-opus' in model:
                return 3.5  # Highest cost
            elif 'claude-3-sonnet' in model:
                return 2.0  # Medium cost
            else:
                return 1.5  # Lower cost (haiku)
        elif provider_name == "grok":
            return 2.5  # Medium-high cost
        
        return 2.0  # Default medium cost
    
    def _get_provider_weighted_score(self, provider_name: str) -> float:
        """Get weighted score for provider selection (higher is better)"""
        health_data = self._provider_health[provider_name]
        metrics_data = self._provider_metrics[provider_name]
        
        # Health score (0-1, higher is better)
        if health_data["healthy"]:
            health_score = max(0.1, 1.0 - (health_data["consecutive_failures"] * 0.2))
        else:
            health_score = 0.0
        
        # Performance score (0-1, higher is better, based on response time)
        if metrics_data["avg_response_time"] > 0:
            # Normalize response time (assume 10s is very slow, 1s is very fast)
            performance_score = max(0.1, 1.0 - min(1.0, metrics_data["avg_response_time"] / 10.0))
        else:
            performance_score = 0.5  # Default for no data
        
        # Cost score (0-1, higher is better, inverse of cost)
        cost_score_raw = self._get_provider_cost_score(provider_name)
        cost_score = max(0.1, 1.0 - (cost_score_raw / 4.0))  # Normalize to 0-1
        
        # Weighted final score
        final_score = (
            self.config.health_weight * health_score +
            self.config.performance_weight * performance_score +
            self.config.cost_weight * cost_score
        )
        
        logger.debug("Provider scoring",
                   provider=provider_name,
                   health_score=health_score,
                   performance_score=performance_score,
                   cost_score=cost_score,
                   final_score=final_score)
        
        return final_score
    
    async def _health_check_loop(self):
        """Background health checking loop"""
        while not self._shutdown_event.is_set():
            try:
                # Check all providers
                for provider_name, provider in self.providers.items():
                    if self._shutdown_event.is_set():
                        break
                        
                    await self._check_provider_health(provider_name, provider)
                
                # Wait for next check cycle
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.config.health_check_interval
                )
                
            except asyncio.TimeoutError:
                continue  # Normal timeout, continue loop
            except Exception as e:
                logger.error("Health check loop error", error=str(e))
                await asyncio.sleep(5)  # Wait before retrying
    
    async def _check_provider_health(self, provider_name: str, provider: AIProvider):
        """Check health of a specific provider"""
        try:
            start_time = time.time()
            
            # Perform health check with timeout
            health_result = await asyncio.wait_for(
                provider.health_check(),
                timeout=self.config.health_check_timeout
            )
            
            duration = time.time() - start_time
            is_healthy = health_result.get("healthy", False)
            
            # Update health status
            health_data = self._provider_health[provider_name]
            health_data["last_check"] = time.time()
            
            if is_healthy:
                health_data["healthy"] = True
                health_data["consecutive_failures"] = 0
                health_data["last_success"] = time.time()
                health_data["last_error"] = None
                
                logger.debug("Provider health check passed",
                           provider=provider_name,
                           response_time_ms=duration * 1000)
            else:
                health_data["consecutive_failures"] += 1
                health_data["last_error"] = health_result.get("error", "Health check failed")
                
                # Mark as unhealthy if threshold exceeded
                if health_data["consecutive_failures"] >= self.config.unhealthy_threshold:
                    health_data["healthy"] = False
                    logger.warning("Provider marked as unhealthy",
                                 provider=provider_name,
                                 consecutive_failures=health_data["consecutive_failures"])
            
        except asyncio.TimeoutError:
            await self._handle_health_check_failure(provider_name, "Health check timeout")
        except Exception as e:
            await self._handle_health_check_failure(provider_name, str(e))
    
    async def _handle_health_check_failure(self, provider_name: str, error: str):
        """Handle health check failure"""
        health_data = self._provider_health[provider_name]
        health_data["consecutive_failures"] += 1
        health_data["last_check"] = time.time()
        health_data["last_error"] = error
        
        if health_data["consecutive_failures"] >= self.config.unhealthy_threshold:
            health_data["healthy"] = False
            logger.warning("Provider health check failed",
                         provider=provider_name,
                         error=error,
                         consecutive_failures=health_data["consecutive_failures"])
    
    async def _record_request_start(self, provider_name: str):
        """Record the start of a request for metrics"""
        metrics = self._provider_metrics[provider_name]
        metrics["requests"] += 1
        metrics["last_request_time"] = time.time()
    
    async def _record_request_success(self, provider_name: str, duration: float, items_count: int):
        """Record successful request metrics"""
        metrics = self._provider_metrics[provider_name]
        metrics["successes"] += 1
        metrics["total_duration"] += duration
        
        # Update average response time
        metrics["avg_response_time"] = metrics["total_duration"] / metrics["requests"]
        
        # Update error rate
        metrics["error_rate"] = metrics["failures"] / metrics["requests"]
        
        # Update provider health on success
        health_data = self._provider_health[provider_name]
        health_data["healthy"] = True
        health_data["consecutive_failures"] = 0
        health_data["last_success"] = time.time()
    
    async def _record_request_failure(self, provider_name: str, duration: float, error: str):
        """Record failed request metrics"""
        metrics = self._provider_metrics[provider_name]
        metrics["failures"] += 1
        metrics["total_duration"] += duration
        
        # Update average response time
        metrics["avg_response_time"] = metrics["total_duration"] / metrics["requests"]
        
        # Update error rate
        metrics["error_rate"] = metrics["failures"] / metrics["requests"]
        
        # Update provider health on failure
        health_data = self._provider_health[provider_name]
        health_data["consecutive_failures"] += 1
        health_data["last_error"] = error
        
        # Mark as unhealthy if threshold exceeded
        if health_data["consecutive_failures"] >= self.config.unhealthy_threshold:
            health_data["healthy"] = False
    
    async def get_current_provider_name(self) -> Optional[str]:
        """Get the name of the currently preferred provider"""
        healthy_providers = [name for name, health in self._provider_health.items() 
                           if health["healthy"]]
        
        if not healthy_providers:
            return None
        
        # Return the first provider from the current ordering
        provider_order = await self._get_provider_order(BatchRequest(items=[]))
        return provider_order[0] if provider_order else None
    
    async def get_providers_info(self) -> Dict[str, Any]:
        """Get information about all providers"""
        providers_info = {}
        
        for name, provider in self.providers.items():
            try:
                provider_info = await provider.get_provider_info()
                provider_info["health"] = self._provider_health[name]
                provider_info["metrics"] = self._provider_metrics[name]
                providers_info[name] = provider_info
            except Exception as e:
                logger.error("Error getting provider info", provider=name, error=str(e))
                providers_info[name] = {
                    "name": name,
                    "error": str(e),
                    "health": self._provider_health.get(name, {}),
                    "metrics": self._provider_metrics.get(name, {})
                }
        
        return providers_info
    
    async def test_provider(self, provider_name: str, test_item: DataItem) -> Dict[str, Any]:
        """Test a specific provider with a test item"""
        if provider_name not in self.providers:
            raise ValueError(f"Provider '{provider_name}' not found")
        
        provider = self.providers[provider_name]
        
        try:
            start_time = time.time()
            result = await provider.classify_batch([test_item])
            duration = time.time() - start_time
            
            return {
                "success": True,
                "result": result[0] if result else None,
                "response_time_seconds": duration,
                "provider_info": await provider.get_provider_info()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "provider_info": await provider.get_provider_info()
            }
    
    async def trigger_manual_failover(self) -> bool:
        """Manually trigger failover to next available provider"""
        healthy_providers = [name for name, health in self._provider_health.items() 
                           if health["healthy"]]
        
        if len(healthy_providers) <= 1:
            return False  # No alternative providers available
        
        # Force rotation to next provider
        self._current_provider_index = (self._current_provider_index + 1) % len(healthy_providers)
        
        logger.info("Manual failover triggered",
                   new_provider_index=self._current_provider_index,
                   available_providers=healthy_providers)
        
        return True
    
    @property
    def fallback_enabled(self) -> bool:
        """Check if fallback is enabled"""
        return self.config.enable_fallback
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive service statistics"""
        uptime = time.time() - self._start_time
        
        # Aggregate metrics across all providers
        total_requests = sum(metrics["requests"] for metrics in self._provider_metrics.values())
        total_successes = sum(metrics["successes"] for metrics in self._provider_metrics.values())
        total_failures = sum(metrics["failures"] for metrics in self._provider_metrics.values())
        
        healthy_providers = [name for name, health in self._provider_health.items() 
                           if health["healthy"]]
        
        return {
            "uptime_seconds": uptime,
            "requests_processed": total_requests,
            "success_rate": total_successes / total_requests if total_requests > 0 else 0,
            "error_rate": total_failures / total_requests if total_requests > 0 else 0,
            "providers": {
                "total": len(self.providers),
                "healthy": len(healthy_providers),
                "unhealthy": len(self.providers) - len(healthy_providers)
            },
            "provider_details": self._provider_metrics,
            "health_status": self._provider_health,
            "configuration": {
                "selection_strategy": self.config.selection_strategy,
                "fallback_enabled": self.config.enable_fallback,
                "max_concurrent_requests": self.config.max_concurrent_requests
            }
        }
    
    async def shutdown(self):
        """Shutdown the provider manager and all providers"""
        logger.info("Shutting down AI Provider Manager")
        
        # Stop health checking
        self._shutdown_event.set()
        if self._health_check_task:
            try:
                await asyncio.wait_for(self._health_check_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._health_check_task.cancel()
        
        # Shutdown all providers
        for name, provider in self.providers.items():
            try:
                await provider.shutdown()
                logger.debug("Provider shutdown completed", provider=name)
            except Exception as e:
                logger.error("Error shutting down provider", provider=name, error=str(e))
        
        logger.info("AI Provider Manager shutdown completed")