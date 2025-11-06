"""
AI Model Version Management

Comprehensive model versioning system for tracking, deploying, and managing
AI models across different providers with A/B testing and rollback capabilities.
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class ModelStatus(Enum):
    """Model deployment status"""
    PENDING = "pending"
    ACTIVE = "active"
    TESTING = "testing"
    DEPRECATED = "deprecated"
    RETIRED = "retired"
    FAILED = "failed"


class DeploymentStrategy(Enum):
    """Model deployment strategies"""
    REPLACE = "replace"  # Replace current model immediately
    CANARY = "canary"    # Gradual rollout with traffic splitting
    BLUE_GREEN = "blue_green"  # Switch between two environments
    A_B_TEST = "a_b_test"  # Side-by-side testing


@dataclass
class ModelMetrics:
    """Model performance metrics"""
    # Request metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    
    # Performance metrics
    avg_response_time: float = 0.0
    min_response_time: float = float('inf')
    max_response_time: float = 0.0
    p95_response_time: float = 0.0
    p99_response_time: float = 0.0
    
    # Quality metrics
    avg_confidence_score: float = 0.0
    classification_accuracy: float = 0.0
    
    # Business metrics
    cost_per_request: float = 0.0
    total_cost: float = 0.0
    
    # Error tracking
    error_rate: float = 0.0
    timeout_rate: float = 0.0
    
    # Timestamps
    first_request_time: Optional[float] = None
    last_request_time: Optional[float] = None
    last_updated: float = field(default_factory=time.time)
    
    def update_request_metrics(self, response_time: float, success: bool, confidence: float = 0.0, cost: float = 0.0):
        """Update metrics with new request data"""
        current_time = time.time()
        
        # Initialize timestamps
        if self.first_request_time is None:
            self.first_request_time = current_time
        self.last_request_time = current_time
        self.last_updated = current_time
        
        # Update request counts
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
        
        # Update response time metrics
        if response_time > 0:
            if self.total_requests == 1:
                self.avg_response_time = response_time
                self.min_response_time = response_time
                self.max_response_time = response_time
            else:
                # Exponential moving average for response time
                alpha = 0.1
                self.avg_response_time = alpha * response_time + (1 - alpha) * self.avg_response_time
                self.min_response_time = min(self.min_response_time, response_time)
                self.max_response_time = max(self.max_response_time, response_time)
        
        # Update confidence score
        if confidence > 0:
            if self.total_requests == 1:
                self.avg_confidence_score = confidence
            else:
                alpha = 0.1
                self.avg_confidence_score = alpha * confidence + (1 - alpha) * self.avg_confidence_score
        
        # Update cost metrics
        self.total_cost += cost
        if self.total_requests > 0:
            self.cost_per_request = self.total_cost / self.total_requests
        
        # Update derived metrics
        self.error_rate = self.failed_requests / self.total_requests if self.total_requests > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary"""
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": self.successful_requests / self.total_requests if self.total_requests > 0 else 0.0,
            "error_rate": self.error_rate,
            "avg_response_time": self.avg_response_time,
            "min_response_time": self.min_response_time if self.min_response_time != float('inf') else 0.0,
            "max_response_time": self.max_response_time,
            "avg_confidence_score": self.avg_confidence_score,
            "cost_per_request": self.cost_per_request,
            "total_cost": self.total_cost,
            "first_request_time": self.first_request_time,
            "last_request_time": self.last_request_time,
            "last_updated": self.last_updated
        }


@dataclass
class ModelConfiguration:
    """Model configuration parameters"""
    provider: str
    model_name: str
    model_version: str
    temperature: float = 0.3
    max_tokens: int = 1000
    timeout: int = 30
    
    # Provider-specific parameters
    custom_parameters: Dict[str, Any] = field(default_factory=dict)
    
    # Resource requirements
    cpu_limit: Optional[str] = None
    memory_limit: Optional[str] = None
    gpu_required: bool = False
    
    # Feature flags
    enable_caching: bool = True
    enable_streaming: bool = False
    enable_batch_processing: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "custom_parameters": self.custom_parameters,
            "cpu_limit": self.cpu_limit,
            "memory_limit": self.memory_limit,
            "gpu_required": self.gpu_required,
            "enable_caching": self.enable_caching,
            "enable_streaming": self.enable_streaming,
            "enable_batch_processing": self.enable_batch_processing
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ModelConfiguration':
        """Create configuration from dictionary"""
        return cls(
            provider=data["provider"],
            model_name=data["model_name"],
            model_version=data["model_version"],
            temperature=data.get("temperature", 0.3),
            max_tokens=data.get("max_tokens", 1000),
            timeout=data.get("timeout", 30),
            custom_parameters=data.get("custom_parameters", {}),
            cpu_limit=data.get("cpu_limit"),
            memory_limit=data.get("memory_limit"),
            gpu_required=data.get("gpu_required", False),
            enable_caching=data.get("enable_caching", True),
            enable_streaming=data.get("enable_streaming", False),
            enable_batch_processing=data.get("enable_batch_processing", True)
        )


