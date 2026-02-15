#!/bin/bash

# =============================================================================
# Transcription Pipeline Deployment Script
# =============================================================================
# This script automates the deployment of the transcription pipeline.
# It checks prerequisites, creates necessary directories, sets up configuration,
# and starts the services.
# =============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"
CONFIG_DIR="${PROJECT_DIR}/config"
UPLOADS_DIR="${PROJECT_DIR}/uploads"
OUTPUT_DIR="${PROJECT_DIR}/output"
LOGS_DIR="${PROJECT_DIR}/logs"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if a command exists
command_exists() {
    command -v "$1" &> /dev/null
}

# Check Docker version
check_docker_version() {
    local version
    version=$(docker --version | grep -oE '[0-9]+\.[0-9]+' | head -1)
    local major
    major=$(echo "$version" | cut -d. -f1)
    local minor
    minor=$(echo "$version" | cut -d. -f2)
    
    if [ "$major" -lt 20 ] || ([ "$major" -eq 20 ] && [ "$minor" -lt 10 ]); then
        log_error "Docker version $version is too old. Please upgrade to 20.10 or later."
        exit 1
    fi
    log_success "Docker version $version is compatible"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command_exists docker; then
        log_error "Docker is not installed. Please install Docker first."
        log_info "Visit: https://docs.docker.com/engine/install/"
        exit 1
    fi
    log_success "Docker is installed"
    
    # Check Docker version
    check_docker_version
    
    # Check Docker Compose
    if command_exists docker-compose; then
        DOCKER_COMPOSE="docker-compose"
        log_success "Docker Compose is installed (standalone)"
    elif docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
        log_success "Docker Compose is installed (plugin)"
    else
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        log_info "Visit: https://docs.docker.com/compose/install/"
        exit 1
    fi
    
    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running. Please start Docker first."
        exit 1
    fi
    log_success "Docker daemon is running"
    
    # Check available disk space (require at least 5GB)
    local available_space
    available_space=$(df -BG "$PROJECT_DIR" | awk 'NR==2 {print $4}' | sed 's/G//')
    if [ "$available_space" -lt 5 ]; then
        log_warning "Low disk space: ${available_space}GB available. At least 5GB recommended."
    else
        log_success "Disk space check passed: ${available_space}GB available"
    fi
    
    export DOCKER_COMPOSE
}

# Create directory structure
create_directories() {
    log_info "Creating directory structure..."
    
    local dirs=("$CONFIG_DIR" "$UPLOADS_DIR" "$OUTPUT_DIR" "$LOGS_DIR")
    
    for dir in "${dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            log_success "Created directory: $dir"
        else
            log_info "Directory already exists: $dir"
        fi
    done
    
    # Set appropriate permissions
    chmod 755 "$UPLOADS_DIR" "$OUTPUT_DIR" "$LOGS_DIR"
    log_success "Directory permissions set"
}

# Copy configuration templates
copy_config_templates() {
    log_info "Setting up configuration..."
    
    local template_file="${CONFIG_DIR}/config.yaml.template"
    local config_file="${CONFIG_DIR}/config.yaml"
    
    if [ ! -f "$config_file" ]; then
        if [ -f "$template_file" ]; then
            cp "$template_file" "$config_file"
            log_success "Created config.yaml from template"
            log_warning "Please review and edit ${config_file} before starting the services"
        else
            log_error "Template file not found: $template_file"
            exit 1
        fi
    else
        log_info "Configuration file already exists: $config_file"
    fi
}

# Create docker-compose.yml if it doesn't exist
create_compose_file() {
    log_info "Checking Docker Compose configuration..."
    
    if [ -f "$COMPOSE_FILE" ]; then
        log_info "Docker Compose file already exists"
        return 0
    fi
    
    log_info "Creating docker-compose.yml..."
    
    cat > "$COMPOSE_FILE" << 'EOF'
version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    image: transcription-pipeline:latest
    container_name: transcription-pipeline
    ports:
      - "${API_PORT:-8000}:8000"
    volumes:
      - ./uploads:/app/uploads
      - ./output:/app/output
      - ./logs:/app/logs
      - ./config:/app/config:ro
    environment:
      - API_KEY=${API_KEY:-change-me-in-production}
      - REDIS_HOST=redis
      - REDIS_PASSWORD=${REDIS_PASSWORD:-}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - TRANSCRIPTION_ENGINE=${TRANSCRIPTION_ENGINE:-whisper}
    depends_on:
      - redis
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  redis:
    image: redis:7-alpine
    container_name: transcription-redis
    volumes:
      - redis_data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  worker:
    build:
      context: .
      dockerfile: Dockerfile
    image: transcription-pipeline:latest
    container_name: transcription-worker
    command: python -m src.worker
    volumes:
      - ./uploads:/app/uploads
      - ./output:/app/output
      - ./logs:/app/logs
      - ./config:/app/config:ro
    environment:
      - REDIS_HOST=redis
      - REDIS_PASSWORD=${REDIS_PASSWORD:-}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - TRANSCRIPTION_ENGINE=${TRANSCRIPTION_ENGINE:-whisper}
      - WORKER_CONCURRENCY=${WORKER_CONCURRENCY:-4}
    depends_on:
      - redis
    restart: unless-stopped
    deploy:
      replicas: ${WORKER_REPLICAS:-2}

volumes:
  redis_data:
EOF

    log_success "Created docker-compose.yml"
}

