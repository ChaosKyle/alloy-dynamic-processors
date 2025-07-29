"""
Enterprise RBAC Engine for Advanced Authorization

Provides role-based access control with support for hierarchical roles, resource-level 
permissions, tenant isolation, and policy-based authorization decisions.
"""

import asyncio
import json
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
import structlog
import re
from datetime import datetime, timedelta

logger = structlog.get_logger(__name__)


class Permission(Enum):
    """Standard permissions for observability platform"""
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    DELETE = "delete"
    CONFIG = "config"
    AUDIT = "audit"
    BILLING = "billing"


class ResourceType(Enum):
    """Resource types in the observability platform"""
    METRICS = "metrics"
    LOGS = "logs"
    TRACES = "traces"
    DASHBOARDS = "dashboards"
    ALERTS = "alerts"
    USERS = "users"
    TENANTS = "tenants"
    CONFIGS = "configs"
    BILLING = "billing"
    SYSTEM = "system"


@dataclass
class Role:
    """Enterprise role definition"""
    name: str
    description: str
    permissions: Dict[ResourceType, Set[Permission]]
    tenant_scope: Optional[str] = None  # None means global, specific tenant_id for tenant-scoped
    inherits_from: List[str] = field(default_factory=list)
    conditions: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # Higher priority overrides lower priority roles


@dataclass 
class PolicyRule:
    """Policy rule for fine-grained access control"""
    name: str
    effect: str  # "allow" or "deny"
    actions: List[str]
    resources: List[str]
    conditions: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0


@dataclass
class RBACConfig:
    """RBAC configuration settings"""
    roles: Dict[str, Role] = field(default_factory=dict)
    group_role_mapping: Dict[str, List[str]] = field(default_factory=dict)
    policies: List[PolicyRule] = field(default_factory=list)
    default_tenant_access: bool = False
    inheritance_enabled: bool = True
    policy_evaluation_order: str = "deny-overrides"  # "deny-overrides" or "allow-overrides"