@dataclass
class ModelDeployment:
    """Model deployment information"""
    deployment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    model_id: str = ""
    version: str = ""
    status: ModelStatus = ModelStatus.PENDING
    deployment_strategy: DeploymentStrategy = DeploymentStrategy.REPLACE
    
    # Deployment configuration
    traffic_percentage: float = 100.0  # Percentage of traffic to route to this model
    target_traffic_percentage: float = 100.0  # Target percentage for gradual rollout
    rollout_step_percentage: float = 10.0  # Percentage to increase per rollout step
    rollout_interval_minutes: int = 30  # Minutes between rollout steps
    
    # Deployment metadata
    deployed_by: str = "system"
    deployed_at: float = field(default_factory=time.time)
    activated_at: Optional[float] = None
    retired_at: Optional[float] = None
    
    # Health and performance criteria
    min_success_rate: float = 0.95
    max_response_time: float = 5.0
    min_confidence_score: float = 0.8
    
    # Rollback configuration
    auto_rollback_enabled: bool = True
    rollback_threshold_error_rate: float = 0.1
    rollback_threshold_response_time: float = 10.0
    rollback_evaluation_window_minutes: int = 15
    
    # A/B testing configuration
    ab_test_duration_hours: int = 24
    ab_test_min_requests: int = 1000
    ab_test_confidence_level: float = 0.95
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert deployment to dictionary"""
        return {
            "deployment_id": self.deployment_id,
            "model_id": self.model_id,
            "version": self.version,
            "status": self.status.value,
            "deployment_strategy": self.deployment_strategy.value,
            "traffic_percentage": self.traffic_percentage,
            "target_traffic_percentage": self.target_traffic_percentage,
            "rollout_step_percentage": self.rollout_step_percentage,
            "rollout_interval_minutes": self.rollout_interval_minutes,
            "deployed_by": self.deployed_by,
            "deployed_at": self.deployed_at,
            "activated_at": self.activated_at,
            "retired_at": self.retired_at,
            "min_success_rate": self.min_success_rate,
            "max_response_time": self.max_response_time,
            "min_confidence_score": self.min_confidence_score,
            "auto_rollback_enabled": self.auto_rollback_enabled,
            "rollback_threshold_error_rate": self.rollback_threshold_error_rate,
            "rollback_threshold_response_time": self.rollback_threshold_response_time,
            "rollback_evaluation_window_minutes": self.rollback_evaluation_window_minutes,
            "ab_test_duration_hours": self.ab_test_duration_hours,
            "ab_test_min_requests": self.ab_test_min_requests,
            "ab_test_confidence_level": self.ab_test_confidence_level
        }


@dataclass
class ModelVersion:
    """Comprehensive model version information"""
    # Core identification
    model_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: str = "1.0.0"
    name: str = ""
    description: str = ""
    
    # Configuration
    configuration: ModelConfiguration = field(default_factory=lambda: ModelConfiguration("", "", ""))
    
    # Status and lifecycle
    status: ModelStatus = ModelStatus.PENDING
    created_at: float = field(default_factory=time.time)
    created_by: str = "system"
    
    # Deployment information
    deployments: List[ModelDeployment] = field(default_factory=list)
    current_deployment: Optional[ModelDeployment] = None
    
    # Performance tracking
    metrics: ModelMetrics = field(default_factory=ModelMetrics)
    
    # Quality assurance
    validation_results: Dict[str, Any] = field(default_factory=dict)
    test_results: Dict[str, Any] = field(default_factory=dict)
    
    # Changelog and notes
    changelog: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    
    # Dependencies
    parent_version: Optional[str] = None
    child_versions: List[str] = field(default_factory=list)
    
    def add_deployment(self, deployment: ModelDeployment) -> None:
        """Add a new deployment"""
        deployment.model_id = self.model_id
        deployment.version = self.version
        self.deployments.append(deployment)
        
        # Update current deployment if this is active
        if deployment.status == ModelStatus.ACTIVE:
            self.current_deployment = deployment
            self.status = ModelStatus.ACTIVE
        
        logger.info("Deployment added to model version",
                   model_id=self.model_id,
                   version=self.version,
                   deployment_id=deployment.deployment_id,
                   strategy=deployment.deployment_strategy.value)
    
    def get_active_deployment(self) -> Optional[ModelDeployment]:
        """Get the currently active deployment"""
        for deployment in self.deployments:
            if deployment.status == ModelStatus.ACTIVE:
                return deployment
        return None
    
    def update_metrics(self, response_time: float, success: bool, confidence: float = 0.0, cost: float = 0.0):
        """Update model metrics"""
        self.metrics.update_request_metrics(response_time, success, confidence, cost)
    
    def calculate_health_score(self) -> float:
        """Calculate overall health score (0.0 to 1.0)"""
        if self.metrics.total_requests == 0:
            return 0.5  # Neutral score for untested models
        
        # Success rate component (0-0.4)
        success_rate = self.metrics.successful_requests / self.metrics.total_requests
        success_component = min(0.4, success_rate * 0.4)
        
        # Response time component (0-0.3)
        if self.metrics.avg_response_time > 0:
            # Normalize response time (assume 10s is very poor, 1s is excellent)
            normalized_response_time = max(0, 1 - (self.metrics.avg_response_time / 10.0))
            response_time_component = normalized_response_time * 0.3
        else:
            response_time_component = 0.15  # Neutral
        
        # Confidence score component (0-0.2)
        confidence_component = self.metrics.avg_confidence_score * 0.2
        
        # Error rate penalty (0-0.1)
        error_penalty = min(0.1, self.metrics.error_rate * 0.1)
        
        health_score = success_component + response_time_component + confidence_component - error_penalty
        return max(0.0, min(1.0, health_score))
    
    def should_rollback(self) -> tuple[bool, str]:
        """Check if model should be rolled back based on performance criteria"""
        if not self.current_deployment or not self.current_deployment.auto_rollback_enabled:
            return False, "Auto-rollback not enabled"
        
        deployment = self.current_deployment
        
        # Check if we have enough data for evaluation
        if self.metrics.total_requests < 100:  # Minimum requests for evaluation
            return False, "Insufficient data for rollback evaluation"
        
        # Check error rate threshold
        if self.metrics.error_rate > deployment.rollback_threshold_error_rate:
            return True, f"Error rate {self.metrics.error_rate:.3f} exceeds threshold {deployment.rollback_threshold_error_rate:.3f}"
        
        # Check response time threshold
        if self.metrics.avg_response_time > deployment.rollback_threshold_response_time:
            return True, f"Response time {self.metrics.avg_response_time:.2f}s exceeds threshold {deployment.rollback_threshold_response_time:.2f}s"
        
        # Check success rate threshold
        success_rate = self.metrics.successful_requests / self.metrics.total_requests
        if success_rate < deployment.min_success_rate:
            return True, f"Success rate {success_rate:.3f} below minimum {deployment.min_success_rate:.3f}"
        
        return False, "All metrics within acceptable thresholds"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model version to dictionary"""
        return {
            "model_id": self.model_id,
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "configuration": self.configuration.to_dict(),
            "status": self.status.value,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "deployments": [d.to_dict() for d in self.deployments],
            "current_deployment": self.current_deployment.to_dict() if self.current_deployment else None,
            "metrics": self.metrics.to_dict(),
            "validation_results": self.validation_results,
            "test_results": self.test_results,
            "changelog": self.changelog,
            "tags": self.tags,
            "parent_version": self.parent_version,
            "child_versions": self.child_versions,
            "health_score": self.calculate_health_score()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ModelVersion':
        """Create model version from dictionary"""
        model_version = cls(
            model_id=data["model_id"],
            version=data["version"],
            name=data.get("name", ""),
            description=data.get("description", ""),
            configuration=ModelConfiguration.from_dict(data["configuration"]),
            status=ModelStatus(data["status"]),
            created_at=data.get("created_at", time.time()),
            created_by=data.get("created_by", "system"),
            validation_results=data.get("validation_results", {}),
            test_results=data.get("test_results", {}),
            changelog=data.get("changelog", []),
            tags=data.get("tags", []),
            parent_version=data.get("parent_version"),
            child_versions=data.get("child_versions", [])
        )
        
        # Restore deployments
        for deployment_data in data.get("deployments", []):
            deployment = ModelDeployment(**deployment_data)
            deployment.status = ModelStatus(deployment_data["status"])
            deployment.deployment_strategy = DeploymentStrategy(deployment_data["deployment_strategy"])
            model_version.deployments.append(deployment)
        
        # Restore current deployment
        if data.get("current_deployment"):
            current_deployment_data = data["current_deployment"]
            model_version.current_deployment = ModelDeployment(**current_deployment_data)
            model_version.current_deployment.status = ModelStatus(current_deployment_data["status"])
            model_version.current_deployment.deployment_strategy = DeploymentStrategy(current_deployment_data["deployment_strategy"])
        
        # Restore metrics
        if "metrics" in data:
            metrics_data = data["metrics"]
            model_version.metrics = ModelMetrics(
                total_requests=metrics_data.get("total_requests", 0),
                successful_requests=metrics_data.get("successful_requests", 0),
                failed_requests=metrics_data.get("failed_requests", 0),
                avg_response_time=metrics_data.get("avg_response_time", 0.0),
                min_response_time=metrics_data.get("min_response_time", float('inf')),
                max_response_time=metrics_data.get("max_response_time", 0.0),
                avg_confidence_score=metrics_data.get("avg_confidence_score", 0.0),
                cost_per_request=metrics_data.get("cost_per_request", 0.0),
                total_cost=metrics_data.get("total_cost", 0.0),
                error_rate=metrics_data.get("error_rate", 0.0),
                first_request_time=metrics_data.get("first_request_time"),
                last_request_time=metrics_data.get("last_request_time"),
                last_updated=metrics_data.get("last_updated", time.time())
            )
        
        return model_version