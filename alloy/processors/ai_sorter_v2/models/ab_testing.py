"""
A/B Testing Engine for AI Model Comparison

Statistical A/B testing framework for comparing AI model performance
with proper significance testing and automated decision making.
"""

import asyncio
import time
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import structlog
import math

logger = structlog.get_logger(__name__)


class ABTestStatus(Enum):
    """A/B test status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


class ABTestResult(Enum):
    """A/B test result"""
    CONTROL_WINS = "control_wins"
    TREATMENT_WINS = "treatment_wins"
    NO_DIFFERENCE = "no_difference"
    INCONCLUSIVE = "inconclusive"


@dataclass
class ABTestVariant:
    """A/B test variant (control or treatment)"""
    name: str
    model_name: str
    model_version: str
    traffic_percentage: float = 50.0
    
    # Metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_response_time: float = 0.0
    total_confidence_score: float = 0.0
    total_cost: float = 0.0
    
    # Performance metrics
    response_times: List[float] = field(default_factory=list)
    confidence_scores: List[float] = field(default_factory=list)
    
    def update_metrics(self, response_time: float, success: bool, confidence: float = 0.0, cost: float = 0.0):
        """Update variant metrics"""
        self.total_requests += 1
        
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
        
        self.total_response_time += response_time
        self.total_confidence_score += confidence
        self.total_cost += cost
        
        # Store individual values for statistical analysis (with limits)
        if len(self.response_times) < 10000:  # Limit memory usage
            self.response_times.append(response_time)
        if len(self.confidence_scores) < 10000:
            self.confidence_scores.append(confidence)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        return self.successful_requests / self.total_requests if self.total_requests > 0 else 0.0
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate"""
        return self.failed_requests / self.total_requests if self.total_requests > 0 else 0.0
    
    @property
    def avg_response_time(self) -> float:
        """Calculate average response time"""
        return self.total_response_time / self.total_requests if self.total_requests > 0 else 0.0
    
    @property
    def avg_confidence_score(self) -> float:
        """Calculate average confidence score"""
        return self.total_confidence_score / self.total_requests if self.total_requests > 0 else 0.0
    
    @property
    def cost_per_request(self) -> float:
        """Calculate cost per request"""
        return self.total_cost / self.total_requests if self.total_requests > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert variant to dictionary"""
        return {
            "name": self.name,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "traffic_percentage": self.traffic_percentage,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": self.success_rate,
            "error_rate": self.error_rate,
            "avg_response_time": self.avg_response_time,
            "avg_confidence_score": self.avg_confidence_score,
            "cost_per_request": self.cost_per_request,
            "total_cost": self.total_cost
        }


@dataclass
class ABTestConfiguration:
    """A/B test configuration"""
    test_id: str
    name: str
    description: str
    
    # Test setup
    control_variant: ABTestVariant
    treatment_variant: ABTestVariant
    
    # Test parameters
    confidence_level: float = 0.95  # 95% confidence level
    minimum_detectable_effect: float = 0.05  # 5% minimum effect size
    power: float = 0.8  # 80% statistical power
    
    # Duration and sample size
    max_duration_hours: int = 168  # 1 week
    min_sample_size_per_variant: int = 1000
    max_sample_size_per_variant: int = 100000
    
    # Success criteria
    primary_metric: str = "success_rate"  # success_rate, response_time, confidence_score
    secondary_metrics: List[str] = field(default_factory=lambda: ["response_time", "confidence_score"])
    
    # Auto-stopping rules
    early_stopping_enabled: bool = True
    futility_threshold: float = 0.01  # Stop if probability of finding effect < 1%
    harm_threshold: float = 0.95  # Stop if treatment is significantly worse
    
    # Traffic allocation
    ramp_up_enabled: bool = True
    initial_traffic_percentage: float = 10.0
    ramp_up_interval_hours: int = 24
    
    def calculate_required_sample_size(self) -> int:
        """Calculate required sample size based on test parameters"""
        try:
            # Use simplified formula for sample size calculation
            # n = (Z_α/2 + Z_β)² * 2 * p * (1-p) / δ²
            # Where p is baseline rate, δ is minimum detectable effect
            
            # Z-scores for confidence level and power
            z_alpha = 1.96 if self.confidence_level == 0.95 else 2.58  # 95% or 99%
            z_beta = 0.84 if self.power == 0.8 else 1.28  # 80% or 90% power
            
            # Assume baseline success rate of 0.95
            baseline_rate = 0.95
            
            # Calculate sample size
            numerator = (z_alpha + z_beta) ** 2 * 2 * baseline_rate * (1 - baseline_rate)
            denominator = self.minimum_detectable_effect ** 2
            
            sample_size = int(numerator / denominator)
            
            # Apply bounds
            sample_size = max(self.min_sample_size_per_variant, sample_size)
            sample_size = min(self.max_sample_size_per_variant, sample_size)
            
            return sample_size
            
        except Exception as e:
            logger.error("Error calculating sample size", error=str(e))
            return self.min_sample_size_per_variant


@dataclass
class ABTestResults:
    """A/B test statistical results"""
    test_id: str
    status: ABTestResult
    confidence_level: float
    p_value: float
    effect_size: float
    confidence_interval: Tuple[float, float]
    
    # Metric comparisons
    primary_metric_results: Dict[str, Any]
    secondary_metric_results: Dict[str, Dict[str, Any]]
    
    # Recommendations
    winning_variant: str
    recommendation: str
    statistical_significance: bool
    practical_significance: bool
    
    # Meta information
    calculated_at: float = field(default_factory=time.time)
    total_requests: int = 0
    test_duration_hours: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert results to dictionary"""
        return {
            "test_id": self.test_id,
            "status": self.status.value,
            "confidence_level": self.confidence_level,
            "p_value": self.p_value,
            "effect_size": self.effect_size,
            "confidence_interval": list(self.confidence_interval),
            "primary_metric_results": self.primary_metric_results,
            "secondary_metric_results": self.secondary_metric_results,
            "winning_variant": self.winning_variant,
            "recommendation": self.recommendation,
            "statistical_significance": self.statistical_significance,
            "practical_significance": self.practical_significance,
            "calculated_at": self.calculated_at,
            "total_requests": self.total_requests,
            "test_duration_hours": self.test_duration_hours
        }


