.PHONY: help build run test clean lint format docker-build docker-run docker-test

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

build: ## Build the application
	python -m pip install -r requirements.txt

run: ## Run the application locally
	python -m app.main

test: ## Run tests
	pytest

clean: ## Clean up generated files
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .pytest_cache
	rm -rf build/
	rm -rf dist/

lint: ## Run linting
	flake8 app/ tests/
	black --check app/ tests/
	isort --check-only app/ tests/

format: ## Format code
	black app/ tests/
	isort app/ tests/

docker-build: ## Build Docker image
	docker build -t brronson .

docker-run: ## Run Docker container
	docker run -p 1968:1968 brronson

docker-test: ## Run tests in Docker
	docker build -t brronson .
	docker run --rm brronson pytest

docker-compose-up: ## Start services with docker-compose
	docker-compose up -d

docker-compose-down: ## Stop services with docker-compose
	docker-compose down

docker-compose-logs: ## View docker-compose logs
	docker-compose logs -f

install-dev: ## Install development dependencies
	pip install -r requirements-dev.txt

install-pre-commit: ## Install pre-commit hooks
	pre-commit install

run-pre-commit: ## Run pre-commit on all files
	pre-commit run --all-files

setup-dev: install-dev install-pre-commit ## Setup development environment

test-coverage: ## Run tests with coverage
	pytest --cov=app --cov-report=html --cov-report=term-missing

test-watch: ## Run tests in watch mode
	pytest-watch

clean-logs: ## Clean log files
	rm -f *.log
	rm -rf logs/

clean-docker: ## Clean Docker images and containers
	docker system prune -f
	docker image prune -f

clean-all: clean clean-logs clean-docker ## Clean everything

help-docker: ## Show Docker-related commands
	@echo "Docker commands:"
	@echo "  docker-build      - Build Docker image"
	@echo "  docker-run        - Run Docker container"
	@echo "  docker-test       - Run tests in Docker"
	@echo "  docker-compose-up - Start services with docker-compose"
	@echo "  docker-compose-down - Stop services with docker-compose"
	@echo "  docker-compose-logs - View docker-compose logs"
	@echo "  clean-docker      - Clean Docker images and containers"
