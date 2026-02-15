# Transcription Pipeline - Makefile
# Provides convenient commands for Docker operations

# Variables
IMAGE_NAME ?= transcription-pipeline
CONTAINER_NAME ?= transcription-pipeline
COMPOSE_FILE ?= docker-compose.yml

# Colors for output
BLUE := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
NC := \033[0m # No Color

.PHONY: help build up down logs shell test clean lint format

# Default target
.DEFAULT_GOAL := help

help: ## Show this help message
	@echo "$(BLUE)Transcription Pipeline - Available Commands:$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""

build: ## Build Docker image
	@echo "$(BLUE)Building Docker image...$(NC)"
	docker build -t $(IMAGE_NAME):latest .
	@echo "$(GREEN)Build complete!$(NC)"

up: ## Start containers with docker-compose
	@echo "$(BLUE)Starting containers...$(NC)"
	@if [ -f $(COMPOSE_FILE) ]; then \
		docker-compose -f $(COMPOSE_FILE) up -d; \
	else \
		docker run -d \
			--name $(CONTAINER_NAME) \
			-v $(PWD)/uploads:/app/uploads \
			-v $(PWD)/output:/app/output \
			-v $(PWD)/logs:/app/logs \
			-p 8000:8000 \
			$(IMAGE_NAME):latest; \
	fi
	@echo "$(GREEN)Containers started!$(NC)"

down: ## Stop and remove containers
	@echo "$(YELLOW)Stopping containers...$(NC)"
	@if [ -f $(COMPOSE_FILE) ]; then \
		docker-compose -f $(COMPOSE_FILE) down; \
	else \
		docker stop $(CONTAINER_NAME) 2>/dev/null || true; \
		docker rm $(CONTAINER_NAME) 2>/dev/null || true; \
	fi
	@echo "$(GREEN)Containers stopped!$(NC)"

logs: ## View container logs
	@if [ -f $(COMPOSE_FILE) ]; then \
		docker-compose -f $(COMPOSE_FILE) logs -f; \
	else \
		docker logs -f $(CONTAINER_NAME); \
	fi

shell: ## Enter container shell
	@echo "$(BLUE)Entering container shell...$(NC)"
	@if [ -f $(COMPOSE_FILE) ]; then \
		docker-compose -f $(COMPOSE_FILE) exec app /bin/bash; \
	else \
		docker exec -it $(CONTAINER_NAME) /bin/bash; \
	fi

test: ## Run tests inside container
	@echo "$(BLUE)Running tests...$(NC)"
	@if [ -f $(COMPOSE_FILE) ]; then \
		docker-compose -f $(COMPOSE_FILE) exec app python -m pytest tests/ -v; \
	else \
		docker exec $(CONTAINER_NAME) python -m pytest tests/ -v; \
	fi
	@echo "$(GREEN)Tests complete!$(NC)"

# Additional useful commands

clean: ## Remove stopped containers and unused images
	@echo "$(YELLOW)Cleaning up Docker resources...$(NC)"
	docker system prune -f
	docker volume prune -f
	@echo "$(GREEN)Cleanup complete!$(NC)"

restart: down up ## Restart containers

status: ## Show container status
	@echo "$(BLUE)Container Status:$(NC)"
	@if [ -f $(COMPOSE_FILE) ]; then \
		docker-compose -f $(COMPOSE_FILE) ps; \
	else \
		docker ps -a | grep $(CONTAINER_NAME); \
	fi

lint: ## Run linting checks
	@echo "$(BLUE)Running linting...$(NC)"
	docker run --rm -v $(PWD):/app $(IMAGE_NAME):latest \
		python -m flake8 src/ tests/ || true
	@echo "$(GREEN)Linting complete!$(NC)"

format: ## Format code with black
	@echo "$(BLUE)Formatting code...$(NC)"
	docker run --rm -v $(PWD):/app $(IMAGE_NAME):latest \
		python -m black src/ tests/ || true
	@echo "$(GREEN)Formatting complete!$(NC)"

dev: ## Start containers in development mode (with hot reload)
	@echo "$(BLUE)Starting in development mode...$(NC)"
	docker run -d \
		--name $(CONTAINER_NAME)-dev \
		-v $(PWD)/src:/app/src \
		-v $(PWD)/tests:/app/tests \
		-v $(PWD)/uploads:/app/uploads \
		-v $(PWD)/output:/app/output \
		-e DEBUG=1 \
		-p 8000:8000 \
		$(IMAGE_NAME):latest
	@echo "$(GREEN)Development container started!$(NC)"
