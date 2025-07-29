"""
JWT Token Manager for Enterprise Authentication

Provides secure JWT token generation, validation, and management with support for
token blacklisting, refresh tokens, and comprehensive security features.
"""

import jwt
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass
import structlog
import secrets
import hashlib
import redis.asyncio as redis
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

logger = structlog.get_logger(__name__)


@dataclass
class JWTConfig:
    """JWT configuration settings"""
    # Token settings
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    
    # Security settings
    audience: str = "alloy-observability"
    issuer: str = "alloy-auth-service"
    require_iat: bool = True
    require_exp: bool = True
    require_nbf: bool = True
    
    # Redis settings for token blacklist
    redis_url: str = "redis://localhost:6379"
    redis_key_prefix: str = "auth:blacklist:"
    
    # RSA keys for asymmetric signing (optional)
    private_key: Optional[str] = None
    public_key: Optional[str] = None


class TokenBlacklist:
    """Token blacklist using Redis for distributed token revocation"""
    
    def __init__(self, redis_url: str, key_prefix: str):
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self._redis: Optional[redis.Redis] = None
    
    async def connect(self):
        """Connect to Redis"""
        try:
            self._redis = redis.from_url(self.redis_url)
            await self._redis.ping()
            logger.info("Connected to Redis for token blacklist")
        except Exception as e:
            logger.error("Failed to connect to Redis", error=str(e))
            raise
    
    async def disconnect(self):
        """Disconnect from Redis"""
        if self._redis:
            await self._redis.close()
    
    async def add_token(self, jti: str, expires_at: datetime):
        """Add token to blacklist"""
        try:
            if not self._redis:
                await self.connect()
            
            # Calculate TTL based on token expiration
            ttl_seconds = int((expires_at - datetime.utcnow()).total_seconds())
            if ttl_seconds > 0:
                await self._redis.setex(
                    f"{self.key_prefix}{jti}",
                    ttl_seconds,
                    "blacklisted"
                )
                logger.debug("Token added to blacklist", jti=jti, ttl=ttl_seconds)
        except Exception as e:
            logger.error("Error adding token to blacklist", jti=jti, error=str(e))
    
    async def is_blacklisted(self, jti: str) -> bool:
        """Check if token is blacklisted"""
        try:
            if not self._redis:
                await self.connect()
            
            result = await self._redis.exists(f"{self.key_prefix}{jti}")
            return bool(result)
        except Exception as e:
            logger.error("Error checking token blacklist", jti=jti, error=str(e))
            return False  # Fail open for availability
    
    async def cleanup_expired(self):
        """Cleanup expired blacklist entries (Redis handles this automatically with TTL)"""
        # Redis automatically removes expired keys, but we can scan for cleanup
        try:
            if not self._redis:
                await self.connect()
            
            # Scan for blacklist keys and get count
            cursor = 0
            count = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor=cursor,
                    match=f"{self.key_prefix}*",
                    count=100
                )
                count += len(keys)
                if cursor == 0:
                    break
            
            logger.debug("Blacklist cleanup check", active_entries=count)
        except Exception as e:
            logger.error("Error during blacklist cleanup", error=str(e))


