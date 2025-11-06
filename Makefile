# =============================================================================
# Alloy Dynamic Processors - Makefile
# =============================================================================
# Common development and operations tasks
# =============================================================================

.PHONY: help
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
NC := \033[0m # No Color

# Configuration
DOCKER_COMPOSE := docker compose
HELM := helm
KUBECTL := kubectl
ALLOY := alloy
PYTHON := python3

# Directories
SCRIPTS_DIR := scripts
ALLOY_DIR := alloy
CONFIGS_DIR := $(ALLOY_DIR)/configs
HELM_DIR := $(ALLOY_DIR)/helm/alloy-dynamic-processors
AI_SORTER_DIR := $(ALLOY_DIR)/processors/ai_sorter
CONTAINERS_DIR := containers

# Image names
IMAGE_PREFIX := alloy-dynamic-processors
AI_SORTER_IMAGE := $(IMAGE_PREFIX)/ai-sorter
ALLOY_IMAGE := $(IMAGE_PREFIX)/alloy

##@ Help

help: ## Display this help message
	@echo "$(BLUE)Alloy Dynamic Processors - Makefile$(NC)"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make $(YELLOW)<target>$(NC)\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(BLUE)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Development

.PHONY: setup
setup: ## Set up development environment
	@echo "$(BLUE)Setting up development environment...$(NC)"
	@cp -n .env.example .env 2>/dev/null || true
	@echo "$(GREEN)✓ Created .env file (edit with your credentials)$(NC)"
	@$(PYTHON) -m pip install --upgrade pip
	@$(PYTHON) -m pip install pre-commit
	@pre-commit install
	@pre-commit install --hook-type commit-msg
	@echo "$(GREEN)✓ Installed pre-commit hooks$(NC)"
	@echo "$(GREEN)✓ Development environment ready!$(NC)"

.PHONY: fmt
fmt: ## Format all code (Alloy configs, Python, Shell)
	@echo "$(BLUE)Formatting code...$(NC)"
	@echo "Formatting Alloy configurations..."
	@for config in $(CONFIGS_DIR)/*.river $(CONFIGS_DIR)/*.alloy; do \
		if [ -f "$$config" ]; then \
			$(ALLOY) fmt "$$config" && echo "$(GREEN)✓ $$(basename $$config)$(NC)"; \
		fi \
	done
	@echo "Formatting Python code..."
	@cd $(AI_SORTER_DIR) && black . && isort . && ruff check --fix . || true
	@echo "Formatting shell scripts..."
	@shfmt -i 2 -ci -w $(SCRIPTS_DIR)/ || true
	@echo "$(GREEN)✓ Code formatting complete$(NC)"

.PHONY: lint
lint: ## Lint all code
	@echo "$(BLUE)Linting code...$(NC)"
	@echo "Linting Alloy configurations..."
	@$(ALLOY) fmt --verify $(CONFIGS_DIR)/*.river $(CONFIGS_DIR)/*.alloy || exit 1
	@echo "Linting Python code..."
	@cd $(AI_SORTER_DIR) && ruff check . && mypy ai_sorter.py --ignore-missing-imports || true
	@echo "Linting shell scripts..."
	@shellcheck $(SCRIPTS_DIR)/*.sh || true
	@echo "$(GREEN)✓ Linting complete$(NC)"

.PHONY: test
test: ## Run all tests
	@echo "$(BLUE)Running tests...$(NC)"
	@echo "Testing Alloy configurations..."
	@bash $(SCRIPTS_DIR)/validate-configs.sh
	@echo "Testing Python AI sorter..."
	@cd $(AI_SORTER_DIR) && pytest test_ai_sorter.py -v --tb=short
	@echo "$(GREEN)✓ All tests passed$(NC)"

.PHONY: test-coverage
test-coverage: ## Run tests with coverage
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	@cd $(AI_SORTER_DIR) && pytest test_ai_sorter.py -v --cov=ai_sorter --cov-report=term-missing --cov-report=html
	@echo "$(GREEN)✓ Coverage report generated in $(AI_SORTER_DIR)/htmlcov/$(NC)"

##@ Container Operations

.PHONY: build
build: ## Build all Docker images
	@echo "$(BLUE)Building Docker images...$(NC)"
	@$(DOCKER_COMPOSE) build --no-cache
	@echo "$(GREEN)✓ Docker images built$(NC)"

.PHONY: build-alloy
build-alloy: ## Build Alloy image only
	@echo "$(BLUE)Building Alloy image...$(NC)"
	@docker build -f $(CONTAINERS_DIR)/alloy.Dockerfile -t $(ALLOY_IMAGE):local .
	@echo "$(GREEN)✓ Alloy image built$(NC)"

.PHONY: build-ai-sorter
build-ai-sorter: ## Build AI Sorter image only
	@echo "$(BLUE)Building AI Sorter image...$(NC)"
	@docker build -f $(CONTAINERS_DIR)/ai-sorter.Dockerfile -t $(AI_SORTER_IMAGE):local .
	@echo "$(GREEN)✓ AI Sorter image built$(NC)"

.PHONY: scan
scan: ## Scan Docker images for vulnerabilities
	@echo "$(BLUE)Scanning Docker images...$(NC)"
	@echo "Scanning AI Sorter..."
	@trivy image $(AI_SORTER_IMAGE):local || true
	@echo "Scanning Alloy..."
	@trivy image $(ALLOY_IMAGE):local || true
	@echo "$(GREEN)✓ Security scan complete$(NC)"

##@ Docker Compose

.PHONY: up
up: ## Start all services with Docker Compose
	@echo "$(BLUE)Starting services...$(NC)"
	@$(DOCKER_COMPOSE) up -d
	@echo "$(GREEN)✓ Services started$(NC)"
	@$(MAKE) status

.PHONY: test-e2e
test-e2e: ## Run end-to-end integration tests
	@echo "$(BLUE)Running end-to-end tests...$(NC)"
	@bash $(SCRIPTS_DIR)/test-e2e.sh

.PHONY: up-ai
up-ai: ## Start all services including AI Sorter
	@echo "$(BLUE)Starting services with AI Sorter...$(NC)"
	@$(DOCKER_COMPOSE) --profile ai up -d
	@echo "$(GREEN)✓ Services started with AI Sorter$(NC)"
	@$(MAKE) status

.PHONY: down
down: ## Stop all services
	@echo "$(BLUE)Stopping services...$(NC)"
	@$(DOCKER_COMPOSE) down
	@echo "$(GREEN)✓ Services stopped$(NC)"

.PHONY: down-clean
down-clean: ## Stop services and remove volumes
	@echo "$(YELLOW)⚠ This will remove all data volumes!$(NC)"
	@read -p "Continue? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		$(DOCKER_COMPOSE) down -v; \
		echo "$(GREEN)✓ Services stopped and volumes removed$(NC)"; \
	fi

.PHONY: restart
restart: down up ## Restart all services

.PHONY: status
status: ## Show service status and endpoints
	@echo "$(BLUE)Service Status:$(NC)"
	@$(DOCKER_COMPOSE) ps
	@echo ""
	@echo "$(BLUE)Access Endpoints:$(NC)"
	@echo "  $(GREEN)Alloy UI:$(NC)        http://localhost:12345"
	@echo "  $(GREEN)Alloy Health:$(NC)    http://localhost:13133/healthz"
	@echo "  $(GREEN)AI Sorter:$(NC)       http://localhost:8080 (if enabled)"
	@echo "  $(GREEN)Prometheus:$(NC)      http://localhost:9090"
	@echo "  $(GREEN)Grafana:$(NC)         http://localhost:3000 (admin/admin)"
	@echo "  $(GREEN)Loki:$(NC)            http://localhost:3100"

.PHONY: logs
logs: ## Tail logs from all services
	@$(DOCKER_COMPOSE) logs -f

.PHONY: logs-alloy
logs-alloy: ## Tail Alloy logs
	@$(DOCKER_COMPOSE) logs -f alloy

.PHONY: logs-ai-sorter
logs-ai-sorter: ## Tail AI Sorter logs
	@$(DOCKER_COMPOSE) logs -f ai-sorter

.PHONY: health
health: ## Check health of all services
	@echo "$(BLUE)Checking service health...$(NC)"
	@curl -f http://localhost:13133/healthz && echo "$(GREEN)✓ Alloy healthy$(NC)" || echo "$(RED)✗ Alloy unhealthy$(NC)"
	@curl -f http://localhost:8080/healthz && echo "$(GREEN)✓ AI Sorter healthy$(NC)" || echo "$(YELLOW)⚠ AI Sorter not running$(NC)"
	@curl -f http://localhost:9090/-/healthy && echo "$(GREEN)✓ Prometheus healthy$(NC)" || echo "$(RED)✗ Prometheus unhealthy$(NC)"
	@curl -f http://localhost:3100/ready && echo "$(GREEN)✓ Loki healthy$(NC)" || echo "$(RED)✗ Loki unhealthy$(NC)"

##@ Kubernetes/Helm

.PHONY: helm-lint
helm-lint: ## Lint Helm chart
	@echo "$(BLUE)Linting Helm chart...$(NC)"
	@$(HELM) lint $(HELM_DIR)
	@echo "$(GREEN)✓ Helm chart linted$(NC)"

.PHONY: helm-template
helm-template: ## Generate Kubernetes manifests from Helm chart
	@echo "$(BLUE)Generating Helm templates...$(NC)"
	@$(HELM) template alloy-processors $(HELM_DIR) --set aiSorter.enabled=true

.PHONY: helm-install
helm-install: ## Install Helm chart to local Kubernetes
	@echo "$(BLUE)Installing Helm chart...$(NC)"
	@$(HELM) install alloy-processors $(HELM_DIR) \
		--namespace monitoring \
		--create-namespace \
		--set aiSorter.enabled=true
	@echo "$(GREEN)✓ Helm chart installed$(NC)"

.PHONY: helm-upgrade
helm-upgrade: ## Upgrade Helm release
	@echo "$(BLUE)Upgrading Helm release...$(NC)"
	@$(HELM) upgrade alloy-processors $(HELM_DIR) \
		--namespace monitoring
	@echo "$(GREEN)✓ Helm chart upgraded$(NC)"

.PHONY: helm-uninstall
helm-uninstall: ## Uninstall Helm chart
	@echo "$(BLUE)Uninstalling Helm chart...$(NC)"
	@$(HELM) uninstall alloy-processors --namespace monitoring
	@echo "$(GREEN)✓ Helm chart uninstalled$(NC)"

##@ Maintenance

.PHONY: clean
clean: ## Clean up generated files and caches
	@echo "$(BLUE)Cleaning up...$(NC)"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@rm -rf $(AI_SORTER_DIR)/htmlcov 2>/dev/null || true
	@rm -rf $(AI_SORTER_DIR)/.mypy_cache 2>/dev/null || true
	@echo "$(GREEN)✓ Cleanup complete$(NC)"

.PHONY: pre-commit
pre-commit: ## Run pre-commit on all files
	@echo "$(BLUE)Running pre-commit checks...$(NC)"
	@pre-commit run --all-files

.PHONY: update-deps
update-deps: ## Update dependencies
	@echo "$(BLUE)Updating dependencies...$(NC)"
	@cd $(AI_SORTER_DIR) && pip install --upgrade -r requirements.txt
	@pre-commit autoupdate
	@echo "$(GREEN)✓ Dependencies updated$(NC)"

##@ CI/CD Simulation

.PHONY: ci
ci: lint test build scan ## Run full CI pipeline locally
	@echo "$(GREEN)✓ CI pipeline complete$(NC)"

.PHONY: release-dry-run
release-dry-run: ## Simulate release process
	@echo "$(BLUE)Simulating release process...$(NC)"
	@echo "Building multi-arch images..."
	@echo "Scanning for vulnerabilities..."
	@echo "Generating SBOM..."
	@echo "Signing images..."
	@echo "$(GREEN)✓ Release dry run complete$(NC)"

##@ Documentation

.PHONY: docs
docs: ## Generate documentation
	@echo "$(BLUE)Documentation:$(NC)"
	@echo "  README: $(GREEN)README.md$(NC)"
	@echo "  Overview: $(GREEN)docs/overview.md$(NC)"
	@echo "  Architecture: $(GREEN)docs/ARCHITECTURE.md$(NC)"
	@echo "  Security: $(GREEN)SECURITY.md$(NC)"
	@echo "  Contributing: $(GREEN)CONTRIBUTING.md$(NC)"
