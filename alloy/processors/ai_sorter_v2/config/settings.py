"""
Configuration Management for Multi-Provider AI System

Comprehensive configuration system supporting multiple AI providers,
environment-specific settings, and enterprise deployment patterns.
"""

import os
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path
import yaml
import structlog

from ..providers.openai_provider import OpenAIConfig
from ..providers.claude_provider import ClaudeConfig
from ..providers.ai_provider_manager import AIManagerConfig
from ..utils.health_checker import HealthCheckConfig
from ..utils.metrics import MetricsConfig

logger = structlog.get_logger(__name__)


@dataclass
class GrokConfig:
    """Configuration for Grok AI provider"""
    enabled: bool = False
    api_key: str = ""
    model: str = "grok-beta"
    temperature: float = 0.3
    max_tokens: int = 1000
    max_retries: int = 3
    request_timeout: int = 30
    base_url: str = "https://api.x.ai/v1"
    
    # Rate limiting
    requests_per_minute: int = 50
    tokens_per_minute: int = 5000
    
    # Cost optimization
    use_cheaper_model_fallback: bool = False
    cheaper_model: str = "grok-beta"  # Only one model available currently
    
    def __post_init__(self):
        # Get from environment if not provided
        if not self.api_key:
            self.api_key = os.getenv("GROK_API_KEY", "")
        
        # Validate configuration
        if self.enabled and not self.api_key:
            logger.warning("Grok provider enabled but no API key provided")
            self.enabled = False


@dataclass
class CORSConfig:
    """CORS configuration"""
    allowed_origins: List[str] = field(default_factory=lambda: ["*"])
    allow_credentials: bool = True
    allowed_methods: List[str] = field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE"])
    allowed_headers: List[str] = field(default_factory=lambda: ["*"])


@dataclass
class SecurityConfig:
    """Security configuration"""
    # API Security
    require_api_key: bool = False
    api_key_header: str = "X-API-Key"
    valid_api_keys: List[str] = field(default_factory=list)
    
    # Rate limiting
    enable_rate_limiting: bool = True
    requests_per_minute: int = 1000
    requests_per_hour: int = 10000
    
    # Request validation
    max_request_size_mb: int = 10
    max_items_per_batch: int = 1000
    
    # Logging
    log_requests: bool = True
    log_responses: bool = False  # May contain sensitive data
    mask_sensitive_data: bool = True
    
    def __post_init__(self):
        # Load API keys from environment
        env_api_keys = os.getenv("AI_SORTER_API_KEYS", "")
        if env_api_keys:
            self.valid_api_keys.extend(env_api_keys.split(","))
        
        # Enable API key requirement if keys are provided
        if self.valid_api_keys:
            self.require_api_key = True


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    format: str = "json"  # json or console
    include_timestamp: bool = True
    include_caller: bool = True
    log_file: Optional[str] = None
    
    # Structured logging fields
    service_name: str = "ai-sorter-v2"
    service_version: str = "2.3.0"
    environment: str = "production"
    
    def __post_init__(self):
        # Override from environment
        self.level = os.getenv("LOG_LEVEL", self.level)
        self.environment = os.getenv("ENVIRONMENT", self.environment)
        if os.getenv("LOG_FILE"):
            self.log_file = os.getenv("LOG_FILE")


@dataclass
class DeploymentConfig:
    """Deployment-specific configuration"""
    # Service configuration
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    
    # Health checks
    health_check_path: str = "/health"
    readiness_check_path: str = "/ready"
    liveness_check_path: str = "/health/live"
    
    # Metrics
    metrics_path: str = "/metrics"
    enable_prometheus_metrics: bool = True
    
    # Graceful shutdown
    shutdown_timeout: int = 30
    
    def __post_init__(self):
        # Override from environment
        self.host = os.getenv("AI_SORTER_HOST", self.host)
        self.port = int(os.getenv("AI_SORTER_PORT", str(self.port)))
        self.workers = int(os.getenv("AI_SORTER_WORKERS", str(self.workers)))


