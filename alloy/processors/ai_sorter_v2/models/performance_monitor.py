"""
Performance Monitoring for AI Model Versions

Advanced performance monitoring system for tracking model performance,
detecting degradation, and triggering automated responses.
"""

import asyncio
import time
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from collections import deque
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PerformanceThreshold:
    """Performance threshold configuration"""
    metric_name: str
    threshold_value: float
    operator: str = "greater_than"  # greater_than, less_than, equals
    severity: str = "warning"  # info, warning, critical
    duration_minutes: int = 5  # How long threshold must be breached
    action: str = "alert"  # alert, rollback, scale


@dataclass
class PerformanceAlert:
    """Performance alert"""
    alert_id: str
    model_name: str
    model_version: str
    metric_name: str
    threshold: PerformanceThreshold
    current_value: float
    triggered_at: float
    resolved_at: Optional[float] = None
    actions_taken: List[str] = field(default_factory=list)
    
    @property
    def is_active(self) -> bool:
        """Check if alert is still active"""
        return self.resolved_at is None
    
    @property
    def duration_minutes(self) -> float:
        """Get alert duration in minutes"""
        end_time = self.resolved_at or time.time()
        return (end_time - self.triggered_at) / 60
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary"""
        return {
            "alert_id": self.alert_id,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "metric_name": self.metric_name,
            "threshold_value": self.threshold.threshold_value,
            "threshold_operator": self.threshold.operator,
            "severity": self.threshold.severity,
            "current_value": self.current_value,
            "triggered_at": self.triggered_at,
            "resolved_at": self.resolved_at,
            "is_active": self.is_active,
            "duration_minutes": self.duration_minutes,
            "actions_taken": self.actions_taken
        }


@dataclass
class PerformanceBaseline:
    """Performance baseline for comparison"""
    model_name: str
    metric_name: str
    baseline_value: float
    baseline_std: float
    confidence_interval: Tuple[float, float]
    sample_size: int
    calculated_at: float
    
    def is_anomaly(self, value: float, sensitivity: float = 2.0) -> bool:
        """Check if value is anomalous compared to baseline"""
        return abs(value - self.baseline_value) > (sensitivity * self.baseline_std)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert baseline to dictionary"""
        return {
            "model_name": self.model_name,
            "metric_name": self.metric_name,
            "baseline_value": self.baseline_value,
            "baseline_std": self.baseline_std,
            "confidence_interval": list(self.confidence_interval),
            "sample_size": self.sample_size,
            "calculated_at": self.calculated_at
        }


