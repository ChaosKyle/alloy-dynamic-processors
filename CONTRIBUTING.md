# Contributing to Alloy Dynamic Processors

Thank you for your interest in contributing to the Alloy Dynamic Processors project! This document provides guidelines and procedures for contributing to this enterprise-grade observability solution.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing Requirements](#testing-requirements)
- [Security Guidelines](#security-guidelines)
- [Documentation Standards](#documentation-standards)
- [Pull Request Process](#pull-request-process)
- [Community Guidelines](#community-guidelines)

---

## Code of Conduct

This project adheres to the Grafana [Code of Conduct](https://grafana.com/docs/grafana/latest/community/code-of-conduct/). By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

### Our Standards

**Positive behaviors include:**
- Using welcoming and inclusive language
- Being respectful of differing viewpoints and experiences
- Gracefully accepting constructive criticism
- Focusing on what is best for the community
- Showing empathy towards other community members

**Unacceptable behaviors include:**
- Harassment, discrimination, or offensive comments
- Public or private harassment
- Publishing others' private information without permission
- Other conduct which could reasonably be considered inappropriate

---

## Getting Started

### Prerequisites

Before contributing, ensure you have:

- **Docker & Docker Compose**: For containerized development
- **Kubernetes cluster**: For testing deployments (minikube, kind, or cloud cluster)
- **Helm 3.x**: For managing Kubernetes deployments
- **Git**: For version control
- **Python 3.11+**: For AI sorter development
- **Go 1.21+**: For Alloy configuration validation

### Development Environment Setup

1. **Fork and Clone the Repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/alloy-dynamic-processors.git
   cd alloy-dynamic-processors
   ```

2. **Set Up Development Environment**
   ```bash
   # Install pre-commit hooks
   pip install pre-commit
   pre-commit install
   
   # Set up local development environment
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Validate Environment**
   ```bash
   # Test Alloy configurations
   ./scripts/validate-configs.sh
   
   # Run AI sorter tests
   cd alloy/processors/ai_sorter
   pip install -r requirements.txt
   pytest
   ```

### Project Structure

```
alloy-dynamic-processors/
├── .github/                    # GitHub workflows and templates
├── alloy/                      # Main Alloy implementation
│   ├── configs/               # Alloy River configurations
│   ├── helm/                  # Helm charts for deployment
│   ├── processors/            # Custom processors (AI sorter)
│   └── scripts/               # Deployment and utility scripts
├── docs/                      # Detailed documentation
├── examples/                  # Usage examples and demos
└── tools/                     # Development and maintenance tools
```

---

## Development Workflow

### Branch Strategy

We use **GitFlow** with the following branch structure:

- **`main`**: Production-ready code
- **`develop`**: Integration branch for features
- **`feature/*`**: Feature development branches
- **`hotfix/*`**: Critical bug fixes
- **`release/*`**: Release preparation branches

### Workflow Steps

1. **Create Feature Branch**
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feature/your-feature-name
   ```

2. **Develop and Test**
   ```bash
   # Make your changes
   # Run tests locally
   ./scripts/test-local.sh
   
   # Validate configurations
   ./scripts/validate-configs.sh
   ```

3. **Commit Changes**
   ```bash
   # Follow conventional commits
   git commit -m "feat: add new AI provider integration
   
   - Add OpenAI provider alongside Grok
   - Implement fallback mechanism
   - Add configuration validation
   - Update documentation
   
   Closes #123"
   ```

4. **Push and Create PR**
   ```bash
   git push origin feature/your-feature-name
   # Create pull request via GitHub UI
   ```

### Conventional Commits

We use [Conventional Commits](https://www.conventionalcommits.org/) for consistent commit messages:

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `security`: Security-related changes

**Examples:**
```bash
feat(ai-sorter): add multi-provider support
fix(helm): correct RBAC permissions for ServiceAccount
docs(security): update threat model documentation
test(alloy): add integration tests for routing processor
```

---

## Coding Standards

### General Principles

1. **Readability**: Code should be self-documenting and easy to understand
2. **Maintainability**: Write code that is easy to modify and extend
3. **Security**: Always consider security implications
4. **Performance**: Optimize for performance without sacrificing readability
5. **Testing**: Write comprehensive tests for all functionality

### Language-Specific Standards

#### Python (AI Sorter)

**Style Guide:**
- Follow [PEP 8](https://pep8.org/) for Python code style
- Use [Black](https://black.readthedocs.io/) for code formatting
- Use [isort](https://pycqa.github.io/isort/) for import sorting
- Use [mypy](https://mypy.readthedocs.io/) for type checking

**Code Example:**
```python
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

class TelemetryClassifier:
    """Classifies telemetry data using AI providers."""
    
    def __init__(self, providers: List[str]) -> None:
        self.providers = providers
        
    async def classify(
        self, 
        data: TelemetryData, 
        timeout: Optional[int] = 30
    ) -> ClassificationResult:
        """Classify telemetry data with fallback support."""
        try:
            return await self._classify_with_primary(data, timeout)
        except Exception as e:
            logger.warning(f"Primary classification failed: {e}")
            return await self._classify_with_fallback(data, timeout)
```

#### River Configuration (Alloy)

**Style Guide:**
- Use consistent indentation (2 spaces)
- Group related components together
- Add comments for complex logic
- Use descriptive component names

**Code Example:**
```hcl
// Memory limiter for protection against OOM
otelcol.processor.memory_limiter "default" {
  limit_mib      = 512
  spike_limit_mib = 128
  check_interval = "1s"

  output {
    metrics = [otelcol.processor.batch.default.input]
    logs    = [otelcol.processor.batch.default.input]
    traces  = [otelcol.processor.batch.default.input]
  }
}

// Batch processor for efficient data handling
otelcol.processor.batch "default" {
  send_batch_size     = 1024
  timeout             = "5s"
  send_batch_max_size = 2048

  output {
    metrics = [otelcol.exporter.prometheus.grafana_cloud.input]
    logs    = [otelcol.exporter.loki.grafana_cloud.input]
    traces  = [otelcol.exporter.otlp.grafana_cloud.input]
  }
}
```

#### YAML (Helm Charts)

**Style Guide:**
- Use 2-space indentation
- Quote string values containing special characters
- Use meaningful variable names
- Add comments for complex logic

**Code Example:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "alloy.fullname" . }}
  labels:
    {{- include "alloy.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      {{- include "alloy.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      annotations:
        # Force pod restart on config changes
        checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
      labels:
        {{- include "alloy.selectorLabels" . | nindent 8 }}
```

---

## Testing Requirements

### Test Categories

1. **Unit Tests**: Test individual functions and components
2. **Integration Tests**: Test component interactions
3. **End-to-End Tests**: Test complete workflows
4. **Security Tests**: Test security controls and vulnerabilities
5. **Performance Tests**: Test scalability and performance

### Testing Standards

#### Python Testing

**Framework**: pytest with fixtures and mocking

```python
import pytest
from unittest.mock import Mock, patch
from ai_sorter import TelemetryClassifier

@pytest.fixture
def mock_ai_provider():
    """Mock AI provider for testing."""
    provider = Mock()
    provider.classify.return_value = {
        "category": "critical",
        "confidence": 0.95
    }
    return provider

def test_classification_success(mock_ai_provider):
    """Test successful telemetry classification."""
    classifier = TelemetryClassifier([mock_ai_provider])
    result = classifier.classify(sample_telemetry_data())
    
    assert result.category == "critical"
    assert result.confidence > 0.9
    mock_ai_provider.classify.assert_called_once()

@patch('ai_sorter.requests.post')
def test_api_failure_fallback(mock_post):
    """Test fallback behavior on API failure."""
    mock_post.side_effect = ConnectionError("API unavailable")
    
    classifier = TelemetryClassifier(["grok", "openai"])
    result = classifier.classify(sample_telemetry_data())
    
    # Should fall back to default classification
    assert result.category in ["critical", "warning", "info"]
```

#### Alloy Configuration Testing

**Validation**: Configuration syntax and logic validation

```bash
#!/bin/bash
# validate-configs.sh

echo "Validating Alloy configurations..."

for config in alloy/configs/*.river; do
    echo "Validating $config"
    
    # Syntax validation
    alloy fmt --verify "$config" || {
        echo "❌ Syntax error in $config"
        exit 1
    }
    
    # Logic validation (custom checks)
    ./tools/validate-alloy-logic.sh "$config" || {
        echo "❌ Logic error in $config"
        exit 1
    }
    
    echo "✅ $config is valid"
done

echo "All configurations validated successfully!"
```

#### Helm Chart Testing

**Framework**: helm lint, helm test, conftest

```bash
#!/bin/bash
# test-helm-charts.sh

cd alloy/helm/alloy-dynamic-processors

# Lint Helm chart
echo "Linting Helm chart..."
helm lint . || exit 1

# Template and validate
echo "Templating Helm chart..."
helm template test-release . \
  --set aiSorter.enabled=true \
  --set grafanaCloud.enabled=true \
  > /tmp/test-manifests.yaml

# Validate with conftest
echo "Validating with conftest policies..."
conftest verify --policy ../../policies /tmp/test-manifests.yaml || exit 1

echo "Helm chart validation successful!"
```

### Coverage Requirements

- **Unit Tests**: Minimum 80% code coverage
- **Integration Tests**: All major workflows covered
- **Security Tests**: All security controls tested
- **Performance Tests**: Critical paths benchmarked

### Test Execution

```bash
# Run all tests
./scripts/test-all.sh

# Run specific test categories
./scripts/test-unit.sh
./scripts/test-integration.sh
./scripts/test-security.sh
./scripts/test-performance.sh

# Run tests with coverage
./scripts/test-coverage.sh
```

---

## Security Guidelines

### Security Review Process

All contributions must undergo security review:

1. **Automated Security Scanning**: All PRs are automatically scanned
2. **Manual Security Review**: Security team reviews high-risk changes
3. **Threat Modeling**: New features require threat analysis
4. **Penetration Testing**: Major changes may require pen testing

### Security Checklist

Before submitting a PR, ensure:

- [ ] No hardcoded secrets or sensitive information
- [ ] Input validation for all user inputs
- [ ] Proper error handling without information disclosure
- [ ] Secure defaults for all configurations
- [ ] Principle of least privilege applied
- [ ] Security tests added for new functionality
- [ ] Dependencies scanned for vulnerabilities
- [ ] Documentation updated with security considerations

### Secure Coding Practices

#### Input Validation

```python
from pydantic import BaseModel, validator
import re

class TelemetryRequest(BaseModel):
    service_name: str
    data: dict
    
    @validator('service_name')
    def validate_service_name(cls, v):
        if not re.match(r'^[a-zA-Z0-9\-_]+$', v):
            raise ValueError('Invalid service name format')
        if len(v) > 100:
            raise ValueError('Service name too long')
        return v
```

#### Secret Management

```python
import os
from typing import Optional

def get_api_key(key_name: str) -> Optional[str]:
    """Securely retrieve API key from environment or secret store."""
    # Try environment variable first
    key = os.getenv(key_name)
    if key:
        return key
    
    # Try Kubernetes secret mount
    secret_path = f"/var/secrets/{key_name.lower()}"
    try:
        with open(secret_path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None
```

---

## Documentation Standards

### Documentation Types

1. **Code Documentation**: Inline comments and docstrings
2. **API Documentation**: OpenAPI/Swagger specifications
3. **User Documentation**: Installation and usage guides
4. **Architecture Documentation**: System design and decisions
5. **Operational Documentation**: Runbooks and procedures

### Documentation Requirements

#### Code Comments

```python
def classify_telemetry(
    data: TelemetryData,
    providers: List[AIProvider],
    timeout: int = 30
) -> ClassificationResult:
    """
    Classify telemetry data using AI providers with fallback support.
    
    This function attempts classification with the primary provider first,
    falling back to secondary providers if the primary fails. It implements
    circuit breaker patterns to avoid cascading failures.
    
    Args:
        data: The telemetry data to classify
        providers: List of AI providers in priority order
        timeout: Maximum time to wait for classification (seconds)
        
    Returns:
        ClassificationResult containing category, confidence, and metadata
        
    Raises:
        ClassificationError: If all providers fail or timeout
        ValidationError: If input data is invalid
        
    Example:
        >>> data = TelemetryData(type="log", content={"message": "error"})
        >>> providers = [GrokProvider(), OpenAIProvider()]
        >>> result = classify_telemetry(data, providers)
        >>> print(result.category)  # "critical"
    """
```

#### README Standards

Each component should have a comprehensive README:

```markdown
# Component Name

Brief description of the component and its purpose.

## Features

- Feature 1: Description
- Feature 2: Description
- Feature 3: Description

## Quick Start

### Prerequisites
- Requirement 1
- Requirement 2

### Installation
```bash
# Installation commands
```

### Basic Usage
```bash
# Usage examples
```

## Configuration

### Environment Variables
| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| VAR_NAME | Description | default | Yes |

### Configuration Files
Description of configuration options.

## API Reference

Link to detailed API documentation.

## Security Considerations

Security-specific information for this component.

## Troubleshooting

Common issues and solutions.

## Contributing

Link to this contributing guide.
```

---

## Pull Request Process

### PR Requirements

1. **Branch up to date**: Rebase on latest develop branch
2. **Tests passing**: All automated tests must pass
3. **Code review**: At least one approving review required
4. **Security review**: Security approval for sensitive changes
5. **Documentation**: Updated documentation for new features
6. **Changelog**: Entry added to CHANGELOG.md

### PR Template

```markdown
## Description
Brief description of changes made.

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Security improvement
- [ ] Performance optimization

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing completed
- [ ] Security testing completed

## Security Considerations
- [ ] No secrets or sensitive data in code
- [ ] Input validation implemented
- [ ] Security review completed (if applicable)
- [ ] Threat model updated (if applicable)

## Documentation
- [ ] Code documentation updated
- [ ] README updated
- [ ] API documentation updated
- [ ] CHANGELOG.md updated

## Checklist
- [ ] My code follows the style guidelines
- [ ] I have performed a self-review of my code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes

## Related Issues
Closes #[issue number]
```

### Review Process

1. **Author Responsibilities**:
   - Ensure PR meets all requirements
   - Respond to review feedback promptly
   - Maintain PR in mergeable state

2. **Reviewer Responsibilities**:
   - Review within 48 hours
   - Provide constructive feedback
   - Test changes when appropriate
   - Approve when standards are met

3. **Maintainer Responsibilities**:
   - Final review and merge approval
   - Ensure consistency with project goals
   - Coordinate releases and deployments

---

## Community Guidelines

### Communication Channels

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: General questions and community discussion
- **Slack**: Real-time community chat (link in README)
- **Email**: security@grafana.com for security issues

### Getting Help

1. **Check Documentation**: README, docs/, and inline comments
2. **Search Issues**: Existing issues may have solutions
3. **Ask Questions**: Use GitHub Discussions for help
4. **Report Bugs**: Create detailed bug reports with reproduction steps

### Recognition

We recognize contributors through:

- **Contributors section** in README
- **Release notes** acknowledgments
- **Hall of fame** for significant contributions
- **Swag and rewards** for exceptional contributions

### Maintainer Guidelines

Current maintainers:
- Review PRs and issues promptly
- Maintain project roadmap and vision
- Ensure code quality and security standards
- Foster inclusive community environment
- Make final decisions on controversial changes

---

## Development Tools and Resources

### Required Tools

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Pre-commit hooks
pre-commit install

# Code formatting
black .
isort .

# Type checking
mypy .

# Security scanning
bandit -r .
safety check
```

### Recommended IDE Setup

**VS Code Extensions:**
- Python
- YAML
- Docker
- Kubernetes
- GitLens
- Security scanning extensions

**Configuration:**
```json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.mypyEnabled": true,
    "python.formatting.provider": "black",
    "editor.formatOnSave": true
}
```

### Useful Resources

- [Grafana Documentation](https://grafana.com/docs/)
- [Grafana Alloy Documentation](https://grafana.com/docs/alloy/)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Helm Documentation](https://helm.sh/docs/)

---

## Questions and Support

If you have questions about contributing:

1. **Check the documentation** first
2. **Search existing issues** for similar questions
3. **Use GitHub Discussions** for general questions
4. **Contact maintainers** for specific guidance

We appreciate your contributions to making observability better for everyone!

---

*This contributing guide is reviewed and updated regularly. Last updated: January 2025*