class RBACEngine:
    """Advanced RBAC engine for enterprise authorization"""
    
    def __init__(self, config: RBACConfig):
        self.config = config
        self._role_cache: Dict[str, Role] = {}
        self._inheritance_cache: Dict[str, Set[str]] = {}
        self._policy_cache: Dict[str, List[PolicyRule]] = {}
        self._initialize_default_roles()
    
    def _initialize_default_roles(self):
        """Initialize default enterprise roles"""
        default_roles = {
            # System Administrator - Full access
            "system_admin": Role(
                name="system_admin",
                description="System Administrator with full platform access",
                permissions={
                    ResourceType.METRICS: {Permission.READ, Permission.WRITE, Permission.ADMIN, Permission.DELETE},
                    ResourceType.LOGS: {Permission.READ, Permission.WRITE, Permission.ADMIN, Permission.DELETE},
                    ResourceType.TRACES: {Permission.READ, Permission.WRITE, Permission.ADMIN, Permission.DELETE},
                    ResourceType.DASHBOARDS: {Permission.READ, Permission.WRITE, Permission.ADMIN, Permission.DELETE},
                    ResourceType.ALERTS: {Permission.READ, Permission.WRITE, Permission.ADMIN, Permission.DELETE},
                    ResourceType.USERS: {Permission.READ, Permission.WRITE, Permission.ADMIN, Permission.DELETE},
                    ResourceType.TENANTS: {Permission.READ, Permission.WRITE, Permission.ADMIN, Permission.DELETE},
                    ResourceType.CONFIGS: {Permission.READ, Permission.WRITE, Permission.ADMIN, Permission.CONFIG},
                    ResourceType.BILLING: {Permission.READ, Permission.WRITE, Permission.ADMIN, Permission.BILLING},
                    ResourceType.SYSTEM: {Permission.READ, Permission.WRITE, Permission.ADMIN, Permission.AUDIT}
                },
                priority=1000
            ),
            
            # Tenant Administrator - Full access within tenant
            "tenant_admin": Role(
                name="tenant_admin",
                description="Tenant Administrator with full access to tenant resources",
                permissions={
                    ResourceType.METRICS: {Permission.READ, Permission.WRITE, Permission.ADMIN},
                    ResourceType.LOGS: {Permission.READ, Permission.WRITE, Permission.ADMIN},
                    ResourceType.TRACES: {Permission.READ, Permission.WRITE, Permission.ADMIN},
                    ResourceType.DASHBOARDS: {Permission.READ, Permission.WRITE, Permission.ADMIN, Permission.DELETE},
                    ResourceType.ALERTS: {Permission.READ, Permission.WRITE, Permission.ADMIN, Permission.DELETE},
                    ResourceType.USERS: {Permission.READ, Permission.WRITE},
                    ResourceType.CONFIGS: {Permission.READ, Permission.WRITE, Permission.CONFIG},
                    ResourceType.BILLING: {Permission.READ, Permission.BILLING}
                },
                priority=800
            ),
            
            # Site Reliability Engineer - Operational access
            "sre": Role(
                name="sre",
                description="Site Reliability Engineer with operational access",
                permissions={
                    ResourceType.METRICS: {Permission.READ, Permission.WRITE},
                    ResourceType.LOGS: {Permission.READ, Permission.WRITE},
                    ResourceType.TRACES: {Permission.READ, Permission.WRITE},
                    ResourceType.DASHBOARDS: {Permission.READ, Permission.WRITE, Permission.DELETE},
                    ResourceType.ALERTS: {Permission.READ, Permission.WRITE, Permission.ADMIN, Permission.DELETE},
                    ResourceType.CONFIGS: {Permission.READ, Permission.CONFIG},
                    ResourceType.BILLING: {Permission.READ}
                },
                priority=600
            ),
            
            # Developer - Development and debugging access
            "developer": Role(
                name="developer",
                description="Developer with access to development and debugging features",
                permissions={
                    ResourceType.METRICS: {Permission.READ, Permission.WRITE},
                    ResourceType.LOGS: {Permission.READ, Permission.WRITE},
                    ResourceType.TRACES: {Permission.READ, Permission.WRITE},
                    ResourceType.DASHBOARDS: {Permission.READ, Permission.WRITE},
                    ResourceType.ALERTS: {Permission.READ}
                },
                priority=400
            ),
            
            # Security Auditor - Read-only with audit access
            "security_auditor": Role(
                name="security_auditor",
                description="Security Auditor with read-only access and audit capabilities",
                permissions={
                    ResourceType.METRICS: {Permission.READ, Permission.AUDIT},
                    ResourceType.LOGS: {Permission.READ, Permission.AUDIT},
                    ResourceType.TRACES: {Permission.READ, Permission.AUDIT},
                    ResourceType.DASHBOARDS: {Permission.READ},
                    ResourceType.ALERTS: {Permission.READ},
                    ResourceType.USERS: {Permission.READ, Permission.AUDIT},
                    ResourceType.TENANTS: {Permission.READ, Permission.AUDIT},
                    ResourceType.CONFIGS: {Permission.READ, Permission.AUDIT},
                    ResourceType.SYSTEM: {Permission.READ, Permission.AUDIT}
                },
                priority=500
            ),
            
            # Finance Analyst - Billing and cost access
            "finance_analyst": Role(
                name="finance_analyst",
                description="Finance Analyst with access to billing and cost information",
                permissions={
                    ResourceType.BILLING: {Permission.READ, Permission.BILLING},
                    ResourceType.TENANTS: {Permission.READ},
                    ResourceType.USERS: {Permission.READ}
                },
                priority=300
            ),
            
            # Viewer - Read-only access
            "viewer": Role(
                name="viewer",
                description="Read-only access to observability data",
                permissions={
                    ResourceType.METRICS: {Permission.READ},
                    ResourceType.LOGS: {Permission.READ},
                    ResourceType.TRACES: {Permission.READ},
                    ResourceType.DASHBOARDS: {Permission.READ},
                    ResourceType.ALERTS: {Permission.READ}
                },
                priority=100
            )
        }
        
        # Add default roles to config
        for role_name, role in default_roles.items():
            self.config.roles[role_name] = role
        
        # Default group mappings (can be overridden)
        default_group_mappings = {
            "Domain Admins": ["system_admin"],
            "Observability Admins": ["tenant_admin"],
            "SRE Team": ["sre"],
            "Engineering": ["developer"],
            "Security Team": ["security_auditor"],
            "Finance Team": ["finance_analyst"],
            "All Users": ["viewer"]
        }
        
        for group, roles in default_group_mappings.items():
            if group not in self.config.group_role_mapping:
                self.config.group_role_mapping[group] = roles
    
    async def map_groups_to_roles(self, groups: List[str]) -> List[str]:
        """Map LDAP/SAML groups to platform roles"""
        try:
            mapped_roles = set()
            
            for group in groups:
                if group in self.config.group_role_mapping:
                    for role in self.config.group_role_mapping[group]:
                        mapped_roles.add(role)
                        logger.debug("Mapped group to role", group=group, role=role)
            
            # If no roles mapped and inheritance enabled, try pattern matching
            if not mapped_roles and self.config.inheritance_enabled:
                mapped_roles.update(await self._pattern_match_groups(groups))
            
            # Always include viewer role as minimum
            if not mapped_roles:
                mapped_roles.add("viewer")
                logger.info("No roles mapped, assigning default viewer role", groups=groups)
            
            # Resolve role inheritance
            final_roles = await self._resolve_inheritance(list(mapped_roles))
            
            logger.info("Groups mapped to roles", groups=groups, roles=final_roles)
            return final_roles
            
        except Exception as e:
            logger.error("Error mapping groups to roles", groups=groups, error=str(e))
            return ["viewer"]  # Fallback to viewer role
    
    async def _pattern_match_groups(self, groups: List[str]) -> Set[str]:
        """Pattern match groups to roles when direct mapping doesn't exist"""
        matched_roles = set()
        
        # Define group patterns and their corresponding roles
        patterns = {
            r".*[Aa]dmin.*": ["tenant_admin"],
            r".*[Ss]RE.*": ["sre"],
            r".*[Dd]ev.*": ["developer"],
            r".*[Ss]ecurity.*": ["security_auditor"],
            r".*[Ff]inance.*": ["finance_analyst"],
            r".*[Aa]uditor.*": ["security_auditor"]
        }
        
        for group in groups:
            for pattern, roles in patterns.items():
                if re.match(pattern, group):
                    matched_roles.update(roles)
                    logger.debug("Pattern matched group to roles", group=group, pattern=pattern, roles=roles)
        
        return matched_roles
    
    async def _resolve_inheritance(self, roles: List[str]) -> List[str]:
        """Resolve role inheritance hierarchy"""
        try:
            if not self.config.inheritance_enabled:
                return roles
            
            resolved_roles = set(roles)
            
            for role_name in roles:
                if role_name in self.config.roles:
                    role = self.config.roles[role_name]
                    # Add inherited roles recursively
                    for inherited_role in role.inherits_from:
                        if inherited_role in self.config.roles:
                            resolved_roles.add(inherited_role)
                            # Recursively resolve inheritance
                            inherited_resolved = await self._resolve_inheritance([inherited_role])
                            resolved_roles.update(inherited_resolved)
            
            return list(resolved_roles)
            
        except Exception as e:
            logger.error("Error resolving role inheritance", roles=roles, error=str(e))
            return roles
    
    async def get_user_tenant_access(self, user_id: str, roles: List[str], 
                                   requested_tenant: Optional[str] = None) -> List[str]:
        """Determine tenant access for user based on roles"""
        try:
            accessible_tenants = set()
            
            for role_name in roles:
                if role_name in self.config.roles:
                    role = self.config.roles[role_name]
                    
                    # Global roles (system_admin, security_auditor) get access to all tenants
                    if role.tenant_scope is None and role_name in ["system_admin", "security_auditor"]:
                        accessible_tenants.add("*")  # Wildcard for all tenants
                    
                    # Tenant-specific roles
                    elif role.tenant_scope:
                        accessible_tenants.add(role.tenant_scope)
                    
                    # Finance roles get billing access to specific tenants
                    elif role_name == "finance_analyst":
                        # Finance can access billing for all tenants they're assigned to
                        # This would typically come from additional configuration
                        accessible_tenants.add("*")
            
            # If user has specific tenant request and permission, add it
            if requested_tenant and await self._check_tenant_permission(user_id, requested_tenant, roles):
                accessible_tenants.add(requested_tenant)
            
            # Convert wildcard to actual tenant list (in real implementation, 
            # this would query available tenants)
            if "*" in accessible_tenants:
                return ["*"]  # Return wildcard indicating all tenant access
            
            tenant_list = list(accessible_tenants)
            logger.debug("Determined tenant access", user_id=user_id, roles=roles, tenants=tenant_list)
            
            return tenant_list
            
        except Exception as e:
            logger.error("Error determining tenant access", user_id=user_id, error=str(e))
            return []
    
    async def _check_tenant_permission(self, user_id: str, tenant_id: str, roles: List[str]) -> bool:
        """Check if user has permission to access specific tenant"""
        # This would typically check tenant membership, role assignments, etc.
        # For now, return True for default access if user has appropriate roles
        return any(role in ["system_admin", "tenant_admin", "sre"] for role in roles)
    
    async def check_authorization(self, user_id: str, user_roles: List[str], action: str, 
                                resource: str, tenant_id: Optional[str] = None,
                                tenant_access: List[str] = None) -> Tuple[bool, Optional[str], List[str]]:
        """
        Check if user is authorized for specific action on resource
        Returns: (authorized: bool, reason: str, required_roles: List[str])
        """
        try:
            logger.debug("Authorization check", 
                        user_id=user_id, 
                        roles=user_roles, 
                        action=action, 
                        resource=resource, 
                        tenant_id=tenant_id)
            
            # First check tenant access if tenant_id specified
            if tenant_id and tenant_access:
                if not await self._check_tenant_access(tenant_id, tenant_access):
                    return False, f"No access to tenant {tenant_id}", []
            
            # Parse resource type and action
            resource_type, permission = await self._parse_action_resource(action, resource)
            if not resource_type or not permission:
                return False, f"Invalid action '{action}' or resource '{resource}'", []
            
            # Check role-based permissions
            authorized_roles = []
            for role_name in user_roles:
                if await self._check_role_permission(role_name, resource_type, permission, tenant_id):
                    authorized_roles.append(role_name)
            
            if authorized_roles:
                # Check policy rules
                policy_result = await self._evaluate_policies(user_id, user_roles, action, resource, tenant_id)
                if policy_result["effect"] == "deny":
                    return False, f"Denied by policy: {policy_result['policy']}", []
                
                logger.debug("Authorization granted", 
                           user_id=user_id, 
                           authorized_roles=authorized_roles)
                return True, None, authorized_roles
            
            # Determine required roles for this action/resource
            required_roles = await self._get_required_roles(resource_type, permission)
            
            return False, f"Insufficient permissions. Required roles: {required_roles}", required_roles
            
        except Exception as e:
            logger.error("Authorization check error", 
                        user_id=user_id, 
                        action=action, 
                        resource=resource, 
                        error=str(e))
            return False, "Authorization service error", []
    
    async def _check_tenant_access(self, tenant_id: str, tenant_access: List[str]) -> bool:
        """Check if user has access to specified tenant"""
        return "*" in tenant_access or tenant_id in tenant_access
    
    async def _parse_action_resource(self, action: str, resource: str) -> Tuple[Optional[ResourceType], Optional[Permission]]:
        """Parse action and resource into ResourceType and Permission"""
        try:
            # Map action to permission
            permission_map = {
                "read": Permission.READ,
                "write": Permission.WRITE,
                "admin": Permission.ADMIN,
                "delete": Permission.DELETE,
                "config": Permission.CONFIG,
                "audit": Permission.AUDIT,
                "billing": Permission.BILLING
            }
            
            # Map resource to resource type
            resource_type_map = {
                "metrics": ResourceType.METRICS,
                "logs": ResourceType.LOGS,
                "traces": ResourceType.TRACES,
                "dashboards": ResourceType.DASHBOARDS,
                "alerts": ResourceType.ALERTS,
                "users": ResourceType.USERS,
                "tenants": ResourceType.TENANTS,
                "configs": ResourceType.CONFIGS,
                "billing": ResourceType.BILLING,
                "system": ResourceType.SYSTEM
            }
            
            permission = permission_map.get(action.lower())
            resource_type = resource_type_map.get(resource.lower().split("/")[0])  # Handle resource paths
            
            return resource_type, permission
            
        except Exception as e:
            logger.error("Error parsing action/resource", action=action, resource=resource, error=str(e))
            return None, None
    
    async def _check_role_permission(self, role_name: str, resource_type: ResourceType, 
                                   permission: Permission, tenant_id: Optional[str] = None) -> bool:
        """Check if role has specific permission for resource type"""
        if role_name not in self.config.roles:
            return False
        
        role = self.config.roles[role_name]
        
        # Check tenant scope
        if role.tenant_scope and tenant_id and role.tenant_scope != tenant_id:
            return False
        
        # Check resource permission
        if resource_type not in role.permissions:
            return False
        
        return permission in role.permissions[resource_type]
    
    async def _evaluate_policies(self, user_id: str, user_roles: List[str], action: str, 
                               resource: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Evaluate policy rules for authorization decision"""
        try:
            applicable_policies = []
            
            # Find applicable policies
            for policy in self.config.policies:
                if await self._policy_applies(policy, user_id, user_roles, action, resource, tenant_id):
                    applicable_policies.append(policy)
            
            if not applicable_policies:
                return {"effect": "allow", "policy": None}
            
            # Sort by priority (higher priority first)
            applicable_policies.sort(key=lambda p: p.priority, reverse=True)
            
            # Evaluate based on policy evaluation order
            if self.config.policy_evaluation_order == "deny-overrides":
                # If any policy denies, deny access
                for policy in applicable_policies:
                    if policy.effect == "deny":
                        return {"effect": "deny", "policy": policy.name}
                return {"effect": "allow", "policy": None}
            
            else:  # allow-overrides
                # If any policy allows, allow access
                for policy in applicable_policies:
                    if policy.effect == "allow":
                        return {"effect": "allow", "policy": policy.name}
                return {"effect": "deny", "policy": applicable_policies[0].name if applicable_policies else None}
                
        except Exception as e:
            logger.error("Policy evaluation error", error=str(e))
            return {"effect": "deny", "policy": "error"}
    
    async def _policy_applies(self, policy: PolicyRule, user_id: str, user_roles: List[str], 
                            action: str, resource: str, tenant_id: Optional[str] = None) -> bool:
        """Check if policy rule applies to current authorization request"""
        try:
            # Check actions
            if policy.actions and action not in policy.actions and "*" not in policy.actions:
                return False
            
            # Check resources (support wildcards)
            if policy.resources:
                resource_match = False
                for policy_resource in policy.resources:
                    if policy_resource == "*" or resource.startswith(policy_resource.rstrip("*")):
                        resource_match = True
                        break
                if not resource_match:
                    return False
            
            # Check conditions
            if policy.conditions:
                # Time-based conditions
                if "time_range" in policy.conditions:
                    time_range = policy.conditions["time_range"]
                    current_hour = datetime.now().hour
                    if not (time_range["start"] <= current_hour <= time_range["end"]):
                        return False
                
                # Role-based conditions
                if "required_roles" in policy.conditions:
                    required_roles = policy.conditions["required_roles"]
                    if not any(role in user_roles for role in required_roles):
                        return False
                
                # Tenant-based conditions
                if "tenant_filter" in policy.conditions:
                    tenant_filter = policy.conditions["tenant_filter"]
                    if tenant_id and tenant_id not in tenant_filter:
                        return False
            
            return True
            
        except Exception as e:
            logger.error("Policy applicability check error", policy=policy.name, error=str(e))
            return False
    
    async def _get_required_roles(self, resource_type: ResourceType, permission: Permission) -> List[str]:
        """Get list of roles that have the required permission for resource type"""
        required_roles = []
        
        for role_name, role in self.config.roles.items():
            if resource_type in role.permissions and permission in role.permissions[resource_type]:
                required_roles.append(role_name)
        
        return required_roles
    
    async def add_role(self, role: Role) -> bool:
        """Add new role to RBAC system"""
        try:
            self.config.roles[role.name] = role
            self._role_cache.clear()  # Clear cache
            logger.info("Role added", role_name=role.name)
            return True
        except Exception as e:
            logger.error("Error adding role", role_name=role.name, error=str(e))
            return False
    
    async def update_group_mapping(self, group: str, roles: List[str]) -> bool:
        """Update group to role mapping"""
        try:
            self.config.group_role_mapping[group] = roles
            logger.info("Group mapping updated", group=group, roles=roles)
            return True
        except Exception as e:
            logger.error("Error updating group mapping", group=group, error=str(e))
            return False
    
    async def add_policy(self, policy: PolicyRule) -> bool:
        """Add policy rule"""
        try:
            self.config.policies.append(policy)
            self._policy_cache.clear()  # Clear cache
            logger.info("Policy added", policy_name=policy.name)
            return True
        except Exception as e:
            logger.error("Error adding policy", policy_name=policy.name, error=str(e))
            return False