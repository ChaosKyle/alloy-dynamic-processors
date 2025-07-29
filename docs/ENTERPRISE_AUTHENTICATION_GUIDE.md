# Enterprise Authentication Integration Guide

## Overview

The Enterprise Authentication Integration provides LDAP/SAML authentication and advanced RBAC for the Alloy Dynamic Processors platform. This guide covers setup, configuration, and best practices for enterprise identity provider integration.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [LDAP Configuration](#ldap-configuration)
- [SAML SSO Setup](#saml-sso-setup)
- [Role-Based Access Control](#role-based-access-control)
- [Deployment Guide](#deployment-guide)
- [User Management](#user-management)
- [Audit and Compliance](#audit-and-compliance)
- [Troubleshooting](#troubleshooting)

## Architecture Overview

The authentication service integrates with your existing enterprise identity infrastructure:

```mermaid
graph TB
    subgraph "Enterprise Identity"
        AD[Active Directory]
        SAML[SAML IdP<br/>Okta/Azure AD]
    end
    
    subgraph "Authentication Service"
        AUTH[Auth Service]
        JWT[JWT Manager]
        RBAC[RBAC Engine]
        AUDIT[Audit Logger]
    end
    
    subgraph "Alloy Platform"
        GATEWAY[API Gateway]
        ALLOY[Alloy Processors]
        UI[Web Interface]
    end
    
    subgraph "Storage"
        REDIS[Redis<br/>Token Blacklist]
        POSTGRES[PostgreSQL<br/>Audit & Users]
    end
    
    AD --> AUTH
    SAML --> AUTH
    AUTH --> JWT
    AUTH --> RBAC
    AUTH --> AUDIT
    
    UI --> GATEWAY
    GATEWAY --> AUTH
    GATEWAY --> ALLOY
    
    JWT --> REDIS
    AUDIT --> POSTGRES
```

## Prerequisites

- Kubernetes cluster with Helm 3.x
- PostgreSQL database for audit logging
- Redis for token blacklist management
- Access to enterprise LDAP/Active Directory
- SAML identity provider (optional)

## LDAP Configuration

### Basic LDAP Setup

Configure LDAP integration in your Helm values:

```yaml
enterpriseAuth:
  enabled: true
  
  ldap:
    serverUri: "ldaps://ldap.company.com:636"
    bindDn: "CN=alloy-service,OU=Service Accounts,DC=company,DC=com"
    bindPassword: "secure-service-password"
    userSearchBase: "OU=Users,DC=company,DC=com"
    groupSearchBase: "OU=Groups,DC=company,DC=com"
    useTls: true
    timeout: 30
    
    attributeMapping:
      userId: "sAMAccountName"
      displayName: "displayName"
      email: "mail"
      firstName: "givenName"
      lastName: "sn"
      department: "department"
      title: "title"
      employeeId: "employeeID"
```

### Active Directory Integration

For Microsoft Active Directory, use these recommended settings:

```yaml
ldap:
  serverUri: "ldaps://dc1.company.com:636"
  bindDn: "CN=alloy-ldap-service,OU=Service Accounts,DC=company,DC=com"
  userSearchBase: "OU=Employees,DC=company,DC=com"
  groupSearchBase: "OU=Security Groups,DC=company,DC=com"
  
  # AD-specific attribute mapping
  attributeMapping:
    userId: "sAMAccountName"
    displayName: "displayName"
    email: "userPrincipalName"
    firstName: "givenName"
    lastName: "sn"
    department: "department"
    title: "title"
    manager: "manager"
    employeeId: "employeeNumber"
```

### Testing LDAP Connection

Deploy with LDAP configuration and test:

```bash
# Check auth service logs
kubectl logs -f deployment/alloy-auth-service -n observability

# Test authentication endpoint
curl -X POST https://auth.company.com/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "testpassword",
    "tenant_id": "company"
  }'
```

## SAML SSO Setup

### Okta Configuration

1. **Create SAML Application in Okta:**
   - Single sign on URL: `https://auth.company.com/auth/saml/acs`
   - Audience URI: `urn:alloy:auth-service`
   - Name ID format: `EmailAddress`

2. **Configure Helm values:**

```yaml
enterpriseAuth:
  saml:
    sp:
      entityId: "urn:alloy:auth-service"
      acsUrl: "https://auth.company.com/auth/saml/acs"
      slsUrl: "https://auth.company.com/auth/saml/sls"
    
    idp:
      entityId: "http://www.okta.com/exk1234567890"
      ssoUrl: "https://dev-123456.okta.com/app/dev-123456_alloy_1/exk1234567890/sso/saml"
      slsUrl: "https://dev-123456.okta.com/app/dev-123456_alloy_1/exk1234567890/slo/saml"
      x509Cert: |
        -----BEGIN CERTIFICATE-----
        MIICmTCCAYECBgF7... [Okta certificate]
        -----END CERTIFICATE-----
    
    attributeMapping:
      userId: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"
      email: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"
      displayName: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/displayname"
      firstName: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname"
      lastName: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname"
      groups: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/groups"
```

### Azure AD Configuration

For Azure Active Directory SAML:

```yaml
saml:
  idp:
    entityId: "https://sts.windows.net/tenant-guid/"
    ssoUrl: "https://login.microsoftonline.com/tenant-guid/saml2"
    x509Cert: |
      -----BEGIN CERTIFICATE-----
      [Azure AD certificate]
      -----END CERTIFICATE-----
  
  attributeMapping:
    userId: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"
    email: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"
    displayName: "http://schemas.microsoft.com/identity/claims/displayname"
    groups: "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups"
```

## Role-Based Access Control

### Default Roles

The system includes these built-in roles:

- **system_admin**: Full platform access
- **tenant_admin**: Full tenant access
- **sre**: Operational access with alerting
- **developer**: Development and debugging access
- **security_auditor**: Read-only with audit capabilities
- **finance_analyst**: Billing and cost access
- **viewer**: Read-only access to observability data

### Group to Role Mapping

Configure how LDAP/SAML groups map to platform roles:

```yaml
enterpriseAuth:
  rbac:
    groupRoleMapping:
      # Enterprise groups to platform roles
      "Domain Admins": ["system_admin"]
      "Observability Platform Admins": ["tenant_admin"]
      "Site Reliability Engineers": ["sre"]
      "Software Engineers": ["developer"]
      "Security Operations": ["security_auditor"]
      "Finance Team": ["finance_analyst"]
      "All Company Users": ["viewer"]
      
      # Department-specific mappings
      "Engineering - Platform": ["sre", "developer"]
      "Engineering - Frontend": ["developer"]
      "Operations - NOC": ["sre"]
      "Security - SOC": ["security_auditor"]
```

### Custom Roles

Define custom roles for specific needs:

```yaml
rbac:
  customRoles:
  - name: "compliance_officer"
    description: "Compliance officer with audit and billing access"
    permissions:
      metrics: ["read", "audit"]
      logs: ["read", "audit"]
      traces: ["read", "audit"]
      billing: ["read", "billing"]
      users: ["read", "audit"]
    priority: 700
```

### Policy-Based Access Control

Implement fine-grained policies:

```yaml
rbac:
  policies:
  - name: "business_hours_only"
    effect: "deny"
    actions: ["admin", "config"]
    resources: ["system/*"]
    conditions:
      time_range:
        start: 18  # 6 PM
        end: 8     # 8 AM
    priority: 100
  
  - name: "tenant_isolation"
    effect: "deny"
    actions: ["*"]
    resources: ["tenants/*"]
    conditions:
      tenant_filter: ["allowed-tenant-1", "allowed-tenant-2"]
    priority: 200
```

## Deployment Guide

### Prerequisites Setup

1. **Create namespace and secrets:**

```bash
# Create namespace
kubectl create namespace observability

# Create auth service secret
kubectl create secret generic alloy-auth-secret \
  --from-literal=secret_key="$(openssl rand -base64 32)" \
  --from-literal=ldap_bind_password="your-ldap-password" \
  --from-literal=database_url="postgresql://auth:password@postgres:5432/auth" \
  --from-literal=redis_url="redis://redis:6379" \
  -n observability
```

2. **Deploy dependencies:**

```bash
# Deploy PostgreSQL
helm install postgres oci://registry-1.docker.io/bitnamicharts/postgresql \
  --set auth.username=auth \
  --set auth.password=password \
  --set auth.database=auth \
  -n observability

# Deploy Redis
helm install redis oci://registry-1.docker.io/bitnamicharts/redis \
  --set auth.enabled=false \
  -n observability
```

### Deploy Authentication Service

```bash
# Deploy with enterprise authentication enabled
helm install alloy-platform ./alloy/helm/alloy-dynamic-processors \
  --set enterpriseAuth.enabled=true \
  --set enterpriseAuth.ldap.serverUri="ldaps://your-ldap.com:636" \
  --set enterpriseAuth.ldap.bindDn="CN=service,DC=company,DC=com" \
  --set enterpriseAuth.saml.enabled=true \
  -n observability
```

### Production Deployment Example

```yaml
# values-production.yaml
enterpriseAuth:
  enabled: true
  replicaCount: 3
  
  # High availability configuration
  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 10
  
  # Production security settings
  jwt:
    algorithm: "RS256"  # Use asymmetric signing
    accessTokenExpireMinutes: 30  # Shorter token lifetime
  
  # Production LDAP with failover
  ldap:
    serverUri: "ldaps://ldap1.company.com:636,ldaps://ldap2.company.com:636"
    useTls: true
    timeout: 10
  
  # Enable comprehensive audit logging
  audit:
    retentionDays: 365  # Compliance requirement
    enableComplianceLogging: true
  
  # Resource limits for production
  resources:
    limits:
      cpu: 1000m
      memory: 1Gi
    requests:
      cpu: 500m
      memory: 512Mi
```

## User Management

### Self-Service Features

Users can access self-service features at `https://auth.company.com/user`:

- View profile information
- See group memberships and roles
- View recent login activity
- Access token management

### Administrative Interface

Administrators can manage users via API:

```bash
# List all users
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://auth.company.com/admin/users

# Get user details
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://auth.company.com/admin/users/john.doe

# Update user roles
curl -X PATCH -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"roles": ["developer", "sre"]}' \
  https://auth.company.com/admin/users/john.doe/roles
```

### Automated Provisioning

Integrate with HR systems for automated user lifecycle:

```yaml
# Example webhook configuration
webhooks:
  user_provisioning:
    enabled: true
    endpoint: "https://auth.company.com/webhooks/user-provisioning"
    events: ["user.created", "user.updated", "user.disabled"]
    authentication:
      type: "bearer_token"
      token: "webhook-secret-token"
```

## Audit and Compliance

### Audit Events

The system logs comprehensive audit events:

- Authentication attempts (success/failure)
- Authorization decisions
- Role changes
- Configuration modifications
- Security violations

### Compliance Reports

Generate compliance reports:

```bash
# Generate SOX compliance report
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "https://auth.company.com/audit/compliance/sox?start=2024-01-01&end=2024-12-31"

# User activity report
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "https://auth.company.com/audit/users/activity?user_id=john.doe&days=30"
```

### Data Retention

Configure audit data retention:

```yaml
audit:
  retentionDays: 2555  # 7 years for financial compliance
  archiveToS3: true
  archiveBucket: "company-audit-logs"
  encryptionEnabled: true
```

## Troubleshooting

### Common Issues

1. **LDAP Connection Failures:**
```bash
# Check LDAP connectivity
kubectl exec -it deployment/alloy-auth-service -- \
  python -c "
import ldap
conn = ldap.initialize('ldaps://ldap.company.com:636')
print('LDAP connection successful')
"
```

2. **SAML Configuration Issues:**
```bash
# Validate SAML metadata
curl https://auth.company.com/auth/saml/metadata
```

3. **Token Validation Errors:**
```bash
# Check Redis connectivity
kubectl exec -it deployment/alloy-auth-service -- \
  redis-cli -h redis ping
```

### Debug Mode

Enable debug logging:

```yaml
enterpriseAuth:
  debug: true
  
  # Additional logging
  podAnnotations:
    logging.level: "DEBUG"
```

### Health Checks

Monitor service health:

```bash
# Check service health
curl https://auth.company.com/health

# Check component health
curl https://auth.company.com/health | jq '.components'
```

## Security Best Practices

1. **Use TLS everywhere**
2. **Rotate secrets regularly**
3. **Implement least-privilege access**
4. **Monitor authentication failures**
5. **Regular security audits**
6. **Use asymmetric JWT signing in production**
7. **Implement rate limiting**
8. **Enable comprehensive audit logging**

## Support

For additional support:
- Check service logs: `kubectl logs deployment/alloy-auth-service -n observability`
- Review audit logs for authentication events
- Consult the main project documentation
- Open GitHub issues for bugs or feature requests