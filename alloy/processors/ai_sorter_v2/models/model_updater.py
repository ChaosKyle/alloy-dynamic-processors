"""
Model Update Automation System

Automated model update and deployment system with CI/CD integration,
validation pipelines, and smart deployment strategies.
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import structlog

from .model_version import ModelVersion, ModelConfiguration, ModelStatus, DeploymentStrategy
from .model_manager import ModelVersionManager
from .ab_testing import ABTestEngine

logger = structlog.get_logger(__name__)


class UpdateTrigger(Enum):
    """Model update triggers"""
    MANUAL = "manual"
    SCHEDULE = "schedule"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    NEW_MODEL_AVAILABLE = "new_model_available"
    SECURITY_UPDATE = "security_update"
    CONFIGURATION_CHANGE = "configuration_change"


class UpdateStatus(Enum):
    """Model update status"""
    PENDING = "pending"
    VALIDATING = "validating"
    DEPLOYING = "deploying"
    TESTING = "testing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class ValidationRule:
    """Model validation rule"""
    name: str
    description: str
    validator_function: str  # Name of validator function
    severity: str = "error"  # error, warning, info
    timeout_seconds: int = 300
    required: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "description": self.description,
            "validator_function": self.validator_function,
            "severity": self.severity,
            "timeout_seconds": self.timeout_seconds,
            "required": self.required
        }


@dataclass
class ValidationResult:
    """Result of a validation rule"""
    rule_name: str
    passed: bool
    message: str
    execution_time_seconds: float
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "rule_name": self.rule_name,
            "passed": self.passed,
            "message": self.message,
            "execution_time_seconds": self.execution_time_seconds,
            "details": self.details
        }


@dataclass
class ModelUpdate:
    """Model update information"""
    update_id: str
    model_name: str
    current_version: str
    target_version: str
    trigger: UpdateTrigger
    deployment_strategy: DeploymentStrategy
    
    # Configuration
    new_configuration: Optional[ModelConfiguration] = None
    validation_rules: List[ValidationRule] = field(default_factory=list)
    
    # Status tracking
    status: UpdateStatus = UpdateStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    # Results
    validation_results: List[ValidationResult] = field(default_factory=list)
    deployment_id: Optional[str] = None
    ab_test_id: Optional[str] = None
    rollback_reason: Optional[str] = None
    
    # Metadata
    triggered_by: str = "system"
    notes: List[str] = field(default_factory=list)
    
    @property
    def duration_minutes(self) -> float:
        """Get update duration in minutes"""
        if not self.started_at:
            return 0.0
        end_time = self.completed_at or time.time()
        return (end_time - self.started_at) / 60
    
    @property
    def validation_passed(self) -> bool:
        """Check if validation passed"""
        if not self.validation_results:
            return False
        
        # Check required validations
        required_validations = [r for r in self.validation_rules if r.required]
        required_results = [vr for vr in self.validation_results 
                          if any(rv.name == vr.rule_name for rv in required_validations)]
        
        return all(vr.passed for vr in required_results)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "update_id": self.update_id,
            "model_name": self.model_name,
            "current_version": self.current_version,
            "target_version": self.target_version,
            "trigger": self.trigger.value,
            "deployment_strategy": self.deployment_strategy.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_minutes": self.duration_minutes,
            "validation_passed": self.validation_passed,
            "validation_results": [vr.to_dict() for vr in self.validation_results],
            "deployment_id": self.deployment_id,
            "ab_test_id": self.ab_test_id,
            "rollback_reason": self.rollback_reason,
            "triggered_by": self.triggered_by,
            "notes": self.notes
        }


class ModelUpdateAutomation:
    """Automated model update and deployment system"""
    
    def __init__(self, 
                 model_manager: ModelVersionManager,
                 ab_test_engine: ABTestEngine,
                 config: Dict[str, Any] = None):
        self.model_manager = model_manager
        self.ab_test_engine = ab_test_engine
        self.config = config or {}
        
        # Update tracking
        self._pending_updates: Dict[str, ModelUpdate] = {}
        self._active_updates: Dict[str, ModelUpdate] = {}
        self._completed_updates: List[ModelUpdate] = []
        
        # Validation functions registry
        self._validators: Dict[str, Callable] = {}
        
        # Update triggers and schedules
        self._scheduled_updates: Dict[str, Dict[str, Any]] = {}
        self._performance_monitors: Dict[str, Dict[str, Any]] = {}
        
        # Background tasks
        self._scheduler_task: Optional[asyncio.Task] = None
        self._processor_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Configuration
        self.max_concurrent_updates = self.config.get("max_concurrent_updates", 3)
        self.default_validation_timeout = self.config.get("default_validation_timeout", 300)
        self.update_check_interval_minutes = self.config.get("update_check_interval_minutes", 60)
        
        # Register default validators
        self._register_default_validators()
        
        logger.info("Model Update Automation initialized",
                   max_concurrent_updates=self.max_concurrent_updates,
                   update_check_interval_minutes=self.update_check_interval_minutes)
    
    async def start(self):
        """Start automation tasks"""
        try:
            self._scheduler_task = asyncio.create_task(self._scheduler_loop())
            self._processor_task = asyncio.create_task(self._processor_loop())
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            
            logger.info("Model Update Automation started")
            
        except Exception as e:
            logger.error("Error starting model update automation", error=str(e))
            raise
    
    async def stop(self):
        """Stop automation tasks"""
        logger.info("Stopping Model Update Automation")
        
        self._shutdown_event.set()
        
        for task in [self._scheduler_task, self._processor_task, self._monitor_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        logger.info("Model Update Automation stopped")
    
    def register_validator(self, name: str, validator_func: Callable):
        """Register a custom validation function"""
        self._validators[name] = validator_func
        logger.info("Validator registered", name=name)
    
    def schedule_update(self,
                       model_name: str,
                       target_version: str,
                       cron_expression: str,
                       deployment_strategy: DeploymentStrategy = DeploymentStrategy.CANARY,
                       validation_rules: List[ValidationRule] = None,
                       **kwargs):
        """Schedule automatic model updates"""
        try:
            schedule_id = f"{model_name}_{target_version}_{int(time.time())}"
            
            schedule_config = {
                "schedule_id": schedule_id,
                "model_name": model_name,
                "target_version": target_version,
                "cron_expression": cron_expression,
                "deployment_strategy": deployment_strategy,
                "validation_rules": validation_rules or [],
                "enabled": True,
                "last_run": None,
                "next_run": self._calculate_next_run(cron_expression),
                **kwargs
            }
            
            self._scheduled_updates[schedule_id] = schedule_config
            
            logger.info("Model update scheduled",
                       schedule_id=schedule_id,
                       model_name=model_name,
                       target_version=target_version,
                       next_run=schedule_config["next_run"])
            
            return schedule_id
            
        except Exception as e:
            logger.error("Error scheduling model update",
                        model_name=model_name,
                        target_version=target_version,
                        error=str(e))
            raise
    
    def trigger_update(self,
                      model_name: str,
                      target_version: str,
                      trigger: UpdateTrigger = UpdateTrigger.MANUAL,
                      deployment_strategy: DeploymentStrategy = DeploymentStrategy.REPLACE,
                      validation_rules: List[ValidationRule] = None,
                      new_configuration: ModelConfiguration = None,
                      triggered_by: str = "user",
                      notes: List[str] = None) -> str:
        """Manually trigger a model update"""
        try:
            update_id = f"{model_name}_{target_version}_{int(time.time())}"
            
            # Get current version
            current_model = self.model_manager.get_active_model(model_name)
            current_version = current_model.version if current_model else "none"
            
            # Create update
            update = ModelUpdate(
                update_id=update_id,
                model_name=model_name,
                current_version=current_version,
                target_version=target_version,
                trigger=trigger,
                deployment_strategy=deployment_strategy,
                new_configuration=new_configuration,
                validation_rules=validation_rules or self._get_default_validation_rules(),
                triggered_by=triggered_by,
                notes=notes or []
            )
            
            self._pending_updates[update_id] = update
            
            logger.info("Model update triggered",
                       update_id=update_id,
                       model_name=model_name,
                       current_version=current_version,
                       target_version=target_version,
                       trigger=trigger.value,
                       triggered_by=triggered_by)
            
            return update_id
            
        except Exception as e:
            logger.error("Error triggering model update",
                        model_name=model_name,
                        target_version=target_version,
                        error=str(e))
            raise
    
    def cancel_update(self, update_id: str, reason: str = "User cancelled") -> bool:
        """Cancel a pending or active update"""
        try:
            if update_id in self._pending_updates:
                update = self._pending_updates[update_id]
                update.status = UpdateStatus.FAILED
                update.rollback_reason = reason
                update.completed_at = time.time()
                
                self._completed_updates.append(update)
                del self._pending_updates[update_id]
                
                logger.info("Pending update cancelled", update_id=update_id, reason=reason)
                return True
            
            elif update_id in self._active_updates:
                update = self._active_updates[update_id]
                update.status = UpdateStatus.FAILED
                update.rollback_reason = reason
                update.completed_at = time.time()
                
                # TODO: Cancel active deployment/testing
                
                self._completed_updates.append(update)
                del self._active_updates[update_id]
                
                logger.info("Active update cancelled", update_id=update_id, reason=reason)
                return True
            
            return False
            
        except Exception as e:
            logger.error("Error cancelling update", update_id=update_id, error=str(e))
            return False
    
    async def _scheduler_loop(self):
        """Background scheduler loop"""
        while not self._shutdown_event.is_set():
            try:
                await self._check_scheduled_updates()
                
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.update_check_interval_minutes * 60
                )
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Scheduler loop error", error=str(e))
                await asyncio.sleep(300)
    
    async def _check_scheduled_updates(self):
        """Check for scheduled updates that need to run"""
        try:
            current_time = time.time()
            
            for schedule_id, schedule_config in self._scheduled_updates.items():
                if (schedule_config["enabled"] and 
                    schedule_config["next_run"] and
                    current_time >= schedule_config["next_run"]):
                    
                    # Trigger the scheduled update
                    update_id = self.trigger_update(
                        model_name=schedule_config["model_name"],
                        target_version=schedule_config["target_version"],
                        trigger=UpdateTrigger.SCHEDULE,
                        deployment_strategy=schedule_config["deployment_strategy"],
                        validation_rules=schedule_config["validation_rules"],
                        triggered_by=f"scheduler:{schedule_id}",
                        notes=[f"Scheduled update: {schedule_config['cron_expression']}"]
                    )
                    
                    # Update schedule
                    schedule_config["last_run"] = current_time
                    schedule_config["next_run"] = self._calculate_next_run(schedule_config["cron_expression"])
                    
                    logger.info("Scheduled update triggered",
                               schedule_id=schedule_id,
                               update_id=update_id,
                               next_run=schedule_config["next_run"])
        
        except Exception as e:
            logger.error("Error checking scheduled updates", error=str(e))
    
    async def _processor_loop(self):
        """Background update processor loop"""
        while not self._shutdown_event.is_set():
            try:
                await self._process_pending_updates()
                await self._monitor_active_updates()
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error("Processor loop error", error=str(e))
                await asyncio.sleep(60)
    
    async def _process_pending_updates(self):
        """Process pending updates"""
        try:
            # Limit concurrent updates
            if len(self._active_updates) >= self.max_concurrent_updates:
                return
            
            # Get next pending update
            pending_ids = list(self._pending_updates.keys())
            if not pending_ids:
                return
            
            update_id = pending_ids[0]  # FIFO processing
            update = self._pending_updates[update_id]
            
            # Move to active updates
            del self._pending_updates[update_id]
            self._active_updates[update_id] = update
            
            # Start processing
            await self._execute_update(update)
        
        except Exception as e:
            logger.error("Error processing pending updates", error=str(e))
    
    async def _execute_update(self, update: ModelUpdate):
        """Execute a model update"""
        try:
            update.status = UpdateStatus.VALIDATING
            update.started_at = time.time()
            
            logger.info("Starting model update execution",
                       update_id=update.update_id,
                       model_name=update.model_name,
                       target_version=update.target_version)
            
            # Phase 1: Validation
            if not await self._run_validation(update):
                update.status = UpdateStatus.FAILED
                update.completed_at = time.time()
                await self._complete_update(update)
                return
            
            # Phase 2: Deployment
            update.status = UpdateStatus.DEPLOYING
            
            if not await self._deploy_model(update):
                update.status = UpdateStatus.FAILED
                update.completed_at = time.time()
                await self._complete_update(update)
                return
            
            # Phase 3: Testing (if applicable)
            if update.deployment_strategy in [DeploymentStrategy.CANARY, DeploymentStrategy.A_B_TEST]:
                update.status = UpdateStatus.TESTING
                
                if not await self._run_testing(update):
                    update.status = UpdateStatus.ROLLED_BACK
                    update.completed_at = time.time()
                    await self._complete_update(update)
                    return
            
            # Phase 4: Completion
            update.status = UpdateStatus.COMPLETED
            update.completed_at = time.time()
            await self._complete_update(update)
            
            logger.info("Model update completed successfully",
                       update_id=update.update_id,
                       duration_minutes=update.duration_minutes)
        
        except Exception as e:
            logger.error("Error executing model update",
                        update_id=update.update_id,
                        error=str(e))
            
            update.status = UpdateStatus.FAILED
            update.rollback_reason = f"Execution error: {str(e)}"
            update.completed_at = time.time()
            await self._complete_update(update)
    
    async def _run_validation(self, update: ModelUpdate) -> bool:
        """Run validation rules for update"""
        try:
            logger.info("Running validation rules",
                       update_id=update.update_id,
                       rule_count=len(update.validation_rules))
            
            all_passed = True
            
            for rule in update.validation_rules:
                start_time = time.time()
                
                try:
                    # Get validator function
                    if rule.validator_function not in self._validators:
                        result = ValidationResult(
                            rule_name=rule.name,
                            passed=False,
                            message=f"Validator function '{rule.validator_function}' not found",
                            execution_time_seconds=0.0
                        )
                    else:
                        validator_func = self._validators[rule.validator_function]
                        
                        # Run validator with timeout
                        try:
                            passed, message, details = await asyncio.wait_for(
                                validator_func(update),
                                timeout=rule.timeout_seconds
                            )
                            
                            result = ValidationResult(
                                rule_name=rule.name,
                                passed=passed,
                                message=message,
                                execution_time_seconds=time.time() - start_time,
                                details=details or {}
                            )
                        
                        except asyncio.TimeoutError:
                            result = ValidationResult(
                                rule_name=rule.name,
                                passed=False,
                                message=f"Validation timed out after {rule.timeout_seconds} seconds",
                                execution_time_seconds=rule.timeout_seconds
                            )
                    
                    update.validation_results.append(result)
                    
                    # Check if this failure should stop the update
                    if not result.passed and rule.required and rule.severity == "error":
                        all_passed = False
                    
                    logger.debug("Validation rule completed",
                               rule_name=rule.name,
                               passed=result.passed,
                               execution_time=result.execution_time_seconds)
                
                except Exception as e:
                    result = ValidationResult(
                        rule_name=rule.name,
                        passed=False,
                        message=f"Validation error: {str(e)}",
                        execution_time_seconds=time.time() - start_time
                    )
                    update.validation_results.append(result)
                    
                    if rule.required and rule.severity == "error":
                        all_passed = False
            
            logger.info("Validation completed",
                       update_id=update.update_id,
                       passed=all_passed,
                       total_rules=len(update.validation_rules),
                       passed_rules=sum(1 for r in update.validation_results if r.passed))
            
            return all_passed
        
        except Exception as e:
            logger.error("Error running validation",
                        update_id=update.update_id,
                        error=str(e))
            return False
    
    async def _deploy_model(self, update: ModelUpdate) -> bool:
        """Deploy the model version"""
        try:
            logger.info("Deploying model version",
                       update_id=update.update_id,
                       model_name=update.model_name,
                       target_version=update.target_version,
                       strategy=update.deployment_strategy.value)
            
            # Create or update model version if needed
            model_version = self.model_manager.get_model_version(update.model_name, update.target_version)
            
            if not model_version:
                if not update.new_configuration:
                    logger.error("No model version found and no configuration provided",
                               update_id=update.update_id)
                    return False
                
                # Create new model version
                model_version = await self.model_manager.create_model_version(
                    model_name=update.model_name,
                    version=update.target_version,
                    configuration=update.new_configuration,
                    description=f"Auto-created by update {update.update_id}",
                    tags=["automated_update"]
                )
            
            # Deploy the model
            deployment = await self.model_manager.deploy_model_version(
                model_name=update.model_name,
                version=update.target_version,
                strategy=update.deployment_strategy,
                deployed_by=f"automation:{update.update_id}"
            )
            
            update.deployment_id = deployment.deployment_id
            
            logger.info("Model deployment initiated",
                       update_id=update.update_id,
                       deployment_id=deployment.deployment_id)
            
            return True
        
        except Exception as e:
            logger.error("Error deploying model",
                        update_id=update.update_id,
                        error=str(e))
            return False
    
    async def _run_testing(self, update: ModelUpdate) -> bool:
        """Run testing phase for canary/A-B deployments"""
        try:
            if update.deployment_strategy == DeploymentStrategy.A_B_TEST:
                # Create A/B test
                current_model = self.model_manager.get_active_model(update.model_name)
                
                if current_model:
                    test_id = self.ab_test_engine.create_test(
                        test_id=f"{update.update_id}_ab_test",
                        name=f"Model Update A/B Test: {update.model_name}",
                        control_model=update.model_name,
                        control_version=current_model.version,
                        treatment_model=update.model_name,
                        treatment_version=update.target_version,
                        description=f"A/B test for model update {update.update_id}"
                    )
                    
                    update.ab_test_id = test_id.test_id
                    
                    logger.info("A/B test created for model update",
                               update_id=update.update_id,
                               ab_test_id=update.ab_test_id)
            
            # For canary deployments, the rollout is managed by the model manager
            # For A/B tests, results will be analyzed separately
            
            return True
        
        except Exception as e:
            logger.error("Error running testing phase",
                        update_id=update.update_id,
                        error=str(e))
            return False
    
    async def _complete_update(self, update: ModelUpdate):
        """Complete an update and move to completed list"""
        try:
            # Move from active to completed
            if update.update_id in self._active_updates:
                del self._active_updates[update.update_id]
            
            self._completed_updates.append(update)
            
            # Limit completed updates list size
            if len(self._completed_updates) > 1000:
                self._completed_updates = self._completed_updates[-1000:]
            
            logger.info("Model update completed",
                       update_id=update.update_id,
                       status=update.status.value,
                       duration_minutes=update.duration_minutes)
        
        except Exception as e:
            logger.error("Error completing update",
                        update_id=update.update_id,
                        error=str(e))
    
    async def _monitor_active_updates(self):
        """Monitor active updates for timeouts and issues"""
        try:
            current_time = time.time()
            timeout_threshold = 3600  # 1 hour timeout
            
            for update_id, update in list(self._active_updates.items()):
                if update.started_at and (current_time - update.started_at) > timeout_threshold:
                    logger.warning("Update timed out",
                                 update_id=update_id,
                                 duration_minutes=update.duration_minutes)
                    
                    update.status = UpdateStatus.FAILED
                    update.rollback_reason = "Update timed out"
                    update.completed_at = current_time
                    await self._complete_update(update)
        
        except Exception as e:
            logger.error("Error monitoring active updates", error=str(e))
    
    async def _monitor_loop(self):
        """Background monitoring loop"""
        while not self._shutdown_event.is_set():
            try:
                await self._monitor_performance_triggers()
                
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=300  # Check every 5 minutes
                )
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Monitor loop error", error=str(e))
                await asyncio.sleep(300)
    
    async def _monitor_performance_triggers(self):
        """Monitor for performance-based update triggers"""
        # TODO: Integrate with performance monitoring to trigger updates
        # when models show degraded performance
        pass
    
    def _register_default_validators(self):
        """Register default validation functions"""
        
        async def validate_model_configuration(update: ModelUpdate) -> tuple[bool, str, dict]:
            """Validate model configuration"""
            try:
                if not update.new_configuration:
                    return True, "No new configuration to validate", {}
                
                config = update.new_configuration
                
                # Basic validation checks
                if not config.provider:
                    return False, "Provider not specified", {}
                
                if not config.model_name:
                    return False, "Model name not specified", {}
                
                if config.temperature < 0 or config.temperature > 2:
                    return False, f"Invalid temperature: {config.temperature}", {}
                
                if config.max_tokens <= 0:
                    return False, f"Invalid max_tokens: {config.max_tokens}", {}
                
                return True, "Configuration validation passed", {
                    "provider": config.provider,
                    "model_name": config.model_name,
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens
                }
                
            except Exception as e:
                return False, f"Configuration validation error: {str(e)}", {}
        
        async def validate_model_availability(update: ModelUpdate) -> tuple[bool, str, dict]:
            """Validate that the target model version is available"""
            try:
                # Check if model version exists or can be created
                model_version = self.model_manager.get_model_version(
                    update.model_name, update.target_version
                )
                
                if model_version:
                    return True, "Model version is available", {
                        "model_id": model_version.model_id,
                        "status": model_version.status.value
                    }
                elif update.new_configuration:
                    return True, "Model version will be created", {
                        "configuration_provided": True
                    }
                else:
                    return False, "Model version not found and no configuration provided", {}
                
            except Exception as e:
                return False, f"Model availability check error: {str(e)}", {}
        
        # Register validators
        self._validators["validate_model_configuration"] = validate_model_configuration
        self._validators["validate_model_availability"] = validate_model_availability
    
    def _get_default_validation_rules(self) -> List[ValidationRule]:
        """Get default validation rules"""
        return [
            ValidationRule(
                name="Model Configuration Validation",
                description="Validate model configuration parameters",
                validator_function="validate_model_configuration",
                severity="error",
                required=True
            ),
            ValidationRule(
                name="Model Availability Check",
                description="Check if target model version is available",
                validator_function="validate_model_availability",
                severity="error",
                required=True
            )
        ]
    
    def _calculate_next_run(self, cron_expression: str) -> float:
        """Calculate next run time from cron expression (simplified)"""
        # This is a simplified implementation
        # In production, use a proper cron parser like croniter
        
        # For now, just add 24 hours for daily schedules
        if "0 0 * * *" in cron_expression:  # Daily at midnight
            return time.time() + 86400  # 24 hours
        elif "0 */6 * * *" in cron_expression:  # Every 6 hours
            return time.time() + 21600  # 6 hours
        else:
            return time.time() + 86400  # Default to 24 hours
    
    def get_update_status(self, update_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific update"""
        # Check active updates
        if update_id in self._active_updates:
            return self._active_updates[update_id].to_dict()
        
        # Check pending updates
        if update_id in self._pending_updates:
            return self._pending_updates[update_id].to_dict()
        
        # Check completed updates
        for update in self._completed_updates:
            if update.update_id == update_id:
                return update.to_dict()
        
        return None
    
    def list_updates(self, model_name: str = None, status: UpdateStatus = None) -> List[Dict[str, Any]]:
        """List updates with optional filtering"""
        all_updates = (
            list(self._pending_updates.values()) +
            list(self._active_updates.values()) +
            self._completed_updates
        )
        
        # Apply filters
        filtered_updates = all_updates
        
        if model_name:
            filtered_updates = [u for u in filtered_updates if u.model_name == model_name]
        
        if status:
            filtered_updates = [u for u in filtered_updates if u.status == status]
        
        # Sort by creation time (newest first)
        filtered_updates.sort(key=lambda u: u.created_at, reverse=True)
        
        return [u.to_dict() for u in filtered_updates]
    
    def get_automation_statistics(self) -> Dict[str, Any]:
        """Get comprehensive automation statistics"""
        try:
            return {
                "pending_updates": len(self._pending_updates),
                "active_updates": len(self._active_updates),
                "completed_updates": len(self._completed_updates),
                "scheduled_updates": len(self._scheduled_updates),
                "registered_validators": len(self._validators),
                "max_concurrent_updates": self.max_concurrent_updates,
                "update_check_interval_minutes": self.update_check_interval_minutes,
                "status_breakdown": {
                    status.value: len([u for u in self._completed_updates if u.status == status])
                    for status in UpdateStatus
                },
                "trigger_breakdown": {
                    trigger.value: len([u for u in self._completed_updates if u.trigger == trigger])
                    for trigger in UpdateTrigger
                }
            }
        
        except Exception as e:
            logger.error("Error getting automation statistics", error=str(e))
            return {"error": str(e)}