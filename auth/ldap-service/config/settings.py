"""
Configuration Settings for Enterprise Authentication Service

Provides centralized configuration management with environment variable support,
validation, and security best practices.
"""

import os
from typing import List, Dict, Optional
from pydantic import BaseSettings, validator, SecretStr
from dataclasses import dataclass

from auth.ldap_client import LDAPConfig
from auth.saml_client import SAMLConfig  
from auth.jwt_manager import JWTConfig
from auth.rbac_engine import RBACConfig
from auth.audit_logger import AuditConfig


class CORSSettings(BaseSettings):
    """CORS configuration"""
    allowed_origins: List[str] = ["*"]
    allowed_methods: List[str] = ["*"]
    allowed_headers: List[str] = ["*"]
    allow_credentials: bool = True

    class Config:
        env_prefix = "CORS_"


class DatabaseSettings(BaseSettings):
    """Database configuration"""
    url: str = "postgresql+asyncpg://auth:password@localhost:5432/auth"
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    
    class Config:
        env_prefix = "DATABASE_"


class Settings(BaseSettings):
    """Main settings class"""
    
    # Service settings
    service_name: str = "enterprise-auth-service"
    service_version: str = "2.2.0"
    debug: bool = False
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 1
    
    # Security settings
    secret_key: SecretStr = SecretStr("change-this-secret-key-in-production")
    
    # LDAP settings
    ldap_server_uri: str = "ldaps://ldap.company.com:636"
    ldap_bind_dn: str = "CN=service-account,OU=Service Accounts,DC=company,DC=com"
    ldap_bind_password: SecretStr = SecretStr("service-password")
    ldap_user_search_base: str = "OU=Users,DC=company,DC=com"
    ldap_group_search_base: str = "OU=Groups,DC=company,DC=com"
    ldap_use_tls: bool = True
    ldap_timeout: int = 30
    
    # SAML settings
    saml_sp_entity_id: str = "urn:alloy:auth-service"
    saml_sp_acs_url: str = "https://auth.company.com/auth/saml/acs"
    saml_sp_sls_url: str = "https://auth.company.com/auth/saml/sls"
    saml_idp_entity_id: str = "urn:company:idp"
    saml_idp_sso_url: str = "https://idp.company.com/saml/sso"
    saml_idp_sls_url: str = "https://idp.company.com/saml/sls"
    saml_idp_x509_cert: str = ""
    saml_sp_x509_cert: str = ""
    saml_sp_private_key: SecretStr = SecretStr("")
    
    # JWT settings
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7
    jwt_audience: str = "alloy-observability"
    jwt_issuer: str = "alloy-auth-service"
    
    # Redis settings
    redis_url: str = "redis://localhost:6379"
    
    # Database settings
    database_url: str = "postgresql+asyncpg://auth:password@localhost:5432/auth"
    
    # Audit settings
    audit_database_url: str = "postgresql+asyncpg://auth:password@localhost:5432/auth_audit"
    audit_retention_days: int = 90
    audit_log_file: str = "/var/log/auth-audit.log"
    
    # Kubernetes settings
    kubernetes_namespace: str = "observability"
    kubernetes_service_account: str = "alloy-auth-service"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    @validator('secret_key')
    def validate_secret_key(cls, v):
        if isinstance(v, SecretStr):
            if v.get_secret_value() == "change-this-secret-key-in-production":
                raise ValueError("Secret key must be changed in production")
        return v
    
    @property
    def ldap(self) -> LDAPConfig:
        """LDAP configuration"""
        return LDAPConfig(
            server_uri=self.ldap_server_uri,
            bind_dn=self.ldap_bind_dn,
            bind_password=self.ldap_bind_password.get_secret_value(),
            user_search_base=self.ldap_user_search_base,
            group_search_base=self.ldap_group_search_base,
            use_tls=self.ldap_use_tls,
            timeout=self.ldap_timeout
        )
    
    @property
    def saml(self) -> SAMLConfig:
        """SAML configuration"""
        return SAMLConfig(
            sp_entity_id=self.saml_sp_entity_id,
            sp_assertion_consumer_service_url=self.saml_sp_acs_url,
            sp_single_logout_service_url=self.saml_sp_sls_url,
            sp_x509_cert=self.saml_sp_x509_cert,
            sp_private_key=self.saml_sp_private_key.get_secret_value(),
            idp_entity_id=self.saml_idp_entity_id,
            idp_single_sign_on_service_url=self.saml_idp_sso_url,
            idp_single_logout_service_url=self.saml_idp_sls_url,
            idp_x509_cert=self.saml_idp_x509_cert
        )
    
    @property
    def jwt(self) -> JWTConfig:
        """JWT configuration"""
        return JWTConfig(
            secret_key=self.secret_key.get_secret_value(),
            algorithm=self.jwt_algorithm,
            access_token_expire_minutes=self.jwt_access_token_expire_minutes,
            refresh_token_expire_days=self.jwt_refresh_token_expire_days,
            audience=self.jwt_audience,
            issuer=self.jwt_issuer,
            redis_url=self.redis_url
        )
    
    @property
    def rbac(self) -> RBACConfig:
        """RBAC configuration"""
        return RBACConfig()
    
    @property
    def audit(self) -> AuditConfig:
        """Audit configuration"""
        return AuditConfig(
            database_url=self.audit_database_url,
            retention_days=self.audit_retention_days,
            log_file_path=self.audit_log_file
        )
    
    @property 
    def cors(self) -> CORSSettings:
        """CORS configuration"""
        return CORSSettings()
    
    @property
    def database(self) -> DatabaseSettings:
        """Database configuration"""
        return DatabaseSettings(url=self.database_url)