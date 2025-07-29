"""
Model Version Manager

Enterprise-grade model lifecycle management with A/B testing, rollback capabilities,
and automated deployment strategies for AI model versioning.
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
import structlog

from .model_version import (
    ModelVersion, ModelDeployment, ModelConfiguration, ModelMetrics,
    ModelStatus, DeploymentStrategy
)

logger = structlog.get_logger(__name__)


@dataclass
class ModelManagerConfig:
    """Configuration for model version manager"""
    # Storage configuration
    storage_backend: str = "file"  # file, redis, database
    storage_path: str = "./models"
    backup_enabled: bool = True
    backup_interval_hours: int = 24
    
    # Deployment configuration
    default_deployment_strategy: DeploymentStrategy = DeploymentStrategy.REPLACE
    canary_rollout_interval_minutes: int = 30
    canary_rollout_step_percentage: float = 10.0
    
    # Health monitoring
    health_check_interval_seconds: int = 60
    rollback_evaluation_window_minutes: int = 15
    min_requests_for_evaluation: int = 100
    
    # A/B testing
    ab_test_default_duration_hours: int = 24
    ab_test_min_requests: int = 1000
    ab_test_confidence_level: float = 0.95
    
    # Retention policy
    max_versions_per_model: int = 10
    retention_days: int = 90
    
    # Validation
    enable_model_validation: bool = True
    validation_timeout_seconds: int = 300


class ModelVersionManager:
    """Comprehensive model version management system"""
    
    def __init__(self, config: ModelManagerConfig):
        self.config = config
        
        # Model storage
        self._models: Dict[str, List[ModelVersion]] = {}  # model_name -> list of versions
        self._active_models: Dict[str, ModelVersion] = {}  # model_name -> active version
        self._ab_tests: Dict[str, Dict[str, Any]] = {}  # test_id -> test configuration
        
        # Background tasks
        self._health_monitor_task: Optional[asyncio.Task] = None
        self._rollout_manager_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Initialize storage
        self._initialize_storage()
        
        logger.info("Model Version Manager initialized",
                   storage_backend=config.storage_backend,
                   storage_path=config.storage_path)
    
    def _initialize_storage(self):
        """Initialize storage backend"""
        if self.config.storage_backend == "file":
            # Create storage directory
            storage_path = Path(self.config.storage_path)
            storage_path.mkdir(parents=True, exist_ok=True)
            
            # Create subdirectories
            (storage_path / "models").mkdir(exist_ok=True)
            (storage_path / "deployments").mkdir(exist_ok=True)
            (storage_path / "backups").mkdir(exist_ok=True)
            
            # Load existing models
            self._load_models_from_storage()
    
    def _load_models_from_storage(self):
        """Load existing models from storage"""
        try:
            models_path = Path(self.config.storage_path) / "models"
            
            for model_file in models_path.glob("*.json"):
                try:
                    with open(model_file, 'r') as f:
                        model_data = json.load(f)
                    
                    model_version = ModelVersion.from_dict(model_data)
                    model_name = model_version.configuration.model_name
                    
                    if model_name not in self._models:
                        self._models[model_name] = []
                    
                    self._models[model_name].append(model_version)
                    
                    # Set as active if it's the active deployment
                    if model_version.status == ModelStatus.ACTIVE:
                        self._active_models[model_name] = model_version
                    
                    logger.debug("Loaded model version from storage",
                               model_name=model_name,
                               version=model_version.version)
                
                except Exception as e:
                    logger.error("Error loading model file",
                               file=model_file.name,
                               error=str(e))
        
        except Exception as e:
            logger.error("Error loading models from storage", error=str(e))
    
    async def start(self):
        """Start background tasks"""
        try:
            # Start health monitoring
            self._health_monitor_task = asyncio.create_task(self._health_monitor_loop())
            
            # Start rollout manager
            self._rollout_manager_task = asyncio.create_task(self._rollout_manager_loop())
            
            # Start cleanup task
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            
            logger.info("Model Version Manager background tasks started")
            
        except Exception as e:
            logger.error("Error starting Model Version Manager", error=str(e))
            raise
    
    async def stop(self):
        """Stop background tasks"""
        logger.info("Stopping Model Version Manager")
        
        self._shutdown_event.set()
        
        # Cancel tasks
        for task in [self._health_monitor_task, self._rollout_manager_task, self._cleanup_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        logger.info("Model Version Manager stopped")
    
    async def create_model_version(self, 
                                 model_name: str,
                                 version: str,
                                 configuration: ModelConfiguration,
                                 description: str = "",
                                 tags: List[str] = None,
                                 parent_version: str = None) -> ModelVersion:
        """Create a new model version"""
        try:
            # Check if version already exists
            if model_name in self._models:
                existing_versions = [mv.version for mv in self._models[model_name]]
                if version in existing_versions:
                    raise ValueError(f"Version {version} already exists for model {model_name}")
            
            # Create model version
            model_version = ModelVersion(
                version=version,
                name=model_name,
                description=description,
                configuration=configuration,
                status=ModelStatus.PENDING,
                tags=tags or [],
                parent_version=parent_version,
                created_by="model_manager"
            )
            
            # Add to storage
            if model_name not in self._models:
                self._models[model_name] = []
            
            self._models[model_name].append(model_version)
            
            # Update parent-child relationships
            if parent_version:
                parent_model = self.get_model_version(model_name, parent_version)
                if parent_model:
                    parent_model.child_versions.append(version)
            
            # Save to storage
            await self._save_model_version(model_version)
            
            logger.info("Model version created",
                       model_name=model_name,
                       version=version,
                       parent_version=parent_version)
            
            return model_version
            
        except Exception as e:
            logger.error("Error creating model version",
                        model_name=model_name,
                        version=version,
                        error=str(e))
            raise
    
    async def deploy_model_version(self,
                                 model_name: str,
                                 version: str,
                                 strategy: DeploymentStrategy = None,
                                 traffic_percentage: float = 100.0,
                                 deployed_by: str = "system") -> ModelDeployment:
        """Deploy a model version with specified strategy"""
        try:
            # Get model version
            model_version = self.get_model_version(model_name, version)
            if not model_version:
                raise ValueError(f"Model version {model_name}:{version} not found")
            
            # Use default strategy if not specified
            if strategy is None:
                strategy = self.config.default_deployment_strategy
            
            # Create deployment
            deployment = ModelDeployment(
                model_id=model_version.model_id,
                version=version,
                deployment_strategy=strategy,
                traffic_percentage=traffic_percentage,
                target_traffic_percentage=traffic_percentage,
                deployed_by=deployed_by,
                rollout_step_percentage=self.config.canary_rollout_step_percentage,
                rollout_interval_minutes=self.config.canary_rollout_interval_minutes
            )
            
            # Handle different deployment strategies
            if strategy == DeploymentStrategy.REPLACE:
                # Retire current active model
                await self._retire_active_model(model_name)
                
                # Activate new model immediately
                deployment.status = ModelStatus.ACTIVE
                deployment.activated_at = time.time()
                deployment.traffic_percentage = 100.0
                
                self._active_models[model_name] = model_version
                model_version.status = ModelStatus.ACTIVE
            
            elif strategy == DeploymentStrategy.CANARY:
                # Start with small percentage
                deployment.traffic_percentage = self.config.canary_rollout_step_percentage
                deployment.status = ModelStatus.TESTING
                model_version.status = ModelStatus.TESTING
            
            elif strategy == DeploymentStrategy.A_B_TEST:
                # Start A/B test
                deployment.traffic_percentage = 50.0  # Split traffic
                deployment.status = ModelStatus.TESTING
                model_version.status = ModelStatus.TESTING
                
                # Create A/B test configuration
                await self._create_ab_test(model_name, version, deployment)
            
            # Add deployment to model
            model_version.add_deployment(deployment)
            
            # Save changes
            await self._save_model_version(model_version)
            
            logger.info("Model version deployed",
                       model_name=model_name,
                       version=version,
                       strategy=strategy.value,
                       traffic_percentage=traffic_percentage,
                       deployment_id=deployment.deployment_id)
            
            return deployment
            
        except Exception as e:
            logger.error("Error deploying model version",
                        model_name=model_name,
                        version=version,
                        error=str(e))
            raise
    
    async def rollback_model(self, 
                           model_name: str, 
                           target_version: str = None,
                           reason: str = "Manual rollback") -> bool:
        """Rollback model to previous version or specified version"""
        try:
            current_model = self._active_models.get(model_name)
            if not current_model:
                raise ValueError(f"No active model found for {model_name}")
            
            # Determine target version
            if target_version is None:
                # Find previous stable version
                target_version = self._find_previous_stable_version(model_name, current_model.version)
                if not target_version:
                    raise ValueError(f"No previous stable version found for {model_name}")
            
            # Get target model version
            target_model = self.get_model_version(model_name, target_version)
            if not target_model:
                raise ValueError(f"Target version {target_version} not found")
            
            # Retire current model
            if current_model.current_deployment:
                current_model.current_deployment.status = ModelStatus.RETIRED
                current_model.current_deployment.retired_at = time.time()
            current_model.status = ModelStatus.RETIRED
            
            # Activate target model
            rollback_deployment = ModelDeployment(
                model_id=target_model.model_id,
                version=target_version,
                deployment_strategy=DeploymentStrategy.REPLACE,
                traffic_percentage=100.0,
                deployed_by="rollback_system",
                status=ModelStatus.ACTIVE
            )
            rollback_deployment.activated_at = time.time()
            
            target_model.add_deployment(rollback_deployment)
            target_model.status = ModelStatus.ACTIVE
            self._active_models[model_name] = target_model
            
            # Add changelog entry
            target_model.changelog.append(f"Rollback from {current_model.version}: {reason}")
            current_model.changelog.append(f"Rolled back to {target_version}: {reason}")
            
            # Save changes
            await self._save_model_version(current_model)
            await self._save_model_version(target_model)
            
            logger.warning("Model rollback executed",
                         model_name=model_name,
                         from_version=current_model.version,
                         to_version=target_version,
                         reason=reason)
            
            return True
            
        except Exception as e:
            logger.error("Error rolling back model",
                        model_name=model_name,
                        target_version=target_version,
                        error=str(e))
            return False
    
    def get_model_version(self, model_name: str, version: str) -> Optional[ModelVersion]:
        """Get specific model version"""
        if model_name not in self._models:
            return None
        
        for model_version in self._models[model_name]:
            if model_version.version == version:
                return model_version
        
        return None
    
    def get_active_model(self, model_name: str) -> Optional[ModelVersion]:
        """Get currently active model version"""
        return self._active_models.get(model_name)
    
    def list_model_versions(self, model_name: str) -> List[ModelVersion]:
        """List all versions of a model"""
        return self._models.get(model_name, [])
    
    def list_all_models(self) -> Dict[str, List[ModelVersion]]:
        """List all models and their versions"""
        return self._models.copy()
    
    async def update_model_metrics(self, 
                                 model_name: str, 
                                 version: str,
                                 response_time: float,
                                 success: bool,
                                 confidence: float = 0.0,
                                 cost: float = 0.0):
        """Update metrics for a model version"""
        try:
            model_version = self.get_model_version(model_name, version)
            if model_version:
                model_version.update_metrics(response_time, success, confidence, cost)
                
                # Check for rollback conditions
                should_rollback, reason = model_version.should_rollback()
                if should_rollback and model_version.status == ModelStatus.ACTIVE:
                    logger.warning("Auto-rollback triggered",
                                 model_name=model_name,
                                 version=version,
                                 reason=reason)
                    await self.rollback_model(model_name, reason=f"Auto-rollback: {reason}")
                
                # Save updated metrics periodically
                if model_version.metrics.total_requests % 100 == 0:  # Every 100 requests
                    await self._save_model_version(model_version)
        
        except Exception as e:
            logger.error("Error updating model metrics",
                        model_name=model_name,
                        version=version,
                        error=str(e))
    
    async def _create_ab_test(self, model_name: str, version: str, deployment: ModelDeployment):
        """Create A/B test configuration"""
        test_id = f"{model_name}_{version}_{int(time.time())}"
        
        current_model = self._active_models.get(model_name)
        control_version = current_model.version if current_model else None
        
        ab_test_config = {
            "test_id": test_id,
            "model_name": model_name,
            "control_version": control_version,
            "treatment_version": version,
            "start_time": time.time(),
            "duration_hours": deployment.ab_test_duration_hours,
            "min_requests": deployment.ab_test_min_requests,
            "confidence_level": deployment.ab_test_confidence_level,
            "status": "running",
            "results": None
        }
        
        self._ab_tests[test_id] = ab_test_config
        
        logger.info("A/B test created",
                   test_id=test_id,
                   model_name=model_name,
                   control_version=control_version,
                   treatment_version=version)
    
    def _find_previous_stable_version(self, model_name: str, current_version: str) -> Optional[str]:
        """Find the previous stable version for rollback"""
        if model_name not in self._models:
            return None
        
        # Sort versions by creation time (newest first)
        versions = sorted(self._models[model_name], 
                         key=lambda mv: mv.created_at, 
                         reverse=True)
        
        # Find current version index
        current_index = None
        for i, model_version in enumerate(versions):
            if model_version.version == current_version:
                current_index = i
                break
        
        if current_index is None:
            return None
        
        # Look for previous stable version
        for i in range(current_index + 1, len(versions)):
            model_version = versions[i]
            if (model_version.status in [ModelStatus.ACTIVE, ModelStatus.RETIRED] and
                model_version.metrics.total_requests > 0 and
                model_version.metrics.error_rate < 0.05):  # Less than 5% error rate
                return model_version.version
        
        return None
    
    async def _retire_active_model(self, model_name: str):
        """Retire currently active model"""
        current_model = self._active_models.get(model_name)
        if current_model and current_model.current_deployment:
            current_model.current_deployment.status = ModelStatus.RETIRED
            current_model.current_deployment.retired_at = time.time()
            current_model.status = ModelStatus.RETIRED
            
            if model_name in self._active_models:
                del self._active_models[model_name]
    
    async def _save_model_version(self, model_version: ModelVersion):
        """Save model version to storage"""
        try:
            if self.config.storage_backend == "file":
                models_path = Path(self.config.storage_path) / "models"
                filename = f"{model_version.configuration.model_name}_{model_version.version}.json"
                filepath = models_path / filename
                
                with open(filepath, 'w') as f:
                    json.dump(model_version.to_dict(), f, indent=2)
        
        except Exception as e:
            logger.error("Error saving model version",
                        model_id=model_version.model_id,
                        version=model_version.version,
                        error=str(e))
    
    async def _health_monitor_loop(self):
        """Background health monitoring loop"""
        while not self._shutdown_event.is_set():
            try:
                await self._check_model_health()
                
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.config.health_check_interval_seconds
                )
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Health monitor error", error=str(e))
                await asyncio.sleep(60)
    
    async def _check_model_health(self):
        """Check health of all active models"""
        for model_name, model_version in self._active_models.items():
            try:
                health_score = model_version.calculate_health_score()
                
                if health_score < 0.3:  # Poor health threshold
                    logger.warning("Model health degraded",
                                 model_name=model_name,
                                 version=model_version.version,
                                 health_score=health_score)
                
                # Check rollback conditions
                should_rollback, reason = model_version.should_rollback()
                if should_rollback:
                    await self.rollback_model(model_name, reason=f"Health check: {reason}")
            
            except Exception as e:
                logger.error("Error checking model health",
                           model_name=model_name,
                           error=str(e))
    
    async def _rollout_manager_loop(self):
        """Background rollout management loop"""
        while not self._shutdown_event.is_set():
            try:
                await self._manage_rollouts()
                
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=60  # Check every minute
                )
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Rollout manager error", error=str(e))
                await asyncio.sleep(60)
    
    async def _manage_rollouts(self):
        """Manage ongoing canary rollouts"""
        for model_name, model_versions in self._models.items():
            for model_version in model_versions:
                if model_version.status == ModelStatus.TESTING:
                    deployment = model_version.current_deployment
                    if (deployment and 
                        deployment.deployment_strategy == DeploymentStrategy.CANARY and
                        deployment.traffic_percentage < deployment.target_traffic_percentage):
                        
                        # Check if it's time for next rollout step
                        time_since_deployment = time.time() - deployment.deployed_at
                        minutes_since_deployment = time_since_deployment / 60
                        
                        if minutes_since_deployment >= deployment.rollout_interval_minutes:
                            await self._advance_canary_rollout(model_version, deployment)
    
    async def _advance_canary_rollout(self, model_version: ModelVersion, deployment: ModelDeployment):
        """Advance canary rollout to next step"""
        try:
            # Check current performance
            if model_version.metrics.total_requests < self.config.min_requests_for_evaluation:
                logger.debug("Insufficient requests for canary advancement",
                           model_name=model_version.name,
                           version=model_version.version,
                           requests=model_version.metrics.total_requests)
                return
            
            # Check health metrics
            should_rollback, reason = model_version.should_rollback()
            if should_rollback:
                logger.warning("Canary rollout failed health check",
                             model_name=model_version.name,
                             version=model_version.version,
                             reason=reason)
                await self.rollback_model(model_version.name, reason=f"Canary failure: {reason}")
                return
            
            # Advance traffic percentage
            new_percentage = min(
                deployment.traffic_percentage + deployment.rollout_step_percentage,
                deployment.target_traffic_percentage
            )
            
            deployment.traffic_percentage = new_percentage
            
            # Check if rollout is complete
            if new_percentage >= deployment.target_traffic_percentage:
                deployment.status = ModelStatus.ACTIVE
                deployment.activated_at = time.time()
                model_version.status = ModelStatus.ACTIVE
                self._active_models[model_version.name] = model_version
                
                # Retire previous active model
                await self._retire_active_model(model_version.name)
                
                logger.info("Canary rollout completed",
                           model_name=model_version.name,
                           version=model_version.version)
            else:
                logger.info("Canary rollout advanced",
                           model_name=model_version.name,
                           version=model_version.version,
                           traffic_percentage=new_percentage)
            
            await self._save_model_version(model_version)
        
        except Exception as e:
            logger.error("Error advancing canary rollout",
                        model_name=model_version.name,
                        version=model_version.version,
                        error=str(e))
    
    async def _cleanup_loop(self):
        """Background cleanup loop"""
        while not self._shutdown_event.is_set():
            try:
                await self._cleanup_old_versions()
                
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=3600  # Run every hour
                )
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Cleanup loop error", error=str(e))
                await asyncio.sleep(3600)
    
    async def _cleanup_old_versions(self):
        """Clean up old model versions based on retention policy"""
        try:
            current_time = time.time()
            retention_seconds = self.config.retention_days * 24 * 3600
            
            for model_name, versions in self._models.items():
                # Sort by creation time (newest first)
                versions.sort(key=lambda mv: mv.created_at, reverse=True)
                
                # Keep active and recent versions
                versions_to_keep = []
                versions_to_remove = []
                
                for i, version in enumerate(versions):
                    # Always keep active versions
                    if version.status == ModelStatus.ACTIVE:
                        versions_to_keep.append(version)
                        continue
                    
                    # Keep recent versions within retention period
                    if current_time - version.created_at < retention_seconds:
                        versions_to_keep.append(version)
                        continue
                    
                    # Keep up to max_versions_per_model
                    if len(versions_to_keep) < self.config.max_versions_per_model:
                        versions_to_keep.append(version)
                        continue
                    
                    # Mark for removal
                    versions_to_remove.append(version)
                
                # Remove old versions
                if versions_to_remove:
                    self._models[model_name] = versions_to_keep
                    
                    for version in versions_to_remove:
                        logger.info("Cleaned up old model version",
                                   model_name=model_name,
                                   version=version.version,
                                   age_days=(current_time - version.created_at) / 86400)
        
        except Exception as e:
            logger.error("Error during cleanup", error=str(e))
    
    def get_model_statistics(self) -> Dict[str, Any]:
        """Get comprehensive model statistics"""
        try:
            stats = {
                "total_models": len(self._models),
                "total_versions": sum(len(versions) for versions in self._models.values()),
                "active_models": len(self._active_models),
                "models": {},
                "deployment_strategies": {strategy.value: 0 for strategy in DeploymentStrategy},
                "model_statuses": {status.value: 0 for status in ModelStatus}
            }
            
            for model_name, versions in self._models.items():
                model_stats = {
                    "total_versions": len(versions),
                    "active_version": None,
                    "latest_version": None,
                    "total_requests": 0,
                    "total_cost": 0.0,
                    "avg_health_score": 0.0
                }
                
                health_scores = []
                for version in versions:
                    # Count statuses
                    stats["model_statuses"][version.status.value] += 1
                    
                    # Count deployment strategies
                    for deployment in version.deployments:
                        stats["deployment_strategies"][deployment.deployment_strategy.value] += 1
                    
                    # Aggregate metrics
                    model_stats["total_requests"] += version.metrics.total_requests
                    model_stats["total_cost"] += version.metrics.total_cost
                    
                    # Track health scores
                    health_score = version.calculate_health_score()
                    health_scores.append(health_score)
                    
                    # Set active and latest versions
                    if version.status == ModelStatus.ACTIVE:
                        model_stats["active_version"] = version.version
                    
                    if (model_stats["latest_version"] is None or 
                        version.created_at > next(v.created_at for v in versions 
                                                if v.version == model_stats["latest_version"])):
                        model_stats["latest_version"] = version.version
                
                # Calculate average health score
                if health_scores:
                    model_stats["avg_health_score"] = sum(health_scores) / len(health_scores)
                
                stats["models"][model_name] = model_stats
            
            return stats
        
        except Exception as e:
            logger.error("Error getting model statistics", error=str(e))
            return {"error": str(e)}
    
    def get_ab_test_results(self, test_id: str) -> Optional[Dict[str, Any]]:
        """Get A/B test results"""
        return self._ab_tests.get(test_id)