@dataclass
class Settings:
    """Main configuration class"""
    # Provider configurations
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    grok: GrokConfig = field(default_factory=GrokConfig)
    
    # System configurations
    ai_manager: AIManagerConfig = field(default_factory=AIManagerConfig)
    health_check: HealthCheckConfig = field(default_factory=HealthCheckConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    
    # Service configurations
    cors: CORSConfig = field(default_factory=CORSConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    deployment: DeploymentConfig = field(default_factory=DeploymentConfig)
    
    # Feature flags
    enable_debug_endpoints: bool = False
    enable_admin_endpoints: bool = False
    enable_testing_endpoints: bool = False
    
    def __post_init__(self):
        """Post-initialization configuration"""
        # Load from environment variables
        self._load_from_environment()
        
        # Load from configuration file if specified
        config_file = os.getenv("AI_SORTER_CONFIG_FILE")
        if config_file:
            self._load_from_file(config_file)
        
        # Validate configuration
        self._validate_configuration()
        
        logger.info("Configuration loaded",
                   openai_enabled=self.openai.enabled,
                   claude_enabled=self.claude.enabled,
                   grok_enabled=self.grok.enabled,
                   environment=self.logging.environment)
    
    def _load_from_environment(self):
        """Load configuration from environment variables"""
        try:
            # Feature flags
            self.enable_debug_endpoints = os.getenv("ENABLE_DEBUG_ENDPOINTS", "false").lower() == "true"
            self.enable_admin_endpoints = os.getenv("ENABLE_ADMIN_ENDPOINTS", "false").lower() == "true"
            self.enable_testing_endpoints = os.getenv("ENABLE_TESTING_ENDPOINTS", "false").lower() == "true"
            
            # OpenAI configuration
            if os.getenv("OPENAI_API_KEY"):
                self.openai.enabled = True
                self.openai.api_key = os.getenv("OPENAI_API_KEY")
            
            if os.getenv("OPENAI_MODEL"):
                self.openai.model = os.getenv("OPENAI_MODEL")
            
            if os.getenv("OPENAI_ORGANIZATION"):
                self.openai.organization = os.getenv("OPENAI_ORGANIZATION")
            
            # Claude configuration
            if os.getenv("CLAUDE_API_KEY"):
                self.claude.enabled = True
                self.claude.api_key = os.getenv("CLAUDE_API_KEY")
            
            if os.getenv("CLAUDE_MODEL"):
                self.claude.model = os.getenv("CLAUDE_MODEL")
            
            # Grok configuration
            if os.getenv("GROK_API_KEY"):
                self.grok.enabled = True
                self.grok.api_key = os.getenv("GROK_API_KEY")
            
            # AI Manager configuration
            if os.getenv("AI_SELECTION_STRATEGY"):
                self.ai_manager.selection_strategy = os.getenv("AI_SELECTION_STRATEGY")
            
            if os.getenv("AI_ENABLE_FALLBACK"):
                self.ai_manager.enable_fallback = os.getenv("AI_ENABLE_FALLBACK").lower() == "true"
            
            logger.debug("Environment configuration loaded")
            
        except Exception as e:
            logger.error("Error loading environment configuration", error=str(e))
    
    def _load_from_file(self, config_file: str):
        """Load configuration from YAML file"""
        try:
            config_path = Path(config_file)
            if not config_path.exists():
                logger.warning("Configuration file not found", file=config_file)
                return
            
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            
            if not config_data:
                logger.warning("Empty configuration file", file=config_file)
                return
            
            # Update configurations based on file data
            self._update_from_dict(config_data)
            
            logger.info("Configuration file loaded", file=config_file)
            
        except Exception as e:
            logger.error("Error loading configuration file", file=config_file, error=str(e))
    
    def _update_from_dict(self, config_data: Dict[str, Any]):
        """Update configuration from dictionary"""
        try:
            # Provider configurations
            if "openai" in config_data:
                self._update_openai_config(config_data["openai"])
            
            if "claude" in config_data:
                self._update_claude_config(config_data["claude"])
            
            if "grok" in config_data:
                self._update_grok_config(config_data["grok"])
            
            # System configurations
            if "ai_manager" in config_data:
                self._update_ai_manager_config(config_data["ai_manager"])
            
            if "health_check" in config_data:
                self._update_health_check_config(config_data["health_check"])
            
            if "security" in config_data:
                self._update_security_config(config_data["security"])
            
            # Feature flags
            if "features" in config_data:
                features = config_data["features"]
                self.enable_debug_endpoints = features.get("debug_endpoints", self.enable_debug_endpoints)
                self.enable_admin_endpoints = features.get("admin_endpoints", self.enable_admin_endpoints)
                self.enable_testing_endpoints = features.get("testing_endpoints", self.enable_testing_endpoints)
            
        except Exception as e:
            logger.error("Error updating configuration from dict", error=str(e))
    
    def _update_openai_config(self, config: Dict[str, Any]):
        """Update OpenAI configuration"""
        for key, value in config.items():
            if hasattr(self.openai, key):
                setattr(self.openai, key, value)
    
    def _update_claude_config(self, config: Dict[str, Any]):
        """Update Claude configuration"""
        for key, value in config.items():
            if hasattr(self.claude, key):
                setattr(self.claude, key, value)
    
    def _update_grok_config(self, config: Dict[str, Any]):
        """Update Grok configuration"""
        for key, value in config.items():
            if hasattr(self.grok, key):
                setattr(self.grok, key, value)
    
    def _update_ai_manager_config(self, config: Dict[str, Any]):
        """Update AI Manager configuration"""
        for key, value in config.items():
            if hasattr(self.ai_manager, key):
                setattr(self.ai_manager, key, value)
    
    def _update_health_check_config(self, config: Dict[str, Any]):
        """Update Health Check configuration"""
        for key, value in config.items():
            if hasattr(self.health_check, key):
                setattr(self.health_check, key, value)
    
    def _update_security_config(self, config: Dict[str, Any]):
        """Update Security configuration"""
        for key, value in config.items():
            if hasattr(self.security, key):
                setattr(self.security, key, value)
    
    def _validate_configuration(self):
        """Validate the complete configuration"""
        try:
            # Check that at least one provider is enabled
            enabled_providers = []
            if self.openai.enabled and self.openai.api_key:
                enabled_providers.append("openai")
            if self.claude.enabled and self.claude.api_key:
                enabled_providers.append("claude")
            if self.grok.enabled and self.grok.api_key:
                enabled_providers.append("grok")
            
            if not enabled_providers:
                raise ValueError("At least one AI provider must be enabled and configured")
            
            # Validate AI manager configuration
            valid_strategies = ["health_weighted", "round_robin", "cost_optimized"]
            if self.ai_manager.selection_strategy not in valid_strategies:
                logger.warning("Invalid selection strategy, using default",
                             strategy=self.ai_manager.selection_strategy,
                             valid_strategies=valid_strategies)
                self.ai_manager.selection_strategy = "health_weighted"
            
            # Validate security configuration
            if self.security.require_api_key and not self.security.valid_api_keys:
                logger.warning("API key authentication enabled but no valid keys configured")
            
            # Validate deployment configuration
            if self.deployment.port < 1 or self.deployment.port > 65535:
                raise ValueError(f"Invalid port number: {self.deployment.port}")
            
            logger.info("Configuration validation completed",
                       enabled_providers=enabled_providers,
                       selection_strategy=self.ai_manager.selection_strategy)
            
        except Exception as e:
            logger.error("Configuration validation failed", error=str(e))
            raise
    
    def get_enabled_providers(self) -> List[str]:
        """Get list of enabled provider names"""
        enabled = []
        if self.openai.enabled and self.openai.api_key:
            enabled.append("openai")
        if self.claude.enabled and self.claude.api_key:
            enabled.append("claude")
        if self.grok.enabled and self.grok.api_key:
            enabled.append("grok")
        return enabled
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary (for serialization)"""
        return {
            "openai": {
                "enabled": self.openai.enabled,
                "model": self.openai.model,
                "organization": self.openai.organization,
                # Note: API key is not included for security
            },
            "claude": {
                "enabled": self.claude.enabled,
                "model": self.claude.model,
                # Note: API key is not included for security
            },
            "grok": {
                "enabled": self.grok.enabled,
                "model": self.grok.model,
                # Note: API key is not included for security
            },
            "ai_manager": {
                "selection_strategy": self.ai_manager.selection_strategy,
                "enable_fallback": self.ai_manager.enable_fallback,
                "max_concurrent_requests": self.ai_manager.max_concurrent_requests,
            },
            "features": {
                "debug_endpoints": self.enable_debug_endpoints,
                "admin_endpoints": self.enable_admin_endpoints,
                "testing_endpoints": self.enable_testing_endpoints,
            },
            "deployment": {
                "host": self.deployment.host,
                "port": self.deployment.port,
                "workers": self.deployment.workers,
            },
            "logging": {
                "level": self.logging.level,
                "environment": self.logging.environment,
            }
        }
    
    def save_to_file(self, file_path: str):
        """Save configuration to YAML file"""
        try:
            config_dict = self.to_dict()
            
            with open(file_path, 'w') as f:
                yaml.dump(config_dict, f, default_flow_style=False, indent=2)
            
            logger.info("Configuration saved to file", file=file_path)
            
        except Exception as e:
            logger.error("Error saving configuration to file", file=file_path, error=str(e))
            raise


def load_settings(config_file: Optional[str] = None) -> Settings:
    """Load settings with optional configuration file"""
    if config_file:
        os.environ["AI_SORTER_CONFIG_FILE"] = config_file
    
    return Settings()


def create_example_config(file_path: str):
    """Create an example configuration file"""
    example_config = {
        "openai": {
            "enabled": True,
            "model": "gpt-4",
            "temperature": 0.3,
            "max_tokens": 1000,
            "use_cheaper_model_fallback": True,
            "cheaper_model": "gpt-3.5-turbo"
        },
        "claude": {
            "enabled": True,
            "model": "claude-3-sonnet-20240229",
            "temperature": 0.3,
            "max_tokens": 1000,
            "use_model_fallback": True
        },
        "grok": {
            "enabled": False,
            "model": "grok-beta",
            "temperature": 0.3,
            "max_tokens": 1000
        },
        "ai_manager": {
            "selection_strategy": "health_weighted",
            "enable_fallback": True,
            "max_fallback_attempts": 3,
            "max_concurrent_requests": 100
        },
        "health_check": {
            "primary_check_interval": 30,
            "detailed_check_interval": 120,
            "response_time_threshold": 5.0
        },
        "security": {
            "require_api_key": False,
            "enable_rate_limiting": True,
            "requests_per_minute": 1000,
            "max_items_per_batch": 1000
        },
        "features": {
            "debug_endpoints": False,
            "admin_endpoints": False,
            "testing_endpoints": False
        },
        "deployment": {
            "host": "0.0.0.0",
            "port": 8000,
            "workers": 1
        },
        "logging": {
            "level": "INFO",
            "environment": "production"
        }
    }
    
    try:
        with open(file_path, 'w') as f:
            yaml.dump(example_config, f, default_flow_style=False, indent=2)
        
        logger.info("Example configuration created", file=file_path)
        
    except Exception as e:
        logger.error("Error creating example configuration", file=file_path, error=str(e))
        raise