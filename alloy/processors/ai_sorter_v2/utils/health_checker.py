"""
Health Checker for Multi-Provider AI System

Comprehensive health monitoring system for AI providers with
detailed status reporting, alerting, and recovery management.
"""

import asyncio
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class HealthCheckConfig:
    """Configuration for health checking system"""
    # Check intervals
    primary_check_interval: int = 30  # seconds
    detailed_check_interval: int = 120  # seconds for comprehensive checks
    
    # Thresholds
    response_time_threshold: float = 5.0  # seconds
    error_rate_threshold: float = 0.1  # 10% error rate
    
    # Recovery management
    recovery_attempts: int = 3
    recovery_delay: int = 60  # seconds between recovery attempts
    
    # Alerting
    alert_on_provider_failure: bool = True
    alert_on_service_degradation: bool = True
    critical_provider_threshold: int = 1  # minimum healthy providers before critical alert


class HealthChecker:
    """Comprehensive health checking system for AI providers"""
    
    def __init__(self, ai_manager, config: HealthCheckConfig):
        self.ai_manager = ai_manager
        self.config = config
        
        # Health tracking
        self._service_start_time = time.time()
        self._total_requests = 0
        self._service_health_history: List[Dict[str, Any]] = []
        
        # Background tasks
        self._health_check_task: Optional[asyncio.Task] = None
        self._detailed_check_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Alert state tracking
        self._alert_state: Dict[str, Any] = {
            "service_critical": False,
            "service_degraded": False,
            "provider_alerts": {}
        }
        
        logger.info("Health Checker initialized",
                   primary_interval=config.primary_check_interval,
                   detailed_interval=config.detailed_check_interval)
    
    async def start(self):
        """Start health checking background tasks"""
        try:
            # Start primary health checking loop
            self._health_check_task = asyncio.create_task(self._primary_health_check_loop())
            
            # Start detailed health checking loop
            self._detailed_check_task = asyncio.create_task(self._detailed_health_check_loop())
            
            logger.info("Health checking started")
            return True
            
        except Exception as e:
            logger.error("Failed to start health checking", error=str(e))
            return False
    
    async def stop(self):
        """Stop health checking"""
        logger.info("Stopping health checker")
        
        self._shutdown_event.set()
        
        # Cancel tasks
        for task in [self._health_check_task, self._detailed_check_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        logger.info("Health checker stopped")
    
    async def _primary_health_check_loop(self):
        """Primary health checking loop - basic status checks"""
        while not self._shutdown_event.is_set():
            try:
                await self._perform_primary_health_checks()
                
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.config.primary_check_interval
                )
                
            except asyncio.TimeoutError:
                continue  # Normal timeout, continue loop
            except Exception as e:
                logger.error("Primary health check error", error=str(e))
                await asyncio.sleep(10)  # Brief delay before retry
    
    async def _detailed_health_check_loop(self):
        """Detailed health checking loop - comprehensive analysis"""
        while not self._shutdown_event.is_set():
            try:
                await self._perform_detailed_health_checks()
                
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.config.detailed_check_interval
                )
                
            except asyncio.TimeoutError:
                continue  # Normal timeout, continue loop
            except Exception as e:
                logger.error("Detailed health check error", error=str(e))
                await asyncio.sleep(30)  # Longer delay for detailed checks
    
    async def _perform_primary_health_checks(self):
        """Perform basic health checks on all providers"""
        try:
            providers_info = await self.ai_manager.get_providers_info()
            
            healthy_count = 0
            total_count = len(providers_info)
            provider_statuses = {}
            
            for provider_name, provider_info in providers_info.items():
                health_data = provider_info.get("health", {})
                is_healthy = health_data.get("healthy", False)
                
                if is_healthy:
                    healthy_count += 1
                
                provider_statuses[provider_name] = {
                    "healthy": is_healthy,
                    "last_check": health_data.get("last_check"),
                    "last_error": health_data.get("last_error"),
                    "consecutive_failures": health_data.get("consecutive_failures", 0)
                }
            
            # Determine service status
            service_status = self._determine_service_status(healthy_count, total_count)
            
            # Check for alert conditions
            await self._check_alert_conditions(service_status, provider_statuses)
            
            # Log summary
            logger.debug("Primary health check completed",
                        healthy_providers=healthy_count,
                        total_providers=total_count,
                        service_status=service_status)
            
        except Exception as e:
            logger.error("Primary health check failed", error=str(e))
    
    async def _perform_detailed_health_checks(self):
        """Perform detailed health analysis and performance checks"""
        try:
            # Get comprehensive statistics
            stats = await self.ai_manager.get_statistics()
            
            # Analyze performance trends
            performance_analysis = self._analyze_performance_trends(stats)
            
            # Check for degradation patterns
            degradation_analysis = self._analyze_degradation_patterns(stats)
            
            # Update service health history
            health_record = {
                "timestamp": time.time(),
                "stats": stats,
                "performance_analysis": performance_analysis,
                "degradation_analysis": degradation_analysis
            }
            
            self._service_health_history.append(health_record)
            
            # Keep only last 24 hours of history (assuming 2-minute intervals)
            max_records = int(24 * 60 / (self.config.detailed_check_interval / 60))
            if len(self._service_health_history) > max_records:
                self._service_health_history = self._service_health_history[-max_records:]
            
            logger.debug("Detailed health check completed",
                        performance_score=performance_analysis.get("overall_score"),
                        degradation_detected=degradation_analysis.get("degradation_detected"))
            
        except Exception as e:
            logger.error("Detailed health check failed", error=str(e))
    
    def _determine_service_status(self, healthy_count: int, total_count: int) -> str:
        """Determine overall service status"""
        if healthy_count == 0:
            return "critical"
        elif healthy_count < self.config.critical_provider_threshold:
            return "critical"
        elif healthy_count < total_count:
            return "degraded"
        else:
            return "healthy"
    
    async def _check_alert_conditions(self, service_status: str, provider_statuses: Dict[str, Any]):
        """Check for alert conditions and manage alert state"""
        try:
            # Service-level alerts
            if service_status == "critical" and not self._alert_state["service_critical"]:
                await self._trigger_alert("service_critical", {
                    "message": "AI service is in critical state",
                    "service_status": service_status,
                    "provider_statuses": provider_statuses
                })
                self._alert_state["service_critical"] = True
                self._alert_state["service_degraded"] = False  # Critical overrides degraded
                
            elif service_status == "degraded" and not self._alert_state["service_degraded"] and not self._alert_state["service_critical"]:
                await self._trigger_alert("service_degraded", {
                    "message": "AI service performance is degraded",
                    "service_status": service_status,
                    "provider_statuses": provider_statuses
                })
                self._alert_state["service_degraded"] = True
                
            elif service_status == "healthy":
                # Clear service alerts if service is healthy
                if self._alert_state["service_critical"] or self._alert_state["service_degraded"]:
                    await self._trigger_alert("service_recovered", {
                        "message": "AI service has recovered to healthy state",
                        "service_status": service_status
                    })
                    self._alert_state["service_critical"] = False
                    self._alert_state["service_degraded"] = False
            
            # Provider-level alerts
            for provider_name, status in provider_statuses.items():
                if not status["healthy"] and provider_name not in self._alert_state["provider_alerts"]:
                    await self._trigger_alert("provider_failure", {
                        "message": f"Provider {provider_name} has failed",
                        "provider": provider_name,
                        "status": status
                    })
                    self._alert_state["provider_alerts"][provider_name] = True
                    
                elif status["healthy"] and provider_name in self._alert_state["provider_alerts"]:
                    await self._trigger_alert("provider_recovered", {
                        "message": f"Provider {provider_name} has recovered",
                        "provider": provider_name,
                        "status": status
                    })
                    del self._alert_state["provider_alerts"][provider_name]
            
        except Exception as e:
            logger.error("Error checking alert conditions", error=str(e))
    
    async def _trigger_alert(self, alert_type: str, alert_data: Dict[str, Any]):
        """Trigger an alert (log for now, could integrate with alerting systems)"""
        logger.warning("ALERT TRIGGERED",
                      alert_type=alert_type,
                      alert_data=alert_data,
                      timestamp=time.time())
        
        # TODO: Integrate with external alerting systems
        # - PagerDuty
        # - Slack/Teams notifications
        # - Email alerts
        # - Custom webhook endpoints
    
    def _analyze_performance_trends(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze performance trends from statistics"""
        try:
            provider_details = stats.get("provider_details", {})
            
            # Calculate overall performance metrics
            total_requests = sum(p.get("requests", 0) for p in provider_details.values())
            total_successes = sum(p.get("successes", 0) for p in provider_details.values())
            total_failures = sum(p.get("failures", 0) for p in provider_details.values())
            
            overall_success_rate = total_successes / total_requests if total_requests > 0 else 0
            overall_error_rate = total_failures / total_requests if total_requests > 0 else 0
            
            # Calculate average response time across providers
            response_times = [p.get("avg_response_time", 0) for p in provider_details.values() if p.get("avg_response_time", 0) > 0]
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0
            
            # Performance scoring (0-1, higher is better)
            success_score = overall_success_rate
            response_time_score = max(0, 1.0 - min(1.0, avg_response_time / self.config.response_time_threshold))
            error_rate_score = max(0, 1.0 - (overall_error_rate / self.config.error_rate_threshold))
            
            overall_score = (success_score + response_time_score + error_rate_score) / 3
            
            return {
                "overall_score": overall_score,
                "success_rate": overall_success_rate,
                "error_rate": overall_error_rate,
                "avg_response_time": avg_response_time,
                "total_requests": total_requests,
                "performance_status": "good" if overall_score > 0.8 else "degraded" if overall_score > 0.5 else "poor"
            }
            
        except Exception as e:
            logger.error("Error analyzing performance trends", error=str(e))
            return {"overall_score": 0, "error": str(e)}
    
    def _analyze_degradation_patterns(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze for performance degradation patterns"""
        try:
            if len(self._service_health_history) < 3:
                return {"degradation_detected": False, "reason": "Insufficient history"}
            
            # Get recent performance scores
            recent_scores = []
            for record in self._service_health_history[-5:]:  # Last 5 records
                performance = record.get("performance_analysis", {})
                score = performance.get("overall_score", 0)
                recent_scores.append(score)
            
            # Check for downward trend
            if len(recent_scores) >= 3:
                # Simple trend analysis - check if performance is consistently declining
                declining_trend = all(recent_scores[i] >= recent_scores[i+1] for i in range(len(recent_scores)-1))
                
                if declining_trend and recent_scores[-1] < 0.7:
                    return {
                        "degradation_detected": True,
                        "pattern": "declining_performance",
                        "current_score": recent_scores[-1],
                        "trend": recent_scores
                    }
            
            # Check for sudden performance drop
            current_stats = stats
            current_error_rate = current_stats.get("error_rate", 0)
            
            if current_error_rate > self.config.error_rate_threshold:
                return {
                    "degradation_detected": True,
                    "pattern": "high_error_rate",
                    "current_error_rate": current_error_rate,
                    "threshold": self.config.error_rate_threshold
                }
            
            return {"degradation_detected": False}
            
        except Exception as e:
            logger.error("Error analyzing degradation patterns", error=str(e))
            return {"degradation_detected": False, "error": str(e)}
    
    async def get_service_health(self) -> Dict[str, Any]:
        """Get comprehensive service health information"""
        try:
            uptime = time.time() - self._service_start_time
            
            # Get current statistics
            stats = await self.ai_manager.get_statistics()
            
            # Get provider statuses
            provider_statuses = await self.get_all_provider_status()
            
            # Determine overall health
            healthy_providers = sum(1 for status in provider_statuses.values() if status["healthy"])
            total_providers = len(provider_statuses)
            service_status = self._determine_service_status(healthy_providers, total_providers)
            
            return {
                "service_status": service_status,
                "uptime_seconds": uptime,
                "requests_processed": stats.get("requests_processed", 0),
                "success_rate": stats.get("success_rate", 0),
                "error_rate": stats.get("error_rate", 0),
                "providers": {
                    "total": total_providers,
                    "healthy": healthy_providers,
                    "unhealthy": total_providers - healthy_providers
                },
                "alert_state": self._alert_state,
                "last_detailed_check": self._service_health_history[-1]["timestamp"] if self._service_health_history else None
            }
            
        except Exception as e:
            logger.error("Error getting service health", error=str(e))
            return {
                "service_status": "unknown",
                "error": str(e),
                "uptime_seconds": time.time() - self._service_start_time
            }
    
    async def get_all_provider_status(self) -> Dict[str, Dict[str, Any]]:
        """Get health status for all providers"""
        try:
            providers_info = await self.ai_manager.get_providers_info()
            
            provider_statuses = {}
            for provider_name, provider_info in providers_info.items():
                health_data = provider_info.get("health", {})
                metrics_data = provider_info.get("metrics", {})
                
                provider_statuses[provider_name] = {
                    "healthy": health_data.get("healthy", False),
                    "last_check": health_data.get("last_check"),
                    "last_success": health_data.get("last_success"),
                    "last_error": health_data.get("last_error"),
                    "consecutive_failures": health_data.get("consecutive_failures", 0),
                    "total_requests": metrics_data.get("requests", 0),
                    "success_rate": 1 - metrics_data.get("error_rate", 0),
                    "avg_response_time": metrics_data.get("avg_response_time", 0),
                    "provider_type": provider_info.get("type"),
                    "models": provider_info.get("models", {})
                }
            
            return provider_statuses
            
        except Exception as e:
            logger.error("Error getting provider statuses", error=str(e))
            return {}
    
    async def check_provider_health(self, provider_name: str) -> Optional[Dict[str, Any]]:
        """Get health status for a specific provider"""
        try:
            all_statuses = await self.get_all_provider_status()
            return all_statuses.get(provider_name)
            
        except Exception as e:
            logger.error("Error checking provider health", provider=provider_name, error=str(e))
            return None
    
    async def get_health_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get health history for the specified number of hours"""
        try:
            cutoff_time = time.time() - (hours * 3600)
            
            # Filter history based on time range
            filtered_history = [
                record for record in self._service_health_history
                if record["timestamp"] >= cutoff_time
            ]
            
            return filtered_history
            
        except Exception as e:
            logger.error("Error getting health history", error=str(e))
            return []
    
    async def force_health_check(self) -> Dict[str, Any]:
        """Force an immediate comprehensive health check"""
        try:
            logger.info("Forcing immediate health check")
            
            # Perform both primary and detailed checks
            await self._perform_primary_health_checks()
            await self._perform_detailed_health_checks()
            
            # Return current health status
            return await self.get_service_health()
            
        except Exception as e:
            logger.error("Error performing forced health check", error=str(e))
            return {"error": str(e)}