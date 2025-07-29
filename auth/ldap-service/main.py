#!/usr/bin/env python3
"""
Enterprise LDAP Authentication Service for Alloy Dynamic Processors

This service provides LDAP/SAML authentication and authorization for the observability platform,
integrating with enterprise identity providers and the multi-tenant framework.
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

import structlog
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from prometheus_client import Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
import uvicorn

from auth.ldap_client import LDAPClient
from auth.saml_client import SAMLClient
from auth.jwt_manager import JWTManager
from auth.rbac_engine import RBACEngine
from auth.audit_logger import AuditLogger
from auth.user_manager import UserManager
from config.settings import Settings


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

logger = structlog.get_logger()

# Prometheus metrics
auth_requests_total = Counter(
    'auth_requests_total',
    'Total authentication requests',
    ['method', 'provider', 'result']
)

auth_duration_seconds = Histogram(
    'auth_duration_seconds',
    'Authentication request duration',
    ['method', 'provider']
)

rbac_checks_total = Counter(
    'rbac_checks_total',
    'Total RBAC authorization checks',
    ['action', 'resource', 'result']
)

# Global instances
settings = Settings()
ldap_client: Optional[LDAPClient] = None
saml_client: Optional[SAMLClient] = None
jwt_manager: Optional[JWTManager] = None
rbac_engine: Optional[RBACEngine] = None
audit_logger: Optional[AuditLogger] = None
user_manager: Optional[UserManager] = None


# Request/Response models
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=255)
    tenant_id: Optional[str] = Field(None, max_length=255)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    display_name: str
    email: str
    groups: List[str]
    roles: List[str]
    tenant_access: List[str]


class SAMLRequest(BaseModel):
    saml_response: str
    relay_state: Optional[str] = None


class UserInfo(BaseModel):
    user_id: str
    display_name: str
    email: str
    groups: List[str]
    roles: List[str]
    tenant_access: List[str]
    last_login: Optional[str] = None


class AuthorizationRequest(BaseModel):
    action: str = Field(..., description="Action to authorize (read, write, admin)")
    resource: str = Field(..., description="Resource being accessed")
    tenant_id: Optional[str] = Field(None, description="Tenant context")


class AuthorizationResponse(BaseModel):
    authorized: bool
    reason: Optional[str] = None
    required_roles: List[str] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global ldap_client, saml_client, jwt_manager, rbac_engine, audit_logger, user_manager
    
    try:
        logger.info("Starting Enterprise Authentication Service")
        
        # Initialize components
        ldap_client = LDAPClient(settings.ldap)
        saml_client = SAMLClient(settings.saml)
        jwt_manager = JWTManager(settings.jwt)
        rbac_engine = RBACEngine(settings.rbac)
        audit_logger = AuditLogger(settings.audit)
        user_manager = UserManager(settings.database)
        
        # Test connections
        await ldap_client.test_connection()
        logger.info("LDAP connection established")
        
        await user_manager.initialize()
        logger.info("User management database initialized")
        
        logger.info("Enterprise Authentication Service started successfully")
        
        yield
        
    except Exception as e:
        logger.error("Failed to start authentication service", error=str(e))
        raise
    finally:
        logger.info("Shutting down Enterprise Authentication Service")
        if ldap_client:
            await ldap_client.close()
        if user_manager:
            await user_manager.close()


# Create FastAPI app
app = FastAPI(
    title="Enterprise Authentication Service",
    description="LDAP/SAML authentication and authorization for Alloy Dynamic Processors",
    version="2.2.0",
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

# Security
security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    """Validate JWT token and return user information"""
    try:
        token = credentials.credentials
        payload = jwt_manager.validate_token(token)
        
        # Log token validation for audit
        await audit_logger.log_event(
            event_type="token_validation",
            user_id=payload.get("user_id"),
            details={"result": "success"}
        )
        
        return payload
    except Exception as e:
        logger.warning("Token validation failed", error=str(e))
        await audit_logger.log_event(
            event_type="token_validation",
            details={"result": "failed", "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    health_status = {
        "status": "healthy",
        "service": "enterprise-auth",
        "version": "2.2.0",
        "components": {}
    }
    
    # Check LDAP connection
    try:
        await ldap_client.test_connection()
        health_status["components"]["ldap"] = "healthy"
    except Exception as e:
        health_status["components"]["ldap"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check database connection
    try:
        await user_manager.health_check()
        health_status["components"]["database"] = "healthy"
    except Exception as e:
        health_status["components"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    return health_status


# Metrics endpoint
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest()


# Authentication endpoints
@app.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Authenticate user via LDAP"""
    with auth_duration_seconds.labels(method="ldap", provider="ldap").time():
        try:
            logger.info("Processing LDAP login", username=request.username, tenant_id=request.tenant_id)
            
            # Authenticate with LDAP
            user_info = await ldap_client.authenticate(request.username, request.password)
            if not user_info:
                auth_requests_total.labels(method="ldap", provider="ldap", result="failed").inc()
                await audit_logger.log_event(
                    event_type="login_failed",
                    user_id=request.username,
                    details={"provider": "ldap", "reason": "invalid_credentials"}
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid credentials"
                )
            
            # Get user groups and roles
            groups = await ldap_client.get_user_groups(request.username)
            roles = await rbac_engine.map_groups_to_roles(groups)
            
            # Determine tenant access
            tenant_access = await rbac_engine.get_user_tenant_access(
                user_id=user_info["user_id"],
                roles=roles,
                requested_tenant=request.tenant_id
            )
            
            # Generate JWT token
            token_payload = {
                "user_id": user_info["user_id"],
                "display_name": user_info["display_name"],
                "email": user_info["email"],
                "groups": groups,
                "roles": roles,
                "tenant_access": tenant_access
            }
            
            access_token = jwt_manager.create_token(token_payload)
            
            # Update user last login
            await user_manager.update_last_login(user_info["user_id"])
            
            # Log successful authentication
            auth_requests_total.labels(method="ldap", provider="ldap", result="success").inc()
            await audit_logger.log_event(
                event_type="login_success",
                user_id=user_info["user_id"],
                details={
                    "provider": "ldap",
                    "groups": groups,
                    "roles": roles,
                    "tenant_access": tenant_access
                }
            )
            
            logger.info("LDAP login successful", user_id=user_info["user_id"], roles=roles)
            
            return LoginResponse(
                access_token=access_token,
                expires_in=settings.jwt.access_token_expire_minutes * 60,
                user_id=user_info["user_id"],
                display_name=user_info["display_name"],
                email=user_info["email"],
                groups=groups,
                roles=roles,
                tenant_access=tenant_access
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("LDAP login error", error=str(e), username=request.username)
            auth_requests_total.labels(method="ldap", provider="ldap", result="error").inc()
            await audit_logger.log_event(
                event_type="login_error",
                user_id=request.username,
                details={"provider": "ldap", "error": str(e)}
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service error"
            )


@app.post("/auth/saml", response_model=LoginResponse)
async def saml_login(request: SAMLRequest):
    """Authenticate user via SAML SSO"""
    with auth_duration_seconds.labels(method="saml", provider="saml").time():
        try:
            logger.info("Processing SAML login")
            
            # Validate SAML response
            user_info = await saml_client.validate_response(
                request.saml_response,
                request.relay_state
            )
            
            if not user_info:
                auth_requests_total.labels(method="saml", provider="saml", result="failed").inc()
                await audit_logger.log_event(
                    event_type="login_failed",
                    details={"provider": "saml", "reason": "invalid_saml_response"}
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid SAML response"
                )
            
            # Map SAML attributes to roles
            groups = user_info.get("groups", [])
            roles = await rbac_engine.map_groups_to_roles(groups)
            
            # Determine tenant access
            tenant_access = await rbac_engine.get_user_tenant_access(
                user_id=user_info["user_id"],
                roles=roles
            )
            
            # Generate JWT token
            token_payload = {
                "user_id": user_info["user_id"],
                "display_name": user_info["display_name"],
                "email": user_info["email"],
                "groups": groups,
                "roles": roles,
                "tenant_access": tenant_access
            }
            
            access_token = jwt_manager.create_token(token_payload)
            
            # Update user last login
            await user_manager.update_last_login(user_info["user_id"])
            
            # Log successful authentication
            auth_requests_total.labels(method="saml", provider="saml", result="success").inc()
            await audit_logger.log_event(
                event_type="login_success",
                user_id=user_info["user_id"],
                details={
                    "provider": "saml",
                    "groups": groups,
                    "roles": roles,
                    "tenant_access": tenant_access
                }
            )
            
            logger.info("SAML login successful", user_id=user_info["user_id"], roles=roles)
            
            return LoginResponse(
                access_token=access_token,
                expires_in=settings.jwt.access_token_expire_minutes * 60,
                user_id=user_info["user_id"],
                display_name=user_info["display_name"],
                email=user_info["email"],
                groups=groups,
                roles=roles,
                tenant_access=tenant_access
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("SAML login error", error=str(e))
            auth_requests_total.labels(method="saml", provider="saml", result="error").inc()
            await audit_logger.log_event(
                event_type="login_error",
                details={"provider": "saml", "error": str(e)}
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service error"
            )


# User information endpoints
@app.get("/auth/user", response_model=UserInfo)
async def get_user_info(current_user: Dict = Depends(get_current_user)):
    """Get current user information"""
    try:
        # Get additional user details from database
        user_details = await user_manager.get_user(current_user["user_id"])
        
        return UserInfo(
            user_id=current_user["user_id"],
            display_name=current_user["display_name"],
            email=current_user["email"],
            groups=current_user["groups"],
            roles=current_user["roles"],
            tenant_access=current_user["tenant_access"],
            last_login=user_details.get("last_login") if user_details else None
        )
        
    except Exception as e:
        logger.error("Error getting user info", error=str(e), user_id=current_user["user_id"])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving user information"
        )


@app.post("/auth/authorize", response_model=AuthorizationResponse)
async def authorize(
    request: AuthorizationRequest,
    current_user: Dict = Depends(get_current_user)
):
    """Check if user is authorized for specific action"""
    try:
        logger.debug(
            "Authorization check",
            user_id=current_user["user_id"],
            action=request.action,
            resource=request.resource,
            tenant_id=request.tenant_id
        )
        
        # Perform RBAC check
        authorized, reason, required_roles = await rbac_engine.check_authorization(
            user_id=current_user["user_id"],
            user_roles=current_user["roles"],
            action=request.action,
            resource=request.resource,
            tenant_id=request.tenant_id,
            tenant_access=current_user["tenant_access"]
        )
        
        # Log authorization decision
        rbac_checks_total.labels(
            action=request.action,
            resource=request.resource,
            result="allowed" if authorized else "denied"
        ).inc()
        
        await audit_logger.log_event(
            event_type="authorization_check",
            user_id=current_user["user_id"],
            details={
                "action": request.action,
                "resource": request.resource,
                "tenant_id": request.tenant_id,
                "result": "allowed" if authorized else "denied",
                "reason": reason
            }
        )
        
        return AuthorizationResponse(
            authorized=authorized,
            reason=reason,
            required_roles=required_roles
        )
        
    except Exception as e:
        logger.error("Authorization error", error=str(e), user_id=current_user["user_id"])
        rbac_checks_total.labels(
            action=request.action,
            resource=request.resource,
            result="error"
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authorization service error"
        )


@app.post("/auth/logout")
async def logout(current_user: Dict = Depends(get_current_user)):
    """Logout user and invalidate token"""
    try:
        # Add token to blacklist
        await jwt_manager.blacklist_token(current_user.get("jti"))
        
        # Log logout event
        await audit_logger.log_event(
            event_type="logout",
            user_id=current_user["user_id"],
            details={"result": "success"}
        )
        
        logger.info("User logged out", user_id=current_user["user_id"])
        
        return {"message": "Successfully logged out"}
        
    except Exception as e:
        logger.error("Logout error", error=str(e), user_id=current_user["user_id"])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout service error"
        )


# Admin endpoints
@app.get("/admin/users")
async def list_users(
    limit: int = 100,
    offset: int = 0,
    current_user: Dict = Depends(get_current_user)
):
    """List users (admin only)"""
    # Check admin permissions
    authorized, _, _ = await rbac_engine.check_authorization(
        user_id=current_user["user_id"],
        user_roles=current_user["roles"],
        action="admin",
        resource="users"
    )
    
    if not authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    
    try:
        users = await user_manager.list_users(limit=limit, offset=offset)
        return {"users": users, "total": len(users)}
        
    except Exception as e:
        logger.error("Error listing users", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving users"
        )


if __name__ == "__main__":
    # Run the application
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        log_config=None,  # Use structlog configuration
        access_log=False  # Disable uvicorn access logs
    )