class ModelPerformanceMonitor:
    """Advanced performance monitoring for AI models"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # Performance data storage
        self._performance_data: Dict[str, deque] = {}  # model_version -> deque of metrics
        self._baselines: Dict[str, PerformanceBaseline] = {}  # model_name:metric -> baseline
        self._thresholds: Dict[str, List[PerformanceThreshold]] = {}  # model_name -> thresholds
        self._active_alerts: Dict[str, PerformanceAlert] = {}  # alert_id -> alert
        self._alert_history: List[PerformanceAlert] = []
        
        # Callback functions for actions
        self._alert_callbacks: List[Callable] = []
        self._rollback_callbacks: List[Callable] = []
        
        # Background tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._baseline_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Configuration
        self.data_retention_hours = self.config.get("data_retention_hours", 168)  # 1 week
        self.monitoring_interval_seconds = self.config.get("monitoring_interval_seconds", 60)
        self.baseline_calculation_interval_hours = self.config.get("baseline_calculation_interval_hours", 24)
        self.anomaly_sensitivity = self.config.get("anomaly_sensitivity", 2.0)
        
        logger.info("Model Performance Monitor initialized",
                   data_retention_hours=self.data_retention_hours,
                   monitoring_interval_seconds=self.monitoring_interval_seconds)
    
    async def start(self):
        """Start monitoring tasks"""
        try:
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())
            self._baseline_task = asyncio.create_task(self._baseline_calculation_loop())
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            
            logger.info("Model Performance Monitor started")
            
        except Exception as e:
            logger.error("Error starting performance monitor", error=str(e))
            raise
    
    async def stop(self):
        """Stop monitoring tasks"""
        logger.info("Stopping Model Performance Monitor")
        
        self._shutdown_event.set()
        
        for task in [self._monitoring_task, self._baseline_task, self._cleanup_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        logger.info("Model Performance Monitor stopped")
    
    def record_performance(self, 
                         model_name: str,
                         model_version: str,
                         metrics: Dict[str, float]):
        """Record performance metrics for a model version"""
        try:
            model_key = f"{model_name}:{model_version}"
            
            # Initialize storage if needed
            if model_key not in self._performance_data:
                self._performance_data[model_key] = deque(maxlen=10000)  # Limit memory usage
            
            # Add timestamp to metrics
            metrics_with_timestamp = {
                "timestamp": time.time(),
                **metrics
            }
            
            self._performance_data[model_key].append(metrics_with_timestamp)
            
            logger.debug("Performance metrics recorded",
                        model_name=model_name,
                        model_version=model_version,
                        metrics=list(metrics.keys()))
            
        except Exception as e:
            logger.error("Error recording performance metrics",
                        model_name=model_name,
                        model_version=model_version,
                        error=str(e))
    
    def set_thresholds(self, model_name: str, thresholds: List[PerformanceThreshold]):
        """Set performance thresholds for a model"""
        self._thresholds[model_name] = thresholds
        
        logger.info("Performance thresholds set",
                   model_name=model_name,
                   threshold_count=len(thresholds))
    
    def add_alert_callback(self, callback: Callable):
        """Add callback function for alerts"""
        self._alert_callbacks.append(callback)
    
    def add_rollback_callback(self, callback: Callable):
        """Add callback function for rollbacks"""
        self._rollback_callbacks.append(callback)
    
    def get_current_metrics(self, model_name: str, model_version: str) -> Dict[str, Any]:
        """Get current performance metrics for a model version"""
        try:
            model_key = f"{model_name}:{model_version}"
            
            if model_key not in self._performance_data:
                return {}
            
            data_points = list(self._performance_data[model_key])
            if not data_points:
                return {}
            
            # Calculate current metrics from recent data
            recent_data = [dp for dp in data_points if time.time() - dp["timestamp"] < 3600]  # Last hour
            
            if not recent_data:
                return {}
            
            # Calculate averages
            metrics = {}
            metric_names = set()
            for dp in recent_data:
                metric_names.update(k for k in dp.keys() if k != "timestamp")
            
            for metric_name in metric_names:
                values = [dp[metric_name] for dp in recent_data if metric_name in dp]
                if values:
                    metrics[f"avg_{metric_name}"] = sum(values) / len(values)
                    metrics[f"min_{metric_name}"] = min(values)
                    metrics[f"max_{metric_name}"] = max(values)
                    metrics[f"count_{metric_name}"] = len(values)
            
            return metrics
            
        except Exception as e:
            logger.error("Error getting current metrics",
                        model_name=model_name,
                        model_version=model_version,
                        error=str(e))
            return {}
    
    def get_performance_trends(self, 
                             model_name: str, 
                             model_version: str,
                             hours_back: int = 24) -> Dict[str, List[Dict[str, Any]]]:
        """Get performance trends over time"""
        try:
            model_key = f"{model_name}:{model_version}"
            
            if model_key not in self._performance_data:
                return {}
            
            # Filter data by time range
            cutoff_time = time.time() - (hours_back * 3600)
            data_points = [dp for dp in self._performance_data[model_key] 
                          if dp["timestamp"] >= cutoff_time]
            
            if not data_points:
                return {}
            
            # Group data by time buckets (e.g., hourly)
            bucket_size_seconds = 3600  # 1 hour buckets
            trends = {}
            
            # Get all metric names
            metric_names = set()
            for dp in data_points:
                metric_names.update(k for k in dp.keys() if k != "timestamp")
            
            # Create time series for each metric
            for metric_name in metric_names:
                time_series = []
                
                # Group by time buckets
                buckets = {}
                for dp in data_points:
                    if metric_name in dp:
                        bucket_key = int(dp["timestamp"] // bucket_size_seconds)
                        if bucket_key not in buckets:
                            buckets[bucket_key] = []
                        buckets[bucket_key].append(dp[metric_name])
                
                # Calculate averages for each bucket
                for bucket_key in sorted(buckets.keys()):
                    values = buckets[bucket_key]
                    time_series.append({
                        "timestamp": bucket_key * bucket_size_seconds,
                        "value": sum(values) / len(values),
                        "count": len(values),
                        "min": min(values),
                        "max": max(values)
                    })
                
                trends[metric_name] = time_series
            
            return trends
            
        except Exception as e:
            logger.error("Error getting performance trends",
                        model_name=model_name,
                        model_version=model_version,
                        error=str(e))
            return {}
    
    def get_model_comparison(self, model_name: str, versions: List[str]) -> Dict[str, Any]:
        """Compare performance across model versions"""
        try:
            comparison = {
                "model_name": model_name,
                "versions": {},
                "summary": {}
            }
            
            all_metrics = {}
            
            for version in versions:
                version_metrics = self.get_current_metrics(model_name, version)
                comparison["versions"][version] = version_metrics
                
                # Collect all metric names
                for metric_name in version_metrics:
                    if metric_name not in all_metrics:
                        all_metrics[metric_name] = {}
                    all_metrics[metric_name][version] = version_metrics[metric_name]
            
            # Create summary comparisons
            for metric_name, version_values in all_metrics.items():
                if len(version_values) > 1:
                    values = list(version_values.values())
                    comparison["summary"][metric_name] = {
                        "best_version": max(version_values, key=version_values.get) if "error" not in metric_name else min(version_values, key=version_values.get),
                        "worst_version": min(version_values, key=version_values.get) if "error" not in metric_name else max(version_values, key=version_values.get),
                        "range": max(values) - min(values),
                        "average": sum(values) / len(values)
                    }
            
            return comparison
            
        except Exception as e:
            logger.error("Error getting model comparison",
                        model_name=model_name,
                        versions=versions,
                        error=str(e))
            return {"error": str(e)}
    
    def get_active_alerts(self) -> List[PerformanceAlert]:
        """Get all active alerts"""
        return [alert for alert in self._active_alerts.values() if alert.is_active]
    
    def get_alert_history(self, hours_back: int = 24) -> List[PerformanceAlert]:
        """Get alert history"""
        cutoff_time = time.time() - (hours_back * 3600)
        return [alert for alert in self._alert_history if alert.triggered_at >= cutoff_time]
    
    def resolve_alert(self, alert_id: str, resolution_note: str = ""):
        """Manually resolve an alert"""
        try:
            if alert_id in self._active_alerts:
                alert = self._active_alerts[alert_id]
                alert.resolved_at = time.time()
                alert.actions_taken.append(f"Manually resolved: {resolution_note}")
                
                # Move to history
                self._alert_history.append(alert)
                del self._active_alerts[alert_id]
                
                logger.info("Alert resolved",
                           alert_id=alert_id,
                           model_name=alert.model_name,
                           model_version=alert.model_version,
                           resolution_note=resolution_note)
                
                return True
            
            return False
            
        except Exception as e:
            logger.error("Error resolving alert", alert_id=alert_id, error=str(e))
            return False
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while not self._shutdown_event.is_set():
            try:
                await self._check_thresholds()
                await self._detect_anomalies()
                
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.monitoring_interval_seconds
                )
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Monitoring loop error", error=str(e))
                await asyncio.sleep(60)
    
    async def _check_thresholds(self):
        """Check performance thresholds for all models"""
        for model_name, thresholds in self._thresholds.items():
            try:
                # Get all versions of this model
                model_versions = []
                for model_key in self._performance_data.keys():
                    if model_key.startswith(f"{model_name}:"):
                        version = model_key.split(":", 1)[1]
                        model_versions.append(version)
                
                for version in model_versions:
                    current_metrics = self.get_current_metrics(model_name, version)
                    
                    for threshold in thresholds:
                        await self._evaluate_threshold(model_name, version, threshold, current_metrics)
            
            except Exception as e:
                logger.error("Error checking thresholds",
                           model_name=model_name,
                           error=str(e))
    
    async def _evaluate_threshold(self, 
                                model_name: str,
                                model_version: str,
                                threshold: PerformanceThreshold,
                                current_metrics: Dict[str, float]):
        """Evaluate a specific threshold"""
        try:
            metric_key = f"avg_{threshold.metric_name}"
            if metric_key not in current_metrics:
                return
            
            current_value = current_metrics[metric_key]
            is_breached = False
            
            # Check threshold condition
            if threshold.operator == "greater_than":
                is_breached = current_value > threshold.threshold_value
            elif threshold.operator == "less_than":
                is_breached = current_value < threshold.threshold_value
            elif threshold.operator == "equals":
                is_breached = abs(current_value - threshold.threshold_value) < 0.001
            
            alert_id = f"{model_name}:{model_version}:{threshold.metric_name}"
            
            if is_breached:
                # Check if this is a new alert or existing
                if alert_id not in self._active_alerts:
                    # Create new alert
                    alert = PerformanceAlert(
                        alert_id=alert_id,
                        model_name=model_name,
                        model_version=model_version,
                        metric_name=threshold.metric_name,
                        threshold=threshold,
                        current_value=current_value,
                        triggered_at=time.time()
                    )
                    
                    self._active_alerts[alert_id] = alert
                    
                    # Execute alert actions
                    await self._execute_alert_actions(alert)
                    
                    logger.warning("Performance threshold breached",
                                 model_name=model_name,
                                 model_version=model_version,
                                 metric=threshold.metric_name,
                                 threshold_value=threshold.threshold_value,
                                 current_value=current_value,
                                 severity=threshold.severity)
                else:
                    # Update existing alert
                    alert = self._active_alerts[alert_id]
                    alert.current_value = current_value
            
            else:
                # Threshold not breached, resolve alert if it exists
                if alert_id in self._active_alerts:
                    alert = self._active_alerts[alert_id]
                    alert.resolved_at = time.time()
                    alert.actions_taken.append("Threshold condition resolved")
                    
                    # Move to history
                    self._alert_history.append(alert)
                    del self._active_alerts[alert_id]
                    
                    logger.info("Performance alert resolved",
                               alert_id=alert_id,
                               duration_minutes=alert.duration_minutes)
        
        except Exception as e:
            logger.error("Error evaluating threshold",
                        model_name=model_name,
                        model_version=model_version,
                        error=str(e))
    
    async def _detect_anomalies(self):
        """Detect performance anomalies using baselines"""
        try:
            for model_key, data_points in self._performance_data.items():
                if not data_points:
                    continue
                
                model_name, model_version = model_key.split(":", 1)
                
                # Get recent data point
                recent_data = list(data_points)[-1]
                
                # Check each metric against baseline
                for metric_name, value in recent_data.items():
                    if metric_name == "timestamp":
                        continue
                    
                    baseline_key = f"{model_name}:{metric_name}"
                    if baseline_key in self._baselines:
                        baseline = self._baselines[baseline_key]
                        
                        if baseline.is_anomaly(value, self.anomaly_sensitivity):
                            logger.warning("Performance anomaly detected",
                                         model_name=model_name,
                                         model_version=model_version,
                                         metric_name=metric_name,
                                         current_value=value,
                                         baseline_value=baseline.baseline_value,
                                         deviation=abs(value - baseline.baseline_value))
        
        except Exception as e:
            logger.error("Error detecting anomalies", error=str(e))
    
    async def _execute_alert_actions(self, alert: PerformanceAlert):
        """Execute actions for a triggered alert"""
        try:
            action = alert.threshold.action
            
            if action == "alert":
                # Execute alert callbacks
                for callback in self._alert_callbacks:
                    try:
                        await callback(alert)
                        alert.actions_taken.append("Alert notification sent")
                    except Exception as e:
                        logger.error("Error executing alert callback", error=str(e))
            
            elif action == "rollback":
                # Execute rollback callbacks
                for callback in self._rollback_callbacks:
                    try:
                        await callback(alert.model_name, alert.model_version, f"Performance threshold breached: {alert.metric_name}")
                        alert.actions_taken.append("Rollback triggered")
                    except Exception as e:
                        logger.error("Error executing rollback callback", error=str(e))
            
            elif action == "scale":
                # Placeholder for scaling actions
                alert.actions_taken.append("Scaling action triggered (placeholder)")
                logger.info("Scaling action would be triggered here", 
                           alert_id=alert.alert_id)
        
        except Exception as e:
            logger.error("Error executing alert actions",
                        alert_id=alert.alert_id,
                        error=str(e))
    
    async def _baseline_calculation_loop(self):
        """Calculate performance baselines periodically"""
        while not self._shutdown_event.is_set():
            try:
                await self._calculate_baselines()
                
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.baseline_calculation_interval_hours * 3600
                )
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Baseline calculation loop error", error=str(e))
                await asyncio.sleep(3600)
    
    async def _calculate_baselines(self):
        """Calculate performance baselines for all models"""
        try:
            for model_key, data_points in self._performance_data.items():
                if len(data_points) < 100:  # Need minimum sample size
                    continue
                
                model_name = model_key.split(":", 1)[0]
                
                # Get historical data (exclude recent 24 hours for stability)
                cutoff_time = time.time() - (24 * 3600)
                historical_data = [dp for dp in data_points if dp["timestamp"] < cutoff_time]
                
                if len(historical_data) < 100:
                    continue
                
                # Calculate baselines for each metric
                metric_names = set()
                for dp in historical_data:
                    metric_names.update(k for k in dp.keys() if k != "timestamp")
                
                for metric_name in metric_names:
                    values = [dp[metric_name] for dp in historical_data if metric_name in dp]
                    
                    if len(values) >= 100:
                        baseline = self._calculate_metric_baseline(model_name, metric_name, values)
                        baseline_key = f"{model_name}:{metric_name}"
                        self._baselines[baseline_key] = baseline
                        
                        logger.debug("Baseline calculated",
                                   model_name=model_name,
                                   metric_name=metric_name,
                                   baseline_value=baseline.baseline_value,
                                   sample_size=len(values))
        
        except Exception as e:
            logger.error("Error calculating baselines", error=str(e))
    
    def _calculate_metric_baseline(self, model_name: str, metric_name: str, values: List[float]) -> PerformanceBaseline:
        """Calculate baseline statistics for a metric"""
        try:
            n = len(values)
            mean = sum(values) / n
            variance = sum((x - mean) ** 2 for x in values) / (n - 1)
            std = variance ** 0.5
            
            # Calculate confidence interval (95%)
            margin_error = 1.96 * (std / (n ** 0.5))
            confidence_interval = (mean - margin_error, mean + margin_error)
            
            return PerformanceBaseline(
                model_name=model_name,
                metric_name=metric_name,
                baseline_value=mean,
                baseline_std=std,
                confidence_interval=confidence_interval,
                sample_size=n,
                calculated_at=time.time()
            )
        
        except Exception as e:
            logger.error("Error calculating metric baseline",
                        model_name=model_name,
                        metric_name=metric_name,
                        error=str(e))
            # Return default baseline
            return PerformanceBaseline(
                model_name=model_name,
                metric_name=metric_name,
                baseline_value=0.0,
                baseline_std=1.0,
                confidence_interval=(0.0, 0.0),
                sample_size=0,
                calculated_at=time.time()
            )
    
    async def _cleanup_loop(self):
        """Clean up old data periodically"""
        while not self._shutdown_event.is_set():
            try:
                await self._cleanup_old_data()
                
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=3600  # Run every hour
                )
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Cleanup loop error", error=str(e))
                await asyncio.sleep(3600)
    
    async def _cleanup_old_data(self):
        """Clean up old performance data"""
        try:
            cutoff_time = time.time() - (self.data_retention_hours * 3600)
            
            # Clean performance data
            for model_key in list(self._performance_data.keys()):
                data_points = self._performance_data[model_key]
                # Filter out old data points
                new_data = deque((dp for dp in data_points if dp["timestamp"] >= cutoff_time), 
                               maxlen=data_points.maxlen)
                self._performance_data[model_key] = new_data
                
                # Remove empty entries
                if not new_data:
                    del self._performance_data[model_key]
            
            # Clean alert history
            self._alert_history = [alert for alert in self._alert_history 
                                 if alert.triggered_at >= cutoff_time]
            
            logger.debug("Performance data cleanup completed",
                        cutoff_time=cutoff_time)
        
        except Exception as e:
            logger.error("Error during data cleanup", error=str(e))
    
    def get_monitoring_statistics(self) -> Dict[str, Any]:
        """Get comprehensive monitoring statistics"""
        try:
            current_time = time.time()
            
            return {
                "models_monitored": len(set(key.split(":", 1)[0] for key in self._performance_data.keys())),
                "model_versions_monitored": len(self._performance_data),
                "total_data_points": sum(len(data) for data in self._performance_data.values()),
                "active_alerts": len(self._active_alerts),
                "total_thresholds": sum(len(thresholds) for thresholds in self._thresholds.values()),
                "baselines_calculated": len(self._baselines),
                "alert_history_count": len(self._alert_history),
                "data_retention_hours": self.data_retention_hours,
                "monitoring_interval_seconds": self.monitoring_interval_seconds,
                "oldest_data_point": min((min(dp["timestamp"] for dp in data) for data in self._performance_data.values() if data), default=current_time),
                "newest_data_point": max((max(dp["timestamp"] for dp in data) for data in self._performance_data.values() if data), default=current_time)
            }
        
        except Exception as e:
            logger.error("Error getting monitoring statistics", error=str(e))
            return {"error": str(e)}