class ABTestEngine:
    """A/B Testing Engine for AI Model Comparison"""
    
    def __init__(self):
        self._active_tests: Dict[str, ABTestConfiguration] = {}
        self._test_results: Dict[str, ABTestResults] = {}
        self._test_start_times: Dict[str, float] = {}
        
        # Background tasks
        self._analysis_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        logger.info("A/B Testing Engine initialized")
    
    async def start(self):
        """Start background analysis task"""
        self._analysis_task = asyncio.create_task(self._analysis_loop())
        logger.info("A/B Testing Engine started")
    
    async def stop(self):
        """Stop background tasks"""
        self._shutdown_event.set()
        if self._analysis_task and not self._analysis_task.done():
            self._analysis_task.cancel()
            try:
                await self._analysis_task
            except asyncio.CancelledError:
                pass
        logger.info("A/B Testing Engine stopped")
    
    def create_test(self, 
                   test_id: str,
                   name: str,
                   control_model: str,
                   control_version: str,
                   treatment_model: str,
                   treatment_version: str,
                   description: str = "",
                   **kwargs) -> ABTestConfiguration:
        """Create a new A/B test"""
        try:
            if test_id in self._active_tests:
                raise ValueError(f"Test {test_id} already exists")
            
            # Create variants
            control_variant = ABTestVariant(
                name="control",
                model_name=control_model,
                model_version=control_version,
                traffic_percentage=50.0
            )
            
            treatment_variant = ABTestVariant(
                name="treatment",
                model_name=treatment_model,
                model_version=treatment_version,
                traffic_percentage=50.0
            )
            
            # Create test configuration
            test_config = ABTestConfiguration(
                test_id=test_id,
                name=name,
                description=description,
                control_variant=control_variant,
                treatment_variant=treatment_variant,
                **kwargs
            )
            
            # Calculate required sample size
            required_sample_size = test_config.calculate_required_sample_size()
            
            self._active_tests[test_id] = test_config
            self._test_start_times[test_id] = time.time()
            
            logger.info("A/B test created",
                       test_id=test_id,
                       name=name,
                       control=f"{control_model}:{control_version}",
                       treatment=f"{treatment_model}:{treatment_version}",
                       required_sample_size=required_sample_size)
            
            return test_config
            
        except Exception as e:
            logger.error("Error creating A/B test",
                        test_id=test_id,
                        error=str(e))
            raise
    
    def should_route_to_treatment(self, test_id: str, user_id: str = None, request_id: str = None) -> bool:
        """Determine if request should go to treatment variant"""
        try:
            test_config = self._active_tests.get(test_id)
            if not test_config:
                return False
            
            # Create hash seed from user_id or request_id for consistent routing
            hash_input = user_id or request_id or str(time.time())
            hash_value = int(hashlib.md5(hash_input.encode()).hexdigest()[:8], 16)
            
            # Determine variant based on hash and traffic percentage
            hash_percentage = (hash_value % 100) + 1
            return hash_percentage <= test_config.treatment_variant.traffic_percentage
            
        except Exception as e:
            logger.error("Error determining variant routing",
                        test_id=test_id,
                        error=str(e))
            return False
    
    def record_result(self, 
                     test_id: str,
                     variant: str,
                     response_time: float,
                     success: bool,
                     confidence: float = 0.0,
                     cost: float = 0.0):
        """Record test result for a variant"""
        try:
            test_config = self._active_tests.get(test_id)
            if not test_config:
                logger.warning("Test not found for result recording", test_id=test_id)
                return
            
            # Update appropriate variant
            if variant == "control":
                test_config.control_variant.update_metrics(response_time, success, confidence, cost)
            elif variant == "treatment":
                test_config.treatment_variant.update_metrics(response_time, success, confidence, cost)
            else:
                logger.warning("Unknown variant", test_id=test_id, variant=variant)
                return
            
            logger.debug("A/B test result recorded",
                        test_id=test_id,
                        variant=variant,
                        response_time=response_time,
                        success=success)
            
        except Exception as e:
            logger.error("Error recording A/B test result",
                        test_id=test_id,
                        variant=variant,
                        error=str(e))
    
    def analyze_test(self, test_id: str) -> Optional[ABTestResults]:
        """Analyze A/B test results"""
        try:
            test_config = self._active_tests.get(test_id)
            if not test_config:
                return None
            
            control = test_config.control_variant
            treatment = test_config.treatment_variant
            
            # Check if we have minimum sample size
            if (control.total_requests < test_config.min_sample_size_per_variant or
                treatment.total_requests < test_config.min_sample_size_per_variant):
                return None
            
            # Analyze primary metric
            primary_results = self._analyze_metric(
                control, treatment, test_config.primary_metric, test_config.confidence_level
            )
            
            # Analyze secondary metrics
            secondary_results = {}
            for metric in test_config.secondary_metrics:
                secondary_results[metric] = self._analyze_metric(
                    control, treatment, metric, test_config.confidence_level
                )
            
            # Determine overall result
            p_value = primary_results["p_value"]
            effect_size = primary_results["effect_size"]
            confidence_interval = primary_results["confidence_interval"]
            
            # Statistical significance
            alpha = 1 - test_config.confidence_level
            statistical_significance = p_value < alpha
            
            # Practical significance
            practical_significance = abs(effect_size) >= test_config.minimum_detectable_effect
            
            # Determine winner
            if statistical_significance and practical_significance:
                if effect_size > 0:
                    status = ABTestResult.TREATMENT_WINS
                    winning_variant = "treatment"
                    recommendation = f"Deploy treatment variant ({treatment.model_name}:{treatment.model_version})"
                else:
                    status = ABTestResult.CONTROL_WINS
                    winning_variant = "control"
                    recommendation = f"Keep control variant ({control.model_name}:{control.model_version})"
            elif statistical_significance:
                status = ABTestResult.NO_DIFFERENCE
                winning_variant = "control"  # Default to control when no practical difference
                recommendation = "No practical difference detected, keep current model"
            else:
                status = ABTestResult.INCONCLUSIVE
                winning_variant = "control"
                recommendation = "Results inconclusive, continue test or increase sample size"
            
            # Calculate test duration
            start_time = self._test_start_times.get(test_id, time.time())
            test_duration_hours = (time.time() - start_time) / 3600
            
            # Create results
            results = ABTestResults(
                test_id=test_id,
                status=status,
                confidence_level=test_config.confidence_level,
                p_value=p_value,
                effect_size=effect_size,
                confidence_interval=confidence_interval,
                primary_metric_results=primary_results,
                secondary_metric_results=secondary_results,
                winning_variant=winning_variant,
                recommendation=recommendation,
                statistical_significance=statistical_significance,
                practical_significance=practical_significance,
                total_requests=control.total_requests + treatment.total_requests,
                test_duration_hours=test_duration_hours
            )
            
            self._test_results[test_id] = results
            
            logger.info("A/B test analysis completed",
                       test_id=test_id,
                       status=status.value,
                       winning_variant=winning_variant,
                       p_value=p_value,
                       effect_size=effect_size)
            
            return results
            
        except Exception as e:
            logger.error("Error analyzing A/B test",
                        test_id=test_id,
                        error=str(e))
            return None
    
    def _analyze_metric(self, 
                       control: ABTestVariant, 
                       treatment: ABTestVariant, 
                       metric: str, 
                       confidence_level: float) -> Dict[str, Any]:
        """Analyze specific metric between variants"""
        try:
            # Get metric values
            if metric == "success_rate":
                control_value = control.success_rate
                treatment_value = treatment.success_rate
                control_n = control.total_requests
                treatment_n = treatment.total_requests
                
                # Two-proportion z-test
                pooled_p = (control.successful_requests + treatment.successful_requests) / (control_n + treatment_n)
                se = math.sqrt(pooled_p * (1 - pooled_p) * (1/control_n + 1/treatment_n))
                
            elif metric == "response_time":
                control_value = control.avg_response_time
                treatment_value = treatment.avg_response_time
                control_n = len(control.response_times)
                treatment_n = len(treatment.response_times)
                
                if control_n == 0 or treatment_n == 0:
                    return {"error": "Insufficient data for response time analysis"}
                
                # Two-sample t-test (simplified)
                control_var = self._calculate_variance(control.response_times)
                treatment_var = self._calculate_variance(treatment.response_times)
                se = math.sqrt(control_var/control_n + treatment_var/treatment_n) if control_var > 0 and treatment_var > 0 else 0.1
                
            elif metric == "confidence_score":
                control_value = control.avg_confidence_score
                treatment_value = treatment.avg_confidence_score
                control_n = len(control.confidence_scores)
                treatment_n = len(control.confidence_scores)
                
                if control_n == 0 or treatment_n == 0:
                    return {"error": "Insufficient data for confidence score analysis"}
                
                # Two-sample t-test (simplified)
                control_var = self._calculate_variance(control.confidence_scores)
                treatment_var = self._calculate_variance(treatment.confidence_scores)
                se = math.sqrt(control_var/control_n + treatment_var/treatment_n) if control_var > 0 and treatment_var > 0 else 0.01
                
            else:
                return {"error": f"Unknown metric: {metric}"}
            
            if se == 0:
                se = 0.001  # Avoid division by zero
            
            # Calculate z-score and p-value
            effect_size = treatment_value - control_value
            z_score = effect_size / se
            
            # Simplified p-value calculation (two-tailed)
            p_value = 2 * (1 - self._normal_cdf(abs(z_score)))
            
            # Confidence interval
            z_critical = 1.96 if confidence_level == 0.95 else 2.58
            margin_error = z_critical * se
            confidence_interval = (effect_size - margin_error, effect_size + margin_error)
            
            return {
                "metric": metric,
                "control_value": control_value,
                "treatment_value": treatment_value,
                "effect_size": effect_size,
                "relative_change": (effect_size / control_value * 100) if control_value != 0 else 0,
                "z_score": z_score,
                "p_value": p_value,
                "confidence_interval": confidence_interval,
                "standard_error": se,
                "control_n": control_n if metric == "success_rate" else len(getattr(control, f"{metric.replace('_', '')}s", [])),
                "treatment_n": treatment_n if metric == "success_rate" else len(getattr(treatment, f"{metric.replace('_', '')}s", []))
            }
            
        except Exception as e:
            logger.error("Error analyzing metric",
                        metric=metric,
                        error=str(e))
            return {"error": str(e)}
    
    def _calculate_variance(self, values: List[float]) -> float:
        """Calculate variance of a list of values"""
        if len(values) < 2:
            return 1.0  # Default variance
        
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return variance
    
    def _normal_cdf(self, x: float) -> float:
        """Simplified normal cumulative distribution function"""
        # Approximation using error function
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))
    
    def get_test_status(self, test_id: str) -> Optional[Dict[str, Any]]:
        """Get current test status and metrics"""
        try:
            test_config = self._active_tests.get(test_id)
            if not test_config:
                return None
            
            start_time = self._test_start_times.get(test_id, time.time())
            duration_hours = (time.time() - start_time) / 3600
            
            return {
                "test_id": test_id,
                "name": test_config.name,
                "description": test_config.description,
                "duration_hours": duration_hours,
                "max_duration_hours": test_config.max_duration_hours,
                "control_variant": test_config.control_variant.to_dict(),
                "treatment_variant": test_config.treatment_variant.to_dict(),
                "required_sample_size": test_config.calculate_required_sample_size(),
                "progress": {
                    "control_progress": min(1.0, test_config.control_variant.total_requests / test_config.min_sample_size_per_variant),
                    "treatment_progress": min(1.0, test_config.treatment_variant.total_requests / test_config.min_sample_size_per_variant)
                },
                "ready_for_analysis": (
                    test_config.control_variant.total_requests >= test_config.min_sample_size_per_variant and
                    test_config.treatment_variant.total_requests >= test_config.min_sample_size_per_variant
                )
            }
            
        except Exception as e:
            logger.error("Error getting test status",
                        test_id=test_id,
                        error=str(e))
            return None
    
    def stop_test(self, test_id: str, reason: str = "Manual stop") -> bool:
        """Stop an active A/B test"""
        try:
            if test_id not in self._active_tests:
                return False
            
            # Analyze final results
            final_results = self.analyze_test(test_id)
            
            if final_results:
                final_results.recommendation += f" (Test stopped: {reason})"
                self._test_results[test_id] = final_results
            
            # Remove from active tests
            del self._active_tests[test_id]
            
            logger.info("A/B test stopped",
                       test_id=test_id,
                       reason=reason)
            
            return True
            
        except Exception as e:
            logger.error("Error stopping A/B test",
                        test_id=test_id,
                        error=str(e))
            return False
    
    def list_active_tests(self) -> List[str]:
        """List all active test IDs"""
        return list(self._active_tests.keys())
    
    def get_test_results(self, test_id: str) -> Optional[ABTestResults]:
        """Get test results"""
        return self._test_results.get(test_id)
    
    async def _analysis_loop(self):
        """Background analysis loop"""
        while not self._shutdown_event.is_set():
            try:
                await self._run_periodic_analysis()
                
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=300  # Run every 5 minutes
                )
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Analysis loop error", error=str(e))
                await asyncio.sleep(60)
    
    async def _run_periodic_analysis(self):
        """Run periodic analysis on all active tests"""
        for test_id in list(self._active_tests.keys()):
            try:
                test_config = self._active_tests[test_id]
                
                # Check if test should be stopped due to duration
                start_time = self._test_start_times.get(test_id, time.time())
                duration_hours = (time.time() - start_time) / 3600
                
                if duration_hours >= test_config.max_duration_hours:
                    self.stop_test(test_id, "Maximum duration reached")
                    continue
                
                # Analyze current results
                results = self.analyze_test(test_id)
                
                if results and test_config.early_stopping_enabled:
                    # Check early stopping conditions
                    if results.statistical_significance and results.practical_significance:
                        self.stop_test(test_id, "Early stopping: significant result detected")
                    elif results.p_value > 0.99:  # Very unlikely to find significance
                        self.stop_test(test_id, "Early stopping: futility threshold reached")
                
            except Exception as e:
                logger.error("Error in periodic analysis",
                           test_id=test_id,
                           error=str(e))