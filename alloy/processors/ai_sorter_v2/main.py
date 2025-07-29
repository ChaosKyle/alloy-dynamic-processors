#!/usr/bin/env python3
"""
Multi-Provider AI Sorter Service

Enhanced version with support for multiple AI providers (OpenAI, Claude, Grok),
intelligent fallback mechanisms, health checking, and comprehensive monitoring.
"""

import asyncio
import os
import time
from typing import List, Dict, Optional, Any
from contextlib import asynccontextmanager
import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from pydantic import BaseModel, Field

from providers.ai_provider_manager import AIProviderManager
from providers.openai_provider import OpenAIProvider
from providers.claude_provider import ClaudeProvider
from providers.grok_provider import GrokProvider
from config.settings import Settings
from models.requests import BatchRequest, DataItem, SortedItem
from utils.health_checker import HealthChecker
from utils.metrics import MetricsCollector


# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Prometheus metrics
requests_total = Counter(
    'ai_sorter_requests_total',
    'Total AI sorting requests',
    ['provider', 'status']
)

request_duration = Histogram(
    'ai_sorter_request_duration_seconds',
    'AI sorting request duration',
    ['provider']
)

provider_health = Gauge(
    'ai_sorter_provider_health',
    'AI provider health status (1=healthy, 0=unhealthy)',
    ['provider']
)

active_providers = Gauge(
    'ai_sorter_active_providers',
    'Number of active AI providers'
)

fallback_usage = Counter(
    'ai_sorter_fallback_usage_total',
    'Number of times fallback was used',
    ['from_provider', 'to_provider']
)

# Global instances
settings = Settings()
ai_manager: Optional[AIProviderManager] = None
health_checker: Optional[HealthChecker] = None
metrics_collector: Optional[MetricsCollector] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global ai_manager, health_checker, metrics_collector
    
    try:
        logger.info("Starting Multi-Provider AI Sorter Service")
        
        # Initialize metrics collector
        metrics_collector = MetricsCollector()
        
        # Initialize AI providers
        providers = []
        
        # Add OpenAI provider if configured
        if settings.openai.enabled and settings.openai.api_key:
            openai_provider = OpenAIProvider(settings.openai)
            providers.append(openai_provider)
            logger.info("OpenAI provider initialized")
        
        # Add Claude provider if configured
        if settings.claude.enabled and settings.claude.api_key:
            claude_provider = ClaudeProvider(settings.claude)
            providers.append(claude_provider)
            logger.info("Claude provider initialized")
        
        # Add Grok provider if configured
        if settings.grok.enabled and settings.grok.api_key:
            grok_provider = GrokProvider(settings.grok)
            providers.append(grok_provider)
            logger.info("Grok provider initialized")
        
        if not providers:
            raise ValueError("No AI providers configured")
        
        # Initialize AI provider manager
        ai_manager = AIProviderManager(providers, settings.ai_manager)
        await ai_manager.initialize()
        
        # Initialize health checker
        health_checker = HealthChecker(ai_manager, settings.health_check)
        await health_checker.start()
        
        # Start background tasks
        asyncio.create_task(update_metrics_loop())
        
        logger.info("Multi-Provider AI Sorter Service started successfully",
                   providers=[p.name for p in providers])
        
        yield
        
    except Exception as e:
        logger.error("Failed to start AI sorter service", error=str(e))
        raise
    finally:
        logger.info("Shutting down Multi-Provider AI Sorter Service")
        if health_checker:
            await health_checker.stop()
        if ai_manager:
            await ai_manager.shutdown()


