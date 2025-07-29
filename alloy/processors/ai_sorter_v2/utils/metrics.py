"""
Metrics Collection and Analysis for Multi-Provider AI System

Comprehensive metrics collection, analysis, and reporting system
for performance monitoring, cost tracking, and operational insights.
"""

import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict, deque
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class MetricRecord:
    """Individual metric record"""
    timestamp: float
    provider: str
    duration: float
    items_count: int
    success: bool
    error_message: Optional[str] = None


@dataclass
class MetricsConfig:
    """Configuration for metrics collection"""
    # Data retention
    max_records: int = 10000  # Maximum number of records to keep in memory
    retention_hours: int = 24  # Hours of data to retain
    
    # Aggregation windows
    minute_window: int = 60  # seconds
    hour_window: int = 3600  # seconds
    
    # Performance thresholds
    slow_request_threshold: float = 5.0  # seconds
    high_error_rate_threshold: float = 0.1  # 10%
    
    # Cost tracking (estimated costs per 1k tokens)
    cost_per_1k_tokens: Dict[str, float] = field(default_factory=lambda: {
        "openai_gpt4": 0.03,
        "openai_gpt35": 0.002,
        "claude_opus": 0.015,
        "claude_sonnet": 0.003,
        "claude_haiku": 0.0005,
        "grok": 0.01
    })


