# Enterprise Integration Patterns

## Overview

This document provides comprehensive guidance for integrating Alloy Dynamic Processors with enterprise systems, including identity providers, monitoring tools, ITSM platforms, and cloud services.

## Table of Contents

- [Identity Integration](#identity-integration)
- [Monitoring Tool Integration](#monitoring-tool-integration)
- [ITSM Integration](#itsm-integration)
- [Cloud Service Integration](#cloud-service-integration)
- [Message Queue Integration](#message-queue-integration)
- [Database Integration](#database-integration)
- [API Gateway Integration](#api-gateway-integration)
- [Service Mesh Integration](#service-mesh-integration)

---

## Identity Integration

### LDAP/Active Directory Integration

```python
# LDAP authentication provider
import ldap3
from typing import Optional, Dict, List

class LDAPAuthProvider:
    def __init__(self, server: str, base_dn: str, bind_user: str, bind_password: str):
        self.server = ldap3.Server(server, use_ssl=True)
        self.base_dn = base_dn
        self.bind_user = bind_user
        self.bind_password = bind_password
    
    async def authenticate(self, username: str, password: str) -> Optional[Dict]:
        """Authenticate user against LDAP/AD"""
        try:
            # Bind as service account
            conn = ldap3.Connection(
                self.server, 
                user=self.bind_user, 
                password=self.bind_password,
                auto_bind=True
            )
            
            # Search for user
            search_filter = f"(sAMAccountName={username})"
            conn.search(
                search_base=self.base_dn,
                search_filter=search_filter,
                attributes=['cn', 'memberOf', 'mail', 'department']
            )
            
            if not conn.entries:
                return None
            
            user_entry = conn.entries[0]
            user_dn = user_entry.entry_dn
            
            # Authenticate user
            user_conn = ldap3.Connection(self.server, user=user_dn, password=password)
            if not user_conn.bind():
                return None
            
            # Extract user information
            groups = [
                group.split(',')[0].split('=')[1] 
                for group in user_entry.memberOf.values
            ]
            
            return {
                'username': username,
                'display_name': str(user_entry.cn),
                'email': str(user_entry.mail),
                'department': str(user_entry.department),
                'groups': groups,
                'roles': self._map_groups_to_roles(groups)
            }
            
        except Exception as e:
            logger.error(f"LDAP authentication failed: {e}")
            return None
    
    def _map_groups_to_roles(self, groups: List[str]) -> List[str]:
        """Map LDAP groups to application roles"""
        role_mapping = {
            'AlloyAdmins': ['admin', 'user'],
            'AlloyOperators': ['operator', 'user'],
            'AlloyViewers': ['viewer', 'user']
        }
        
        roles = set()
        for group in groups:
            if group in role_mapping:
                roles.update(role_mapping[group])
        
        return list(roles)
```

### SAML SSO Integration

```python
# SAML authentication configuration
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.settings import OneLogin_Saml2_Settings

class SAMLAuthProvider:
    def __init__(self, saml_settings: Dict):
        self.saml_settings = saml_settings
    
    def get_saml_auth(self, request):
        """Initialize SAML auth object"""
        return OneLogin_Saml2_Auth(request, self.saml_settings)
    
    def process_saml_response(self, request) -> Optional[Dict]:
        """Process SAML authentication response"""
        auth = self.get_saml_auth(request)
        auth.process_response()
        
        if not auth.is_authenticated():
            return None
        
        attributes = auth.get_attributes()
        
        return {
            'username': auth.get_nameid(),
            'display_name': attributes.get('DisplayName', [''])[0],
            'email': attributes.get('EmailAddress', [''])[0],
            'groups': attributes.get('Groups', []),
            'roles': self._map_saml_groups_to_roles(attributes.get('Groups', []))
        }

# SAML configuration
SAML_SETTINGS = {
    "sp": {
        "entityId": "https://alloy.yourcompany.com",
        "assertionConsumerService": {
            "url": "https://alloy.yourcompany.com/auth/saml/acs",
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        },
        "singleLogoutService": {
            "url": "https://alloy.yourcompany.com/auth/saml/sls",
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        },
        "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        "x509cert": "",
        "privateKey": ""
    },
    "idp": {
        "entityId": "https://idp.yourcompany.com",
        "singleSignOnService": {
            "url": "https://idp.yourcompany.com/sso",
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        },
        "singleLogoutService": {
            "url": "https://idp.yourcompany.com/slo",
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        },
        "x509cert": "IDP_CERTIFICATE_HERE"
    }
}
```

### OAuth 2.0 / OpenID Connect

```yaml
# OAuth configuration for Alloy
apiVersion: v1
kind: ConfigMap
metadata:
  name: oauth-config
  namespace: alloy-system
data:
  oauth.yaml: |
    oauth:
      enabled: true
      provider: "azure"
      client_id: "${OAUTH_CLIENT_ID}"
      client_secret: "${OAUTH_CLIENT_SECRET}"
      redirect_uri: "https://alloy.yourcompany.com/auth/oauth/callback"
      scopes: ["openid", "profile", "email", "groups"]
      endpoints:
        authorization: "https://login.microsoftonline.com/TENANT_ID/oauth2/v2.0/authorize"
        token: "https://login.microsoftonline.com/TENANT_ID/oauth2/v2.0/token"
        userinfo: "https://graph.microsoft.com/v1.0/me"
      role_mapping:
        "AlloyAdmins": ["admin"]
        "AlloyOperators": ["operator"]
        "AlloyViewers": ["viewer"]
```

---

## Monitoring Tool Integration

### Datadog Integration

```python
# Datadog metrics exporter
from datadog import initialize, api
import time

class DatadogExporter:
    def __init__(self, api_key: str, app_key: str, environment: str):
        initialize(api_key=api_key, app_key=app_key)
        self.environment = environment
        self.tags = [f"environment:{environment}", "service:alloy-dynamic-processors"]
    
    async def send_metrics(self, metrics: Dict[str, float]):
        """Send metrics to Datadog"""
        datadog_metrics = []
        current_time = time.time()
        
        for metric_name, value in metrics.items():
            datadog_metrics.append({
                'metric': metric_name,
                'points': [(current_time, value)],
                'tags': self.tags
            })
        
        try:
            api.Metric.send(datadog_metrics)
        except Exception as e:
            logger.error(f"Failed to send metrics to Datadog: {e}")
    
    async def send_events(self, event: Dict):
        """Send events to Datadog"""
        try:
            api.Event.create(
                title=event['title'],
                text=event['description'],
                tags=self.tags + event.get('tags', []),
                alert_type=event.get('alert_type', 'info'),
                source_type_name='alloy'
            )
        except Exception as e:
            logger.error(f"Failed to send event to Datadog: {e}")

# Alloy configuration for Datadog
otelcol.exporter.datadog "default" {
  api {
    key = env("DATADOG_API_KEY")
    site = "datadoghq.com"
  }
  
  metrics {
    delta_ttl = 3600
    instrumentation_library_metadata = true
    resource_attributes_as_tags = true
  }
  
  traces {
    compute_stats_by_span_kind = true
    peer_tags_aggregation = true
    compute_top_level_by_span_kind = true
  }
  
  logs {
    use_resource_metadata = true
  }
}
```

### New Relic Integration

```river
// New Relic exporter configuration
otelcol.exporter.otlp "newrelic" {
  client {
    endpoint = "https://otlp.nr-data.net:4317"
    headers = {
      "api-key" = env("NEW_RELIC_LICENSE_KEY")
    }
    compression = "gzip"
  }
}

// Transform data for New Relic
otelcol.processor.attributes "newrelic_transform" {
  action {
    key = "service.name"
    from_attribute = "service.name"
    action = "update"
  }
  
  action {
    key = "newrelic.source"
    value = "alloy-dynamic-processors"
    action = "insert"
  }
}
```

### Splunk Integration

```python
# Splunk HEC integration
import asyncio
import aiohttp
import json

class SplunkHECExporter:
    def __init__(self, hec_url: str, hec_token: str, index: str = "main"):
        self.hec_url = hec_url
        self.hec_token = hec_token
        self.index = index
        self.session = None
    
    async def initialize(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession(
            headers={
                'Authorization': f'Splunk {self.hec_token}',
                'Content-Type': 'application/json'
            }
        )
    
    async def send_events(self, events: List[Dict]):
        """Send events to Splunk HEC"""
        if not self.session:
            await self.initialize()
        
        splunk_events = []
        for event in events:
            splunk_event = {
                "time": event.get('timestamp', time.time()),
                "index": self.index,
                "source": "alloy-dynamic-processors",
                "sourcetype": event.get('type', 'alloy:telemetry'),
                "event": event
            }
            splunk_events.append(splunk_event)
        
        payload = '\n'.join(json.dumps(event) for event in splunk_events)
        
        try:
            async with self.session.post(
                f"{self.hec_url}/services/collector/event",
                data=payload
            ) as response:
                if response.status != 200:
                    logger.error(f"Splunk HEC error: {response.status}")
        except Exception as e:
            logger.error(f"Failed to send events to Splunk: {e}")

# Alloy configuration for Splunk
otelcol.exporter.splunk_hec "default" {
  endpoint = env("SPLUNK_HEC_URL")
  token = env("SPLUNK_HEC_TOKEN")
  index = "alloy_telemetry"
  
  source = "alloy-dynamic-processors"
  sourcetype = "alloy:otel"
  
  max_idle_conns = 200
  max_idle_conns_per_host = 40
  max_conns_per_host = 40
  idle_conn_timeout = "10s"
}
```

---

## ITSM Integration

### ServiceNow Integration

```python
# ServiceNow REST API integration
import aiohttp
import base64
import json

class ServiceNowIntegration:
    def __init__(self, instance_url: str, username: str, password: str):
        self.instance_url = instance_url
        self.auth_header = self._create_auth_header(username, password)
        self.session = None
    
    def _create_auth_header(self, username: str, password: str) -> str:
        """Create basic auth header"""
        credentials = f"{username}:{password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded_credentials}"
    
    async def initialize(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession(
            headers={
                'Authorization': self.auth_header,
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
        )
    
    async def create_incident(self, incident_data: Dict) -> Optional[str]:
        """Create incident in ServiceNow"""
        if not self.session:
            await self.initialize()
        
        # Map telemetry data to ServiceNow fields
        servicenow_data = {
            'short_description': incident_data.get('title', 'Alloy Processing Alert'),
            'description': incident_data.get('description', ''),
            'impact': self._map_severity_to_impact(incident_data.get('severity', 'low')),
            'urgency': self._map_severity_to_urgency(incident_data.get('severity', 'low')),
            'category': 'Software',
            'subcategory': 'Monitoring',
            'assignment_group': 'Infrastructure Team',
            'caller_id': 'alloy.system',
            'business_service': 'Observability Platform'
        }
        
        try:
            async with self.session.post(
                f"{self.instance_url}/api/now/table/incident",
                json=servicenow_data
            ) as response:
                if response.status == 201:
                    result = await response.json()
                    return result['result']['sys_id']
                else:
                    logger.error(f"ServiceNow API error: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Failed to create ServiceNow incident: {e}")
            return None
    
    def _map_severity_to_impact(self, severity: str) -> str:
        """Map alert severity to ServiceNow impact"""
        mapping = {
            'critical': '1',  # High
            'warning': '2',   # Medium
            'info': '3'       # Low
        }
        return mapping.get(severity, '3')
    
    def _map_severity_to_urgency(self, severity: str) -> str:
        """Map alert severity to ServiceNow urgency"""
        mapping = {
            'critical': '1',  # High
            'warning': '2',   # Medium
            'info': '3'       # Low
        }
        return mapping.get(severity, '3')

# Alert processor for ITSM integration
class ITSMAlertProcessor:
    def __init__(self, servicenow: ServiceNowIntegration):
        self.servicenow = servicenow
    
    async def process_alert(self, alert: Dict):
        """Process alert and create ITSM ticket if needed"""
        severity = alert.get('severity', 'info')
        
        # Only create incidents for critical and warning alerts
        if severity in ['critical', 'warning']:
            incident_id = await self.servicenow.create_incident(alert)
            if incident_id:
                logger.info(f"Created ServiceNow incident: {incident_id}")
                # Update alert with incident reference
                alert['itsm_ticket'] = incident_id
        
        return alert
```

### Jira Service Management Integration

```python
# Jira Service Management integration
from jira import JIRA
import asyncio

class JiraServiceDeskIntegration:
    def __init__(self, server: str, username: str, api_token: str, service_desk_id: str):
        self.server = server
        self.service_desk_id = service_desk_id
        self.jira = JIRA(
            server=server,
            basic_auth=(username, api_token)
        )
    
    async def create_incident(self, incident_data: Dict) -> Optional[str]:
        """Create incident in Jira Service Desk"""
        try:
            # Get request types for the service desk
            request_types = self.jira.request_types(self.service_desk_id)
            incident_request_type = next(
                (rt for rt in request_types if 'incident' in rt.name.lower()),
                request_types[0]  # Fallback to first available
            )
            
            # Create the incident
            issue_dict = {
                'serviceDeskId': self.service_desk_id,
                'requestTypeId': incident_request_type.id,
                'requestFieldValues': {
                    'summary': incident_data.get('title', 'Alloy Processing Alert'),
                    'description': incident_data.get('description', ''),
                    'priority': self._map_severity_to_priority(incident_data.get('severity', 'low')),
                    'components': [{'name': 'Observability'}],
                    'labels': ['alloy', 'monitoring', 'automated']
                }
            }
            
            # Use executor to run synchronous JIRA API call
            loop = asyncio.get_event_loop()
            new_issue = await loop.run_in_executor(
                None, 
                self.jira.create_customer_request,
                issue_dict
            )
            
            return new_issue.key
            
        except Exception as e:
            logger.error(f"Failed to create Jira incident: {e}")
            return None
    
    def _map_severity_to_priority(self, severity: str) -> Dict:
        """Map alert severity to Jira priority"""
        priority_mapping = {
            'critical': {'name': 'Highest'},
            'warning': {'name': 'High'},
            'info': {'name': 'Medium'}
        }
        return priority_mapping.get(severity, {'name': 'Low'})
```

---

## Cloud Service Integration

### AWS Integration

```python
# AWS CloudWatch integration
import boto3
from botocore.exceptions import ClientError

class AWSCloudWatchIntegration:
    def __init__(self, region_name: str, access_key_id: str = None, secret_access_key: str = None):
        self.cloudwatch = boto3.client(
            'cloudwatch',
            region_name=region_name,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key
        )
        self.logs_client = boto3.client(
            'logs',
            region_name=region_name,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key
        )
    
    async def put_metric_data(self, namespace: str, metrics: List[Dict]):
        """Send custom metrics to CloudWatch"""
        try:
            metric_data = []
            for metric in metrics:
                metric_data.append({
                    'MetricName': metric['name'],
                    'Value': metric['value'],
                    'Unit': metric.get('unit', 'Count'),
                    'Dimensions': [
                        {
                            'Name': key,
                            'Value': value
                        }
                        for key, value in metric.get('dimensions', {}).items()
                    ]
                })
            
            self.cloudwatch.put_metric_data(
                Namespace=namespace,
                MetricData=metric_data
            )
            
        except ClientError as e:
            logger.error(f"CloudWatch API error: {e}")
    
    async def send_logs(self, log_group: str, log_stream: str, log_events: List[Dict]):
        """Send logs to CloudWatch Logs"""
        try:
            # Create log stream if it doesn't exist
            try:
                self.logs_client.create_log_stream(
                    logGroupName=log_group,
                    logStreamName=log_stream
                )
            except ClientError as e:
                if e.response['Error']['Code'] != 'ResourceAlreadyExistsException':
                    raise
            
            # Format log events
            formatted_events = [
                {
                    'timestamp': event['timestamp'],
                    'message': json.dumps(event['message'])
                }
                for event in log_events
            ]
            
            self.logs_client.put_log_events(
                logGroupName=log_group,
                logStreamName=log_stream,
                logEvents=formatted_events
            )
            
        except ClientError as e:
            logger.error(f"CloudWatch Logs API error: {e}")

# Alloy configuration for AWS
otelcol.exporter.awscloudwatchmetrics "default" {
  region = env("AWS_REGION")
  
  namespace = "Alloy/DynamicProcessors"
  
  dimension_rollup_option = "NoDimensionRollup"
  metric_declarations = [
    {
      dimensions = [["service.name"], ["service.name", "service.version"]]
      metric_name_selectors = [".*"]
    }
  ]
}

otelcol.exporter.awscloudwatchlogs "default" {
  region = env("AWS_REGION")
  log_group_name = "/aws/alloy/dynamic-processors"
  log_stream_name = "alloy-logs"
}
```

### Azure Integration

```python
# Azure Monitor integration
from azure.monitor.opentelemetry.exporter import AzureMonitorLogExporter, AzureMonitorMetricExporter
from azure.identity import DefaultAzureCredential

class AzureMonitorIntegration:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.credential = DefaultAzureCredential()
        
        # Initialize exporters
        self.log_exporter = AzureMonitorLogExporter(
            connection_string=connection_string
        )
        self.metric_exporter = AzureMonitorMetricExporter(
            connection_string=connection_string
        )
    
    async def send_custom_events(self, events: List[Dict]):
        """Send custom events to Azure Monitor"""
        try:
            for event in events:
                # Transform event to Azure Monitor format
                azure_event = {
                    'name': event.get('name', 'AlloyEvent'),
                    'properties': event.get('properties', {}),
                    'measurements': event.get('measurements', {}),
                    'timestamp': event.get('timestamp')
                }
                
                # Send to Azure Monitor
                self.log_exporter.export([azure_event])
                
        except Exception as e:
            logger.error(f"Azure Monitor export error: {e}")

# Alloy configuration for Azure Monitor
otelcol.exporter.azuremonitor "default" {
  connection_string = env("AZURE_MONITOR_CONNECTION_STRING")
  
  instrumentation_key = env("AZURE_MONITOR_INSTRUMENTATION_KEY")
  
  max_batch_size = 512
  export_timeout = "30s"
}
```

### Google Cloud Integration

```python
# Google Cloud Monitoring and Logging integration
from google.cloud import monitoring_v3
from google.cloud import logging_v2
import time

class GoogleCloudIntegration:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.monitoring_client = monitoring_v3.MetricServiceClient()
        self.logging_client = logging_v2.Client(project=project_id)
        self.project_path = f"projects/{project_id}"
    
    async def write_time_series(self, metrics: List[Dict]):
        """Write time series data to Google Cloud Monitoring"""
        try:
            series = []
            
            for metric in metrics:
                # Create time series
                series_data = monitoring_v3.TimeSeries()
                series_data.metric.type = f"custom.googleapis.com/alloy/{metric['name']}"
                
                # Add labels
                for key, value in metric.get('labels', {}).items():
                    series_data.metric.labels[key] = value
                
                # Add resource labels
                series_data.resource.type = "k8s_container"
                series_data.resource.labels["cluster_name"] = "alloy-cluster"
                series_data.resource.labels["namespace_name"] = "alloy-system"
                
                # Create data point
                point = monitoring_v3.Point()
                point.value.double_value = metric['value']
                point.interval.end_time.seconds = int(metric.get('timestamp', time.time()))
                
                series_data.points = [point]
                series.append(series_data)
            
            # Write time series
            self.monitoring_client.create_time_series(
                name=self.project_path,
                time_series=series
            )
            
        except Exception as e:
            logger.error(f"Google Cloud Monitoring error: {e}")
    
    async def write_log_entries(self, log_entries: List[Dict]):
        """Write log entries to Google Cloud Logging"""
        try:
            logger_instance = self.logging_client.logger("alloy-dynamic-processors")
            
            for entry in log_entries:
                logger_instance.log_struct(
                    entry,
                    severity=entry.get('severity', 'INFO'),
                    labels=entry.get('labels', {})
                )
                
        except Exception as e:
            logger.error(f"Google Cloud Logging error: {e}")

# Alloy configuration for Google Cloud
otelcol.exporter.googlecloud "default" {
  project = env("GOOGLE_CLOUD_PROJECT")
  
  metric {
    prefix = "custom.googleapis.com/alloy/"
  }
  
  log {
    default_log_name = "alloy-dynamic-processors"
  }
  
  trace {}
  
  compression = "gzip"
  
  retry_on_failure {
    enabled = true
    initial_interval = "5s"
    max_interval = "30s"
    max_elapsed_time = "300s"
  }
}
```

---

## Message Queue Integration

### Apache Kafka Integration

```python
# Kafka producer for telemetry streaming
from kafka import KafkaProducer
import json
import asyncio

class KafkaTelemetryProducer:
    def __init__(self, bootstrap_servers: List[str], security_config: Dict = None):
        config = {
            'bootstrap_servers': bootstrap_servers,
            'value_serializer': lambda v: json.dumps(v).encode('utf-8'),
            'key_serializer': lambda k: k.encode('utf-8') if k else None,
            'acks': 'all',  # Wait for all replicas
            'retries': 3,
            'batch_size': 16384,
            'linger_ms': 10,
            'buffer_memory': 33554432
        }
        
        if security_config:
            config.update(security_config)
        
        self.producer = KafkaProducer(**config)
        self.topics = {
            'critical': 'alloy.telemetry.critical',
            'warning': 'alloy.telemetry.warning',
            'info': 'alloy.telemetry.info'
        }
    
    async def send_telemetry(self, telemetry_data: Dict, classification: str = 'info'):
        """Send telemetry data to appropriate Kafka topic"""
        topic = self.topics.get(classification, self.topics['info'])
        key = telemetry_data.get('service_name', 'unknown')
        
        try:
            # Send message asynchronously
            future = self.producer.send(topic, value=telemetry_data, key=key)
            
            # Wait for confirmation
            record_metadata = await asyncio.wrap_future(
                asyncio.Future.wrap_future(future)
            )
            
            logger.info(f"Sent message to {record_metadata.topic} partition {record_metadata.partition}")
            
        except Exception as e:
            logger.error(f"Failed to send message to Kafka: {e}")
    
    def close(self):
        """Close producer connection"""
        self.producer.close()

# Kafka consumer for processing
from kafka import KafkaConsumer

class KafkaTelemetryConsumer:
    def __init__(self, topics: List[str], bootstrap_servers: List[str], group_id: str):
        self.consumer = KafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            auto_offset_reset='latest',
            enable_auto_commit=True,
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
    
    async def consume_messages(self, message_handler):
        """Consume messages and process them"""
        for message in self.consumer:
            try:
                await message_handler(message.value)
            except Exception as e:
                logger.error(f"Error processing message: {e}")

# Alloy Kafka exporter configuration
otelcol.exporter.kafka "default" {
  brokers = ["kafka-1:9092", "kafka-2:9092", "kafka-3:9092"]
  
  topic = "alloy.telemetry"
  
  encoding = "otlp_proto"
  
  producer {
    max_message_bytes = 1000000
    required_acks = 1
    compression = "gzip"
    flush_frequency = "10s"
  }
  
  auth {
    sasl {
      mechanism = "PLAIN"
      username = env("KAFKA_USERNAME")
      password = env("KAFKA_PASSWORD")
    }
    tls {
      ca_file = "/etc/ssl/certs/kafka-ca.pem"
      cert_file = "/etc/ssl/certs/kafka-client.pem"
      key_file = "/etc/ssl/certs/kafka-client-key.pem"
    }
  }
}
```

### RabbitMQ Integration

```python
# RabbitMQ integration for message queuing
import pika
import json
import asyncio
from typing import Callable

class RabbitMQIntegration:
    def __init__(self, connection_params: pika.ConnectionParameters):
        self.connection_params = connection_params
        self.connection = None
        self.channel = None
    
    async def initialize(self):
        """Initialize RabbitMQ connection"""
        self.connection = pika.BlockingConnection(self.connection_params)
        self.channel = self.connection.channel()
        
        # Declare exchanges and queues
        self.setup_exchanges_and_queues()
    
    def setup_exchanges_and_queues(self):
        """Set up RabbitMQ topology"""
        # Declare topic exchange for routing
        self.channel.exchange_declare(
            exchange='alloy.telemetry',
            exchange_type='topic',
            durable=True
        )
        
        # Declare queues for different priorities
        queues = {
            'critical': 'alloy.telemetry.critical',
            'warning': 'alloy.telemetry.warning',
            'info': 'alloy.telemetry.info'
        }
        
        for priority, queue_name in queues.items():
            self.channel.queue_declare(queue=queue_name, durable=True)
            self.channel.queue_bind(
                exchange='alloy.telemetry',
                queue=queue_name,
                routing_key=f'telemetry.{priority}'
            )
        
        # Declare dead letter queue
        self.channel.queue_declare(
            queue='alloy.telemetry.dlq',
            durable=True
        )
    
    async def publish_telemetry(self, telemetry_data: Dict, classification: str = 'info'):
        """Publish telemetry data to RabbitMQ"""
        if not self.channel:
            await self.initialize()
        
        routing_key = f'telemetry.{classification}'
        message = json.dumps(telemetry_data)
        
        try:
            self.channel.basic_publish(
                exchange='alloy.telemetry',
                routing_key=routing_key,
                body=message,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                    content_type='application/json',
                    timestamp=int(time.time())
                )
            )
            
        except Exception as e:
            logger.error(f"Failed to publish to RabbitMQ: {e}")
    
    def consume_messages(self, queue_name: str, callback: Callable):
        """Consume messages from specified queue"""
        if not self.channel:
            raise RuntimeError("Connection not initialized")
        
        def wrapper(ch, method, properties, body):
            try:
                message = json.loads(body.decode('utf-8'))
                callback(message)
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                ch.basic_nack(
                    delivery_tag=method.delivery_tag,
                    requeue=False
                )
        
        self.channel.basic_consume(
            queue=queue_name,
            on_message_callback=wrapper
        )
        
        self.channel.start_consuming()
```

---

## Database Integration

### PostgreSQL Integration

```python
# PostgreSQL integration for telemetry storage
import asyncpg
import json
from typing import List, Dict, Optional

class PostgreSQLTelemetryStore:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.pool = None
    
    async def initialize(self):
        """Initialize connection pool"""
        self.pool = await asyncpg.create_pool(
            self.connection_string,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        
        # Create tables if they don't exist
        await self.create_tables()
    
    async def create_tables(self):
        """Create telemetry storage tables"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_events (
                    id BIGSERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    service_name VARCHAR(255) NOT NULL,
                    event_type VARCHAR(100) NOT NULL,
                    classification VARCHAR(50) NOT NULL,
                    severity VARCHAR(20) NOT NULL,
                    data JSONB NOT NULL,
                    labels JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp 
                ON telemetry_events(timestamp);
                
                CREATE INDEX IF NOT EXISTS idx_telemetry_service 
                ON telemetry_events(service_name);
                
                CREATE INDEX IF NOT EXISTS idx_telemetry_classification 
                ON telemetry_events(classification);
                
                CREATE INDEX IF NOT EXISTS idx_telemetry_labels_gin 
                ON telemetry_events USING GIN(labels);
            """)
    
    async def store_telemetry(self, events: List[Dict]):
        """Store telemetry events in PostgreSQL"""
        if not self.pool:
            await self.initialize()
        
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany("""
                    INSERT INTO telemetry_events 
                    (timestamp, service_name, event_type, classification, severity, data, labels)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """, [
                    (
                        event.get('timestamp'),
                        event.get('service_name', 'unknown'),
                        event.get('type', 'unknown'),
                        event.get('classification', 'info'),
                        event.get('severity', 'info'),
                        json.dumps(event.get('data', {})),
                        json.dumps(event.get('labels', {}))
                    )
                    for event in events
                ])
    
    async def query_telemetry(
        self, 
        service_name: Optional[str] = None,
        classification: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict]:
        """Query telemetry events"""
        if not self.pool:
            await self.initialize()
        
        conditions = []
        params = []
        param_count = 0
        
        if service_name:
            param_count += 1
            conditions.append(f"service_name = ${param_count}")
            params.append(service_name)
        
        if classification:
            param_count += 1
            conditions.append(f"classification = ${param_count}")
            params.append(classification)
        
        if start_time:
            param_count += 1
            conditions.append(f"timestamp >= ${param_count}")
            params.append(start_time)
        
        if end_time:
            param_count += 1
            conditions.append(f"timestamp <= ${param_count}")
            params.append(end_time)
        
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        
        param_count += 1
        query = f"""
            SELECT id, timestamp, service_name, event_type, classification, 
                   severity, data, labels, created_at
            FROM telemetry_events
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ${param_count}
        """
        params.append(limit)
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
```

### Elasticsearch Integration

```python
# Elasticsearch integration for telemetry indexing and search
from elasticsearch import AsyncElasticsearch
import json
from typing import List, Dict, Optional

class ElasticsearchTelemetryIndex:
    def __init__(self, hosts: List[str], username: str = None, password: str = None):
        auth = (username, password) if username and password else None
        self.es = AsyncElasticsearch(
            hosts=hosts,
            http_auth=auth,
            verify_certs=True,
            ssl_show_warn=False
        )
        self.index_pattern = "alloy-telemetry-{date}"
    
    async def initialize(self):
        """Initialize Elasticsearch indices and templates"""
        # Create index template
        template_body = {
            "index_patterns": ["alloy-telemetry-*"],
            "template": {
                "settings": {
                    "number_of_shards": 3,
                    "number_of_replicas": 1,
                    "index.lifecycle.name": "alloy-telemetry-policy",
                    "index.lifecycle.rollover_alias": "alloy-telemetry"
                },
                "mappings": {
                    "properties": {
                        "timestamp": {"type": "date"},
                        "service_name": {"type": "keyword"},
                        "event_type": {"type": "keyword"},
                        "classification": {"type": "keyword"},
                        "severity": {"type": "keyword"},
                        "message": {"type": "text"},
                        "labels": {"type": "object"},
                        "data": {"type": "object"}
                    }
                }
            }
        }
        
        await self.es.indices.put_index_template(
            name="alloy-telemetry-template",
            body=template_body
        )
    
    async def index_telemetry(self, events: List[Dict]):
        """Index telemetry events in Elasticsearch"""
        if not events:
            return
        
        # Prepare bulk request
        actions = []
        for event in events:
            # Generate index name with date
            index_date = event.get('timestamp', '').split('T')[0].replace('-', '.')
            index_name = f"alloy-telemetry-{index_date}"
            
            actions.extend([
                {"index": {"_index": index_name}},
                {
                    "timestamp": event.get('timestamp'),
                    "service_name": event.get('service_name', 'unknown'),
                    "event_type": event.get('type', 'unknown'),
                    "classification": event.get('classification', 'info'),
                    "severity": event.get('severity', 'info'),
                    "message": event.get('message', ''),
                    "labels": event.get('labels', {}),
                    "data": event.get('data', {})
                }
            ])
        
        # Bulk index
        try:
            response = await self.es.bulk(body=actions)
            if response.get('errors'):
                logger.error(f"Elasticsearch bulk indexing errors: {response}")
        except Exception as e:
            logger.error(f"Failed to index to Elasticsearch: {e}")
    
    async def search_telemetry(
        self,
        query: str = None,
        service_name: str = None,
        classification: str = None,
        start_time: str = None,
        end_time: str = None,
        size: int = 100
    ) -> Dict:
        """Search telemetry events"""
        search_body = {
            "query": {"bool": {"must": []}},
            "sort": [{"timestamp": {"order": "desc"}}],
            "size": size
        }
        
        # Add query conditions
        if query:
            search_body["query"]["bool"]["must"].append({
                "multi_match": {
                    "query": query,
                    "fields": ["message", "data.*"]
                }
            })
        
        if service_name:
            search_body["query"]["bool"]["must"].append({
                "term": {"service_name": service_name}
            })
        
        if classification:
            search_body["query"]["bool"]["must"].append({
                "term": {"classification": classification}
            })
        
        if start_time or end_time:
            time_range = {}
            if start_time:
                time_range["gte"] = start_time
            if end_time:
                time_range["lte"] = end_time
            
            search_body["query"]["bool"]["must"].append({
                "range": {"timestamp": time_range}
            })
        
        try:
            response = await self.es.search(
                index="alloy-telemetry-*",
                body=search_body
            )
            return response
        except Exception as e:
            logger.error(f"Elasticsearch search error: {e}")
            return {}
```

---

*This integration patterns document provides comprehensive examples for connecting Alloy Dynamic Processors with enterprise systems. Each integration pattern includes production-ready code examples and configuration snippets for immediate implementation.*