# Create FastAPI app
app = FastAPI(
    title="Multi-Provider AI Sorter",
    description="Enterprise AI-driven intelligent sorting with multiple provider support",
    version="2.3.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def update_metrics_loop():
    """Background task to update Prometheus metrics"""
    while True:
        try:
            if ai_manager and health_checker:
                # Update provider health metrics
                provider_statuses = await health_checker.get_all_provider_status()
                for provider_name, status in provider_statuses.items():
                    provider_health.labels(provider=provider_name).set(1 if status["healthy"] else 0)
                
                # Update active providers count
                healthy_count = sum(1 for status in provider_statuses.values() if status["healthy"])
                active_providers.set(healthy_count)
                
                logger.debug("Metrics updated", 
                           healthy_providers=healthy_count,
                           total_providers=len(provider_statuses))
            
            await asyncio.sleep(30)  # Update every 30 seconds
            
        except Exception as e:
            logger.error("Error updating metrics", error=str(e))
            await asyncio.sleep(60)  # Wait longer on error


@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint"""
    try:
        if not ai_manager or not health_checker:
            return {"status": "unhealthy", "reason": "Service not initialized"}
        
        # Get overall service health
        service_health = await health_checker.get_service_health()
        
        # Get individual provider status
        provider_statuses = await health_checker.get_all_provider_status()
        
        # Determine overall status
        healthy_providers = sum(1 for status in provider_statuses.values() if status["healthy"])
        total_providers = len(provider_statuses)
        
        if healthy_providers == 0:
            overall_status = "critical"
        elif healthy_providers < total_providers:
            overall_status = "degraded"
        else:
            overall_status = "healthy"
        
        return {
            "status": overall_status,
            "service": "multi-provider-ai-sorter",
            "version": "2.3.0",
            "providers": {
                "total": total_providers,
                "healthy": healthy_providers,
                "details": provider_statuses
            },
            "uptime_seconds": service_health.get("uptime_seconds", 0),
            "requests_processed": service_health.get("requests_processed", 0)
        }
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return {"status": "unhealthy", "error": str(e)}


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest()


@app.get("/providers")
async def list_providers():
    """List all configured AI providers and their status"""
    if not ai_manager:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        providers_info = await ai_manager.get_providers_info()
        return {
            "providers": providers_info,
            "active_provider": await ai_manager.get_current_provider_name(),
            "fallback_enabled": ai_manager.fallback_enabled
        }
    except Exception as e:
        logger.error("Error listing providers", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve provider information")


@app.post("/sort", response_model=List[SortedItem])
async def sort_data(batch: BatchRequest, background_tasks: BackgroundTasks):
    """
    Sort and classify telemetry data using multi-provider AI with intelligent fallback
    """
    if not ai_manager:
        raise HTTPException(status_code=503, detail="AI service not initialized")
    
    if not batch.items:
        return []
    
    start_time = time.time()
    provider_used = None
    
    try:
        logger.info("Processing AI sorting request", 
                   items_count=len(batch.items),
                   request_id=batch.request_id)
        
        # Process the batch through AI provider manager
        sorted_items = await ai_manager.sort_batch(batch)
        provider_used = await ai_manager.get_current_provider_name()
        
        # Record successful request metrics
        duration = time.time() - start_time
        requests_total.labels(provider=provider_used, status="success").inc()
        request_duration.labels(provider=provider_used).observe(duration)
        
        # Update metrics in background
        background_tasks.add_task(
            metrics_collector.record_request,
            provider_used,
            duration,
            len(batch.items),
            True
        )
        
        logger.info("AI sorting completed successfully",
                   items_processed=len(sorted_items),
                   provider_used=provider_used,
                   duration_seconds=duration,
                   request_id=batch.request_id)
        
        return sorted_items
        
    except Exception as e:
        # Record failed request metrics
        duration = time.time() - start_time
        provider_name = provider_used or "unknown"
        requests_total.labels(provider=provider_name, status="error").inc()
        
        # Update metrics in background
        background_tasks.add_task(
            metrics_collector.record_request,
            provider_name,
            duration,
            len(batch.items),
            False
        )
        
        logger.error("AI sorting failed",
                   error=str(e),
                   provider_used=provider_used,
                   duration_seconds=duration,
                   request_id=batch.request_id)
        
        # Return a generic error to avoid exposing internal details
        raise HTTPException(
            status_code=500,
            detail="AI sorting service temporarily unavailable"
        )


@app.post("/sort/single")
async def sort_single_item(item: DataItem):
    """Sort a single data item (convenience endpoint)"""
    batch = BatchRequest(items=[item])
    results = await sort_data(batch, BackgroundTasks())
    return results[0] if results else None


@app.get("/providers/{provider_name}/health")
async def check_provider_health(provider_name: str):
    """Check health of a specific provider"""
    if not health_checker:
        raise HTTPException(status_code=503, detail="Health checker not initialized")
    
    try:
        status = await health_checker.check_provider_health(provider_name)
        if status is None:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
        
        return status
    except Exception as e:
        logger.error("Error checking provider health", provider=provider_name, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to check provider health")


@app.post("/providers/{provider_name}/test")
async def test_provider(provider_name: str):
    """Test a specific provider with a sample request"""
    if not ai_manager:
        raise HTTPException(status_code=503, detail="AI manager not initialized")
    
    try:
        # Create a test data item
        test_item = DataItem(
            type="test",
            content={
                "message": "This is a test message for AI provider testing",
                "level": "info",
                "timestamp": time.time()
            }
        )
        
        # Test the specific provider
        result = await ai_manager.test_provider(provider_name, test_item)
        
        return {
            "provider": provider_name,
            "test_successful": True,
            "result": result,
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error("Provider test failed", provider=provider_name, error=str(e))
        return {
            "provider": provider_name,
            "test_successful": False,
            "error": str(e),
            "timestamp": time.time()
        }


@app.post("/admin/failover")
async def trigger_failover():
    """Manually trigger failover to next available provider (admin endpoint)"""
    if not ai_manager:
        raise HTTPException(status_code=503, detail="AI manager not initialized")
    
    try:
        old_provider = await ai_manager.get_current_provider_name()
        success = await ai_manager.trigger_manual_failover()
        
        if success:
            new_provider = await ai_manager.get_current_provider_name()
            logger.info("Manual failover triggered", 
                       from_provider=old_provider,
                       to_provider=new_provider)
            
            # Record fallback usage
            fallback_usage.labels(from_provider=old_provider, to_provider=new_provider).inc()
            
            return {
                "success": True,
                "from_provider": old_provider,
                "to_provider": new_provider
            }
        else:
            return {
                "success": False,
                "reason": "No healthy providers available for failover"
            }
            
    except Exception as e:
        logger.error("Manual failover failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failover operation failed")


@app.get("/stats")
async def get_statistics():
    """Get service statistics and performance metrics"""
    if not metrics_collector:
        raise HTTPException(status_code=503, detail="Metrics collector not initialized")
    
    try:
        stats = await metrics_collector.get_statistics()
        return stats
    except Exception as e:
        logger.error("Error retrieving statistics", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")


if __name__ == "__main__":
    # Run the application
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_config=None,  # Use structlog configuration
        access_log=False  # Disable uvicorn access logs
    )