"""
Comprehensive Audit Logger for Enterprise Authentication

Provides detailed audit logging for all authentication and authorization events
with structured logging, compliance support, and security monitoring.
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import structlog
import asyncio
from sqlalchemy import Column, String, DateTime, Text, Integer, Boolean, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

logger = structlog.get_logger(__name__)

Base = declarative_base()


class EventType(Enum):
    """Audit event types"""
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGIN_ERROR = "login_error"
    LOGOUT = "logout"
    TOKEN_VALIDATION = "token_validation"
    AUTHORIZATION_CHECK = "authorization_check"
    ROLE_CHANGE = "role_change"
    CONFIG_CHANGE = "config_change"
    SECURITY_VIOLATION = "security_violation"


@dataclass
class AuditConfig:
    """Audit configuration settings"""
    database_url: str = "postgresql+asyncpg://auth:password@localhost:5432/auth_audit"
    log_to_file: bool = True
    log_file_path: str = "/var/log/auth-audit.log"
    retention_days: int = 90
    enable_compliance_logging: bool = True
    sensitive_fields: list = None
    
    def __post_init__(self):
        if self.sensitive_fields is None:
            self.sensitive_fields = ["password", "token", "secret", "key"]


class AuditEvent(Base):
    """Audit event database model"""
    __tablename__ = "audit_events"
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    event_type = Column(String(50), nullable=False)
    user_id = Column(String(255), nullable=True)
    session_id = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    tenant_id = Column(String(255), nullable=True)
    resource = Column(String(255), nullable=True)
    action = Column(String(100), nullable=True)
    result = Column(String(50), nullable=True)
    details = Column(Text, nullable=True)
    risk_score = Column(Integer, default=0)
    compliance_relevant = Column(Boolean, default=False)
    
    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_audit_timestamp', 'timestamp'),
        Index('idx_audit_user_id', 'user_id'),
        Index('idx_audit_event_type', 'event_type'),
        Index('idx_audit_compliance', 'compliance_relevant'),
    )


class AuditLogger:
    """Advanced audit logger with database persistence and compliance features"""
    
    def __init__(self, config: AuditConfig):
        self.config = config
        self.engine = None
        self.session_factory = None
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize database connection and session factory"""
        try:
            self.engine = create_async_engine(
                self.config.database_url,
                echo=False,
                future=True
            )
            
            self.session_factory = sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            logger.info("Audit database initialized", database_url=self.config.database_url)
            
        except Exception as e:
            logger.error("Failed to initialize audit database", error=str(e))
            raise
    
    async def create_tables(self):
        """Create audit tables if they don't exist"""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Audit tables created/verified")
        except Exception as e:
            logger.error("Error creating audit tables", error=str(e))
            raise
    
    async def log_event(
        self,
        event_type: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        tenant_id: Optional[str] = None,
        resource: Optional[str] = None,
        action: Optional[str] = None,
        result: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        risk_score: int = 0
    ):
        """Log audit event to database and structured logs"""
        try:
            # Sanitize sensitive data
            sanitized_details = self._sanitize_details(details or {})
            
            # Determine compliance relevance
            compliance_relevant = self._is_compliance_relevant(event_type, details)
            
            # Create audit event
            audit_event = AuditEvent(
                event_type=event_type,
                user_id=user_id,
                session_id=session_id,
                ip_address=ip_address,
                user_agent=user_agent,
                tenant_id=tenant_id,
                resource=resource,
                action=action,
                result=result,
                details=json.dumps(sanitized_details) if sanitized_details else None,
                risk_score=risk_score,
                compliance_relevant=compliance_relevant
            )
            
            # Save to database
            async with self.session_factory() as session:
                session.add(audit_event)
                await session.commit()
            
            # Log to structured logger
            logger.info(
                "Audit event recorded",
                event_type=event_type,
                user_id=user_id,
                session_id=session_id,
                ip_address=ip_address,
                tenant_id=tenant_id,
                resource=resource,
                action=action,
                result=result,
                risk_score=risk_score,
                compliance_relevant=compliance_relevant,
                details=sanitized_details
            )
            
            # Check for security violations
            if risk_score >= 80:
                await self._handle_security_violation(audit_event)
                
        except Exception as e:
            logger.error("Error logging audit event", 
                        event_type=event_type, 
                        user_id=user_id, 
                        error=str(e))
    
    def _sanitize_details(self, details: Dict[str, Any]) -> Dict[str, Any]:
        """Remove or mask sensitive information from details"""
        sanitized = {}
        
        for key, value in details.items():
            if any(sensitive in key.lower() for sensitive in self.config.sensitive_fields):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_details(value)
            elif isinstance(value, str) and len(value) > 100:
                # Truncate very long strings
                sanitized[key] = value[:100] + "..."
            else:
                sanitized[key] = value
        
        return sanitized
    
    def _is_compliance_relevant(self, event_type: str, details: Optional[Dict[str, Any]]) -> bool:
        """Determine if event is relevant for compliance reporting"""
        if not self.config.enable_compliance_logging:
            return False
        
        # Define compliance-relevant events
        compliance_events = {
            EventType.LOGIN_SUCCESS.value,
            EventType.LOGIN_FAILED.value,
            EventType.AUTHORIZATION_CHECK.value,
            EventType.ROLE_CHANGE.value,
            EventType.CONFIG_CHANGE.value,
            EventType.SECURITY_VIOLATION.value
        }
        
        return event_type in compliance_events
    
    async def _handle_security_violation(self, audit_event: AuditEvent):
        """Handle high-risk security violations"""
        try:
            # Log security alert
            logger.critical(
                "Security violation detected",
                event_id=audit_event.id,
                event_type=audit_event.event_type,
                user_id=audit_event.user_id,
                ip_address=audit_event.ip_address,
                risk_score=audit_event.risk_score
            )
            
            # Here you would typically:
            # 1. Send alert to security team
            # 2. Trigger automated response (account lockout, etc.)
            # 3. Create incident ticket
            
        except Exception as e:
            logger.error("Error handling security violation", error=str(e))
    
    async def get_user_activity(self, user_id: str, days: int = 30) -> list:
        """Get user activity for audit purposes"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            async with self.session_factory() as session:
                result = await session.execute(
                    select(AuditEvent)
                    .where(AuditEvent.user_id == user_id)
                    .where(AuditEvent.timestamp >= cutoff_date)
                    .order_by(AuditEvent.timestamp.desc())
                )
                
                events = result.scalars().all()
                return [self._event_to_dict(event) for event in events]
                
        except Exception as e:
            logger.error("Error retrieving user activity", user_id=user_id, error=str(e))
            return []
    
    async def get_compliance_report(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Generate compliance report for specified date range"""
        try:
            async with self.session_factory() as session:
                # Get compliance-relevant events
                result = await session.execute(
                    select(AuditEvent)
                    .where(AuditEvent.compliance_relevant == True)
                    .where(AuditEvent.timestamp >= start_date)
                    .where(AuditEvent.timestamp <= end_date)
                    .order_by(AuditEvent.timestamp.desc())
                )
                
                events = result.scalars().all()
                
                # Generate report statistics
                report = {
                    "period": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat()
                    },
                    "total_events": len(events),
                    "event_types": {},
                    "users": set(),
                    "security_violations": 0,
                    "failed_logins": 0,
                    "successful_logins": 0,
                    "events": [self._event_to_dict(event) for event in events]
                }
                
                # Calculate statistics
                for event in events:
                    # Event type counts
                    event_type = event.event_type
                    report["event_types"][event_type] = report["event_types"].get(event_type, 0) + 1
                    
                    # User tracking
                    if event.user_id:
                        report["users"].add(event.user_id)
                    
                    # Security metrics
                    if event.risk_score >= 80:
                        report["security_violations"] += 1
                    
                    if event.event_type == EventType.LOGIN_FAILED.value:
                        report["failed_logins"] += 1
                    elif event.event_type == EventType.LOGIN_SUCCESS.value:
                        report["successful_logins"] += 1
                
                report["unique_users"] = len(report["users"])
                report["users"] = list(report["users"])  # Convert set to list for JSON serialization
                
                logger.info("Compliance report generated", 
                           period=f"{start_date} to {end_date}",
                           total_events=report["total_events"])
                
                return report
                
        except Exception as e:
            logger.error("Error generating compliance report", error=str(e))
            return {}
    
    def _event_to_dict(self, event: AuditEvent) -> Dict[str, Any]:
        """Convert audit event to dictionary"""
        return {
            "id": event.id,
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type,
            "user_id": event.user_id,
            "session_id": event.session_id,
            "ip_address": event.ip_address,
            "user_agent": event.user_agent,
            "tenant_id": event.tenant_id,
            "resource": event.resource,
            "action": event.action,
            "result": event.result,
            "details": json.loads(event.details) if event.details else None,
            "risk_score": event.risk_score,
            "compliance_relevant": event.compliance_relevant
        }
    
    async def cleanup_old_events(self):
        """Cleanup old audit events based on retention policy"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=self.config.retention_days)
            
            async with self.session_factory() as session:
                result = await session.execute(
                    delete(AuditEvent).where(AuditEvent.timestamp < cutoff_date)
                )
                
                deleted_count = result.rowcount
                await session.commit()
                
                logger.info("Audit events cleanup completed", 
                           deleted_count=deleted_count,
                           cutoff_date=cutoff_date.isoformat())
                
        except Exception as e:
            logger.error("Error during audit cleanup", error=str(e))
    
    async def close(self):
        """Close audit logger and cleanup resources"""
        if self.engine:
            await self.engine.dispose()
        logger.info("Audit logger closed")