class MetricsCollector:
    """Comprehensive metrics collection and analysis system"""
    
    def __init__(self, config: Optional[MetricsConfig] = None):
        self.config = config or MetricsConfig()
        
        # Raw metrics storage
        self._raw_records: deque = deque(maxlen=self.config.max_records)
        
        # Aggregated metrics
        self._minute_aggregates: Dict[int, Dict[str, Any]] = {}
        self._hour_aggregates: Dict[int, Dict[str, Any]] = {}
        
        # Performance tracking
        self._provider_performance: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_duration": 0.0,
            "total_items": 0,
            "slow_requests": 0,
            "avg_response_time": 0.0,
            "success_rate": 0.0,
            "error_rate": 0.0,
            "throughput_items_per_second": 0.0,
            "estimated_cost": 0.0
        })
        
        # System metrics
        self._system_metrics = {
            "start_time": time.time(),
            "total_requests": 0,
            "total_items_processed": 0,
            "uptime": 0.0
        }
        
        logger.info("Metrics collector initialized",
                   max_records=self.config.max_records,
                   retention_hours=self.config.retention_hours)
    
    async def record_request(self, provider: str, duration: float, 
                           items_count: int, success: bool, 
                           error_message: Optional[str] = None):
        """Record a single request metric"""
        try:
            timestamp = time.time()
            
            # Create metric record
            record = MetricRecord(
                timestamp=timestamp,
                provider=provider,
                duration=duration,
                items_count=items_count,
                success=success,
                error_message=error_message
            )
            
            # Store raw record
            self._raw_records.append(record)
            
            # Update real-time aggregates
            await self._update_provider_metrics(record)
            await self._update_system_metrics(record)
            await self._update_time_based_aggregates(record)
            
            # Clean old data periodically
            if len(self._raw_records) % 100 == 0:  # Every 100 records
                await self._cleanup_old_data()
            
            logger.debug("Request metric recorded",
                        provider=provider,
                        duration=duration,
                        items_count=items_count,
                        success=success)
            
        except Exception as e:
            logger.error("Error recording request metric", error=str(e))
    
    async def _update_provider_metrics(self, record: MetricRecord):
        """Update provider-specific metrics"""
        try:
            metrics = self._provider_performance[record.provider]
            
            # Update counters
            metrics["total_requests"] += 1
            metrics["total_items"] += record.items_count
            metrics["total_duration"] += record.duration
            
            if record.success:
                metrics["successful_requests"] += 1
            else:
                metrics["failed_requests"] += 1
            
            # Check for slow requests
            if record.duration > self.config.slow_request_threshold:
                metrics["slow_requests"] += 1
            
            # Calculate derived metrics
            metrics["avg_response_time"] = metrics["total_duration"] / metrics["total_requests"]
            metrics["success_rate"] = metrics["successful_requests"] / metrics["total_requests"]
            metrics["error_rate"] = metrics["failed_requests"] / metrics["total_requests"]
            
            # Calculate throughput (items per second over last hour)
            if metrics["total_duration"] > 0:
                metrics["throughput_items_per_second"] = metrics["total_items"] / metrics["total_duration"]
            
            # Estimate cost (simplified estimation)
            estimated_tokens = record.items_count * 200  # Rough estimate: 200 tokens per item
            cost_key = self._get_cost_key(record.provider)
            cost_per_token = self.config.cost_per_1k_tokens.get(cost_key, 0.01) / 1000
            metrics["estimated_cost"] += estimated_tokens * cost_per_token
            
        except Exception as e:
            logger.error("Error updating provider metrics", provider=record.provider, error=str(e))
    
    async def _update_system_metrics(self, record: MetricRecord):
        """Update system-wide metrics"""
        try:
            self._system_metrics["total_requests"] += 1
            self._system_metrics["total_items_processed"] += record.items_count
            self._system_metrics["uptime"] = time.time() - self._system_metrics["start_time"]
            
        except Exception as e:
            logger.error("Error updating system metrics", error=str(e))
    
    async def _update_time_based_aggregates(self, record: MetricRecord):
        """Update time-based aggregate metrics"""
        try:
            current_time = int(record.timestamp)
            
            # Minute aggregates
            minute_key = current_time // 60
            if minute_key not in self._minute_aggregates:
                self._minute_aggregates[minute_key] = self._create_empty_aggregate()
            
            self._update_aggregate(self._minute_aggregates[minute_key], record)
            
            # Hour aggregates
            hour_key = current_time // 3600
            if hour_key not in self._hour_aggregates:
                self._hour_aggregates[hour_key] = self._create_empty_aggregate()
            
            self._update_aggregate(self._hour_aggregates[hour_key], record)
            
        except Exception as e:
            logger.error("Error updating time-based aggregates", error=str(e))
    
    def _create_empty_aggregate(self) -> Dict[str, Any]:
        """Create empty aggregate structure"""
        return {
            "requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_duration": 0.0,
            "total_items": 0,
            "providers": defaultdict(int),
            "errors": defaultdict(int),
            "avg_response_time": 0.0,
            "success_rate": 0.0,
            "throughput": 0.0
        }
    
    def _update_aggregate(self, aggregate: Dict[str, Any], record: MetricRecord):
        """Update an aggregate with a new record"""
        aggregate["requests"] += 1
        aggregate["total_duration"] += record.duration
        aggregate["total_items"] += record.items_count
        aggregate["providers"][record.provider] += 1
        
        if record.success:
            aggregate["successful_requests"] += 1
        else:
            aggregate["failed_requests"] += 1
            if record.error_message:
                aggregate["errors"][record.error_message] += 1
        
        # Recalculate derived metrics
        aggregate["avg_response_time"] = aggregate["total_duration"] / aggregate["requests"]
        aggregate["success_rate"] = aggregate["successful_requests"] / aggregate["requests"]
        aggregate["throughput"] = aggregate["total_items"] / aggregate["total_duration"] if aggregate["total_duration"] > 0 else 0
    
    def _get_cost_key(self, provider: str) -> str:
        """Get cost key for provider"""
        # This is a simplified mapping - in practice, would need more sophisticated logic
        if "openai" in provider.lower():
            return "openai_gpt4"  # Default to higher cost model
        elif "claude" in provider.lower():
            return "claude_sonnet"  # Default to medium cost model
        elif "grok" in provider.lower():
            return "grok"
        else:
            return "openai_gpt4"  # Conservative default
    
    async def _cleanup_old_data(self):
        """Clean up old data based on retention policy"""
        try:
            cutoff_time = time.time() - (self.config.retention_hours * 3600)
            
            # Clean minute aggregates
            old_minute_keys = [key for key in self._minute_aggregates.keys() 
                             if key * 60 < cutoff_time]
            for key in old_minute_keys:
                del self._minute_aggregates[key]
            
            # Clean hour aggregates
            old_hour_keys = [key for key in self._hour_aggregates.keys() 
                           if key * 3600 < cutoff_time]
            for key in old_hour_keys:
                del self._hour_aggregates[key]
            
            if old_minute_keys or old_hour_keys:
                logger.debug("Cleaned old metrics data",
                           minute_keys_removed=len(old_minute_keys),
                           hour_keys_removed=len(old_hour_keys))
            
        except Exception as e:
            logger.error("Error cleaning old data", error=str(e))
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        try:
            current_time = time.time()
            
            # Overall statistics
            overall_stats = {
                "uptime_seconds": self._system_metrics["uptime"],
                "total_requests": self._system_metrics["total_requests"],
                "total_items_processed": self._system_metrics["total_items_processed"],
                "requests_per_second": 0,
                "items_per_second": 0
            }
            
            # Calculate rates
            if self._system_metrics["uptime"] > 0:
                overall_stats["requests_per_second"] = self._system_metrics["total_requests"] / self._system_metrics["uptime"]
                overall_stats["items_per_second"] = self._system_metrics["total_items_processed"] / self._system_metrics["uptime"]
            
            # Provider statistics
            provider_stats = {}
            total_cost = 0
            for provider, metrics in self._provider_performance.items():
                provider_stats[provider] = dict(metrics)
                total_cost += metrics["estimated_cost"]
            
            # Recent performance (last hour)
            recent_performance = await self._get_recent_performance()
            
            # Error analysis
            error_analysis = await self._analyze_errors()
            
            return {
                "timestamp": current_time,
                "overall": overall_stats,
                "providers": provider_stats,
                "recent_performance": recent_performance,
                "error_analysis": error_analysis,
                "cost_estimate": {
                    "total_estimated_cost": total_cost,
                    "cost_by_provider": {
                        provider: metrics["estimated_cost"] 
                        for provider, metrics in self._provider_performance.items()
                    }
                },
                "data_points": len(self._raw_records)
            }
            
        except Exception as e:
            logger.error("Error getting statistics", error=str(e))
            return {"error": str(e), "timestamp": time.time()}
    
    async def _get_recent_performance(self, hours: int = 1) -> Dict[str, Any]:
        """Get performance metrics for recent time period"""
        try:
            cutoff_time = time.time() - (hours * 3600)
            
            # Filter recent records
            recent_records = [r for r in self._raw_records if r.timestamp >= cutoff_time]
            
            if not recent_records:
                return {"no_data": True, "time_period_hours": hours}
            
            # Calculate recent metrics
            total_requests = len(recent_records)
            successful_requests = sum(1 for r in recent_records if r.success)
            total_duration = sum(r.duration for r in recent_records)
            total_items = sum(r.items_count for r in recent_records)
            
            # Provider breakdown
            provider_breakdown = defaultdict(lambda: {"requests": 0, "successes": 0, "duration": 0})
            for record in recent_records:
                provider_breakdown[record.provider]["requests"] += 1
                if record.success:
                    provider_breakdown[record.provider]["successes"] += 1
                provider_breakdown[record.provider]["duration"] += record.duration
            
            return {
                "time_period_hours": hours,
                "total_requests": total_requests,
                "success_rate": successful_requests / total_requests if total_requests > 0 else 0,
                "avg_response_time": total_duration / total_requests if total_requests > 0 else 0,
                "throughput_items_per_hour": total_items / hours if hours > 0 else 0,
                "provider_breakdown": dict(provider_breakdown)
            }
            
        except Exception as e:
            logger.error("Error getting recent performance", error=str(e))
            return {"error": str(e)}
    
    async def _analyze_errors(self) -> Dict[str, Any]:
        """Analyze error patterns and frequencies"""
        try:
            # Get recent errors (last 24 hours)
            cutoff_time = time.time() - (24 * 3600)
            recent_errors = [r for r in self._raw_records 
                           if not r.success and r.timestamp >= cutoff_time]
            
            if not recent_errors:
                return {"no_errors": True, "time_period_hours": 24}
            
            # Error frequency by provider
            errors_by_provider = defaultdict(int)
            for error_record in recent_errors:
                errors_by_provider[error_record.provider] += 1
            
            # Error types
            error_types = defaultdict(int)
            for error_record in recent_errors:
                if error_record.error_message:
                    # Categorize errors (simplified)
                    error_msg = error_record.error_message.lower()
                    if "timeout" in error_msg:
                        error_types["timeout"] += 1
                    elif "rate limit" in error_msg:
                        error_types["rate_limit"] += 1
                    elif "api" in error_msg:
                        error_types["api_error"] += 1
                    else:
                        error_types["other"] += 1
            
            # Error rate trends (hourly)
            hourly_error_rates = {}
            current_hour = int(time.time()) // 3600
            for i in range(24):  # Last 24 hours
                hour_key = current_hour - i
                if hour_key in self._hour_aggregates:
                    aggregate = self._hour_aggregates[hour_key]
                    error_rate = aggregate["failed_requests"] / aggregate["requests"] if aggregate["requests"] > 0 else 0
                    hourly_error_rates[hour_key] = error_rate
            
            return {
                "time_period_hours": 24,
                "total_errors": len(recent_errors),
                "errors_by_provider": dict(errors_by_provider),
                "error_types": dict(error_types),
                "hourly_error_rates": hourly_error_rates,
                "overall_error_rate": len(recent_errors) / len([r for r in self._raw_records if r.timestamp >= cutoff_time]) if self._raw_records else 0
            }
            
        except Exception as e:
            logger.error("Error analyzing errors", error=str(e))
            return {"error": str(e)}
    
    async def get_provider_metrics(self, provider: str) -> Optional[Dict[str, Any]]:
        """Get detailed metrics for a specific provider"""
        try:
            if provider not in self._provider_performance:
                return None
            
            base_metrics = dict(self._provider_performance[provider])
            
            # Add recent performance data
            recent_records = [r for r in self._raw_records 
                            if r.provider == provider and r.timestamp >= time.time() - 3600]
            
            if recent_records:
                recent_success_rate = sum(1 for r in recent_records if r.success) / len(recent_records)
                recent_avg_time = sum(r.duration for r in recent_records) / len(recent_records)
                
                base_metrics["recent_hour"] = {
                    "requests": len(recent_records),
                    "success_rate": recent_success_rate,
                    "avg_response_time": recent_avg_time
                }
            
            return base_metrics
            
        except Exception as e:
            logger.error("Error getting provider metrics", provider=provider, error=str(e))
            return None
    
    async def get_performance_summary(self, time_window_hours: int = 1) -> Dict[str, Any]:
        """Get performance summary for specified time window"""
        try:
            cutoff_time = time.time() - (time_window_hours * 3600)
            window_records = [r for r in self._raw_records if r.timestamp >= cutoff_time]
            
            if not window_records:
                return {"no_data": True, "time_window_hours": time_window_hours}
            
            # Calculate summary metrics
            total_requests = len(window_records)
            successful_requests = sum(1 for r in window_records if r.success)
            total_items = sum(r.items_count for r in window_records)
            total_duration = sum(r.duration for r in window_records)
            
            # Performance indicators
            success_rate = successful_requests / total_requests
            avg_response_time = total_duration / total_requests
            throughput = total_items / (time_window_hours * 3600) if time_window_hours > 0 else 0
            
            # Performance rating
            performance_rating = "excellent"
            if success_rate < 0.95 or avg_response_time > self.config.slow_request_threshold:
                performance_rating = "good"
            if success_rate < 0.90 or avg_response_time > self.config.slow_request_threshold * 2:
                performance_rating = "fair"
            if success_rate < 0.80 or avg_response_time > self.config.slow_request_threshold * 3:
                performance_rating = "poor"
            
            return {
                "time_window_hours": time_window_hours,
                "total_requests": total_requests,
                "success_rate": success_rate,
                "avg_response_time_seconds": avg_response_time,
                "throughput_items_per_second": throughput,
                "performance_rating": performance_rating,
                "items_processed": total_items
            }
            
        except Exception as e:
            logger.error("Error getting performance summary", error=str(e))
            return {"error": str(e)}
    
    def reset_metrics(self):
        """Reset all metrics (useful for testing or maintenance)"""
        logger.warning("Resetting all metrics data")
        
        self._raw_records.clear()
        self._minute_aggregates.clear()
        self._hour_aggregates.clear()
        self._provider_performance.clear()
        
        self._system_metrics = {
            "start_time": time.time(),
            "total_requests": 0,
            "total_items_processed": 0,
            "uptime": 0.0
        }