# Create .env file if it doesn't exist
create_env_file() {
    local env_file="${PROJECT_DIR}/.env"
    
    if [ -f "$env_file" ]; then
        log_info ".env file already exists"
        return 0
    fi
    
    log_info "Creating .env file..."
    
    cat > "$env_file" << 'EOF'
# Transcription Pipeline Environment Configuration
# Copy this file to .env and customize for your environment

# API Configuration
API_PORT=8000
API_KEY=your-secure-api-key-here

# Logging
LOG_LEVEL=INFO

# Transcription Engine
TRANSCRIPTION_ENGINE=whisper

# Redis Configuration
REDIS_PASSWORD=

# Worker Configuration
WORKER_CONCURRENCY=4
WORKER_REPLICAS=2

# Optional: Cloud Provider Credentials (uncomment if needed)
# AWS_ACCESS_KEY_ID=
# AWS_SECRET_ACCESS_KEY=
# AWS_REGION=us-east-1
# GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/google.json
# AZURE_SPEECH_KEY=
# AZURE_SPEECH_REGION=

# Optional: Storage (uncomment if needed)
# S3_BUCKET=
# S3_REGION=
# S3_ACCESS_KEY_ID=
# S3_SECRET_ACCESS_KEY=

# Optional: Notifications (uncomment if needed)
# WEBHOOK_URL=
# WEBHOOK_SECRET=
EOF

    log_success "Created .env file"
    log_warning "Please edit .env file and set secure values for API_KEY and other credentials"
}

# Build Docker images
build_images() {
    log_info "Building Docker images..."
    
    cd "$PROJECT_DIR"
    
    if ! $DOCKER_COMPOSE build; then
        log_error "Failed to build Docker images"
        exit 1
    fi
    
    log_success "Docker images built successfully"
}

# Start services
start_services() {
    log_info "Starting services..."
    
    cd "$PROJECT_DIR"
    
    # Pull latest images if using pre-built images
    log_info "Pulling latest images..."
    $DOCKER_COMPOSE pull || true
    
    # Start services
    if ! $DOCKER_COMPOSE up -d; then
        log_error "Failed to start services"
        exit 1
    fi
    
    log_success "Services started successfully"
    
    # Wait for services to be healthy
    log_info "Waiting for services to be healthy..."
    sleep 5
    
    local retries=0
    local max_retries=30
    
    while [ $retries -lt $max_retries ]; do
        if $DOCKER_COMPOSE ps | grep -q "healthy"; then
            log_success "Services are healthy!"
            break
        fi
        
        retries=$((retries + 1))
        if [ $retries -eq $max_retries ]; then
            log_warning "Services may not be fully ready yet. Check logs with: docker-compose logs -f"
            break
        fi
        
        echo -n "."
        sleep 2
    done
}

# Display status
show_status() {
    log_info "Deployment Status:"
    echo ""
    
    cd "$PROJECT_DIR"
    $DOCKER_COMPOSE ps
    
    echo ""
    log_info "Service URLs:"
    echo "  API: http://localhost:${API_PORT:-8000}"
    echo "  Health Check: http://localhost:${API_PORT:-8000}/health"
    
    echo ""
    log_info "Useful Commands:"
    echo "  View logs:    make logs"
    echo "  Stop:         make down"
    echo "  Restart:      make restart"
    echo "  Shell:        make shell"
    echo "  Test:         make test"
}

# Cleanup function
cleanup() {
    log_info "Cleaning up..."
    # Add any cleanup tasks here
}

# Main deployment function
main() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║       Transcription Pipeline Deployment Script             ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
    
    # Set trap for cleanup
    trap cleanup EXIT
    
    # Run deployment steps
    check_prerequisites
    create_directories
    copy_config_templates
    create_compose_file
    create_env_file
    
    # Ask user if they want to build and start
    echo ""
    read -p "Do you want to build Docker images and start services? [Y/n]: " -n 1 -r
    echo ""
    
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        build_images
        start_services
        show_status
    else
        log_info "Skipping build and start. You can start services later with: make up"
    fi
    
    echo ""
    log_success "Deployment preparation complete!"
    echo ""
}

# Show help
show_help() {
    echo "Transcription Pipeline Deployment Script"
    echo ""
    echo "Usage: $0 [OPTION]"
    echo ""
    echo "Options:"
    echo "  --help, -h      Show this help message"
    echo "  --check-only    Only check prerequisites, don't deploy"
    echo "  --setup-only    Only setup directories and config, don't build/start"
    echo ""
    echo "Environment Variables:"
    echo "  API_KEY         API authentication key"
    echo "  API_PORT        Port for the API server (default: 8000)"
    echo "  LOG_LEVEL       Logging level (default: INFO)"
    echo ""
}

# Parse arguments
case "${1:-}" in
    --help|-h)
        show_help
        exit 0
        ;;
    --check-only)
        check_prerequisites
        exit 0
        ;;
    --setup-only)
        check_prerequisites
        create_directories
        copy_config_templates
        create_compose_file
        create_env_file
        log_success "Setup complete! Edit .env and config/config.yaml before starting."
        exit 0
        ;;
    "")
        main
        ;;
    *)
        log_error "Unknown option: $1"
        show_help
        exit 1
        ;;
esac