class JWTManager:
    """JWT token manager with comprehensive security features"""
    
    def __init__(self, config: JWTConfig):
        self.config = config
        self.blacklist = TokenBlacklist(config.redis_url, config.redis_key_prefix)
        self._private_key = None
        self._public_key = None
        self._initialize_keys()
    
    def _initialize_keys(self):
        """Initialize cryptographic keys"""
        if self.config.algorithm in ["RS256", "RS384", "RS512"]:
            if self.config.private_key and self.config.public_key:
                # Load provided keys
                self._private_key = self.config.private_key
                self._public_key = self.config.public_key
            else:
                # Generate new RSA key pair
                private_key = rsa.generate_private_key(
                    public_exponent=65537,
                    key_size=2048
                )
                
                self._private_key = private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ).decode('utf-8')
                
                self._public_key = private_key.public_key().public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                ).decode('utf-8')
                
                logger.info("Generated new RSA key pair for JWT signing")
    
    def create_token(self, payload: Dict[str, Any], token_type: str = "access") -> str:
        """Create JWT token with standard claims"""
        try:
            now = datetime.utcnow()
            
            # Standard JWT claims
            claims = {
                "iss": self.config.issuer,
                "aud": self.config.audience,
                "iat": now,
                "nbf": now,
                "jti": self._generate_jti()
            }
            
            # Set expiration based on token type
            if token_type == "access":
                claims["exp"] = now + timedelta(minutes=self.config.access_token_expire_minutes)
                claims["token_type"] = "access"
            else:  # refresh token
                claims["exp"] = now + timedelta(days=self.config.refresh_token_expire_days)
                claims["token_type"] = "refresh"
            
            # Add custom payload
            claims.update(payload)
            
            # Choose signing key based on algorithm
            if self.config.algorithm in ["RS256", "RS384", "RS512"]:
                signing_key = self._private_key
            else:
                signing_key = self.config.secret_key
            
            # Create token
            token = jwt.encode(
                claims,
                signing_key,
                algorithm=self.config.algorithm
            )
            
            logger.debug("JWT token created", 
                        user_id=payload.get("user_id"), 
                        token_type=token_type,
                        expires_at=claims["exp"].isoformat())
            
            return token
            
        except Exception as e:
            logger.error("Error creating JWT token", error=str(e))
            raise
    
    def validate_token(self, token: str) -> Dict[str, Any]:
        """Validate JWT token and return payload"""
        try:
            # Choose verification key based on algorithm
            if self.config.algorithm in ["RS256", "RS384", "RS512"]:
                verification_key = self._public_key
            else:
                verification_key = self.config.secret_key
            
            # Decode and validate token
            payload = jwt.decode(
                token,
                verification_key,
                algorithms=[self.config.algorithm],
                audience=self.config.audience,
                issuer=self.config.issuer,
                options={
                    "require_iat": self.config.require_iat,
                    "require_exp": self.config.require_exp,
                    "require_nbf": self.config.require_nbf
                }
            )
            
            # Check if token is blacklisted
            jti = payload.get("jti")
            if jti and asyncio.run(self.blacklist.is_blacklisted(jti)):
                logger.warning("Attempted use of blacklisted token", jti=jti)
                raise jwt.InvalidTokenError("Token has been revoked")
            
            logger.debug("JWT token validated successfully", 
                        user_id=payload.get("user_id"),
                        token_type=payload.get("token_type"),
                        expires_at=datetime.fromtimestamp(payload["exp"]).isoformat())
            
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token expired", token=token[:20] + "...")
            raise
        except jwt.InvalidTokenError as e:
            logger.warning("Invalid JWT token", error=str(e), token=token[:20] + "...")
            raise
        except Exception as e:
            logger.error("Error validating JWT token", error=str(e))
            raise
    
    async def blacklist_token(self, jti: str, expires_at: Optional[datetime] = None):
        """Add token to blacklist"""
        try:
            if not expires_at:
                expires_at = datetime.utcnow() + timedelta(days=self.config.refresh_token_expire_days)
            
            await self.blacklist.add_token(jti, expires_at)
            logger.info("Token blacklisted", jti=jti)
            
        except Exception as e:
            logger.error("Error blacklisting token", jti=jti, error=str(e))
    
    def create_refresh_token(self, user_id: str, access_token_jti: str) -> str:
        """Create refresh token linked to access token"""
        payload = {
            "user_id": user_id,
            "access_token_jti": access_token_jti,
            "scope": "refresh"
        }
        
        return self.create_token(payload, token_type="refresh")
    
    async def refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, str]]:
        """Generate new access token from refresh token"""
        try:
            # Validate refresh token
            refresh_payload = self.validate_token(refresh_token)
            
            if refresh_payload.get("token_type") != "refresh":
                raise jwt.InvalidTokenError("Invalid token type for refresh")
            
            user_id = refresh_payload.get("user_id")
            if not user_id:
                raise jwt.InvalidTokenError("Missing user_id in refresh token")
            
            # Blacklist old access token if provided
            old_access_token_jti = refresh_payload.get("access_token_jti")
            if old_access_token_jti:
                await self.blacklist_token(old_access_token_jti)
            
            # Create new access token
            # Note: In production, you'd typically fetch fresh user data here
            new_access_payload = {
                "user_id": user_id,
                "display_name": refresh_payload.get("display_name", ""),
                "email": refresh_payload.get("email", ""),
                "roles": refresh_payload.get("roles", []),
                "tenant_access": refresh_payload.get("tenant_access", [])
            }
            
            new_access_token = self.create_token(new_access_payload, token_type="access")
            
            # Extract JTI from new access token for linking
            new_payload = jwt.decode(
                new_access_token,
                self._public_key if self.config.algorithm.startswith("RS") else self.config.secret_key,
                algorithms=[self.config.algorithm],
                options={"verify_signature": False}
            )
            
            # Create new refresh token linked to new access token
            new_refresh_token = self.create_refresh_token(user_id, new_payload["jti"])
            
            # Blacklist old refresh token
            refresh_jti = refresh_payload.get("jti")
            if refresh_jti:
                await self.blacklist_token(refresh_jti, datetime.fromtimestamp(refresh_payload["exp"]))
            
            logger.info("Access token refreshed", user_id=user_id)
            
            return {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "token_type": "bearer",
                "expires_in": self.config.access_token_expire_minutes * 60
            }
            
        except Exception as e:
            logger.error("Error refreshing access token", error=str(e))
            return None
    
    def _generate_jti(self) -> str:
        """Generate unique JWT ID"""
        # Create unique identifier using timestamp and random bytes
        timestamp = str(int(datetime.utcnow().timestamp()))
        random_bytes = secrets.token_bytes(16)
        
        # Create hash for consistent length
        jti_data = timestamp.encode() + random_bytes
        jti = hashlib.sha256(jti_data).hexdigest()[:32]
        
        return jti
    
    def decode_token_unsafe(self, token: str) -> Dict[str, Any]:
        """Decode token without validation (for debugging/logging)"""
        try:
            return jwt.decode(token, options={"verify_signature": False})
        except Exception:
            return {}
    
    def get_token_info(self, token: str) -> Dict[str, Any]:
        """Get token information without full validation"""
        try:
            payload = self.decode_token_unsafe(token)
            
            return {
                "user_id": payload.get("user_id"),
                "token_type": payload.get("token_type"),
                "issued_at": datetime.fromtimestamp(payload["iat"]).isoformat() if "iat" in payload else None,
                "expires_at": datetime.fromtimestamp(payload["exp"]).isoformat() if "exp" in payload else None,
                "issuer": payload.get("iss"),
                "audience": payload.get("aud"),
                "jti": payload.get("jti")
            }
        except Exception as e:
            logger.error("Error getting token info", error=str(e))
            return {}
    
    async def cleanup_blacklist(self):
        """Cleanup expired blacklist entries"""
        await self.blacklist.cleanup_expired()
    
    async def close(self):
        """Close JWT manager and cleanup resources"""
        await self.blacklist.disconnect()
        logger.info("JWT manager closed")
    
    def get_public_key(self) -> Optional[str]:
        """Get public key for token verification (for other services)"""
        return self._public_key if self.config.algorithm.startswith("RS") else None