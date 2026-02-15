#!/bin/bash
#
# Quick start script for transcription pipeline
# Helps with initial setup and testing
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo ""
    echo "========================================"
    echo "$1"
    echo "========================================"
    echo ""
}

print_status() {
    echo -e "${BLUE}[*]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

check_docker() {
    print_status "Checking Docker..."
    if ! command -v docker &> /dev/null; then
        print_error "Docker not found. Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose not found. Please install Docker Compose first."
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker daemon not running. Please start Docker."
        exit 1
    fi
    
    print_success "Docker is ready"
}

check_env() {
    print_status "Checking environment configuration..."
    
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            print_warning ".env file not found, copying from .env.example"
            cp .env.example .env
            print_warning "Please edit .env and add your API keys"
        else
            print_error ".env.example not found"
            exit 1
        fi
    fi
    
    # Source the .env file
    set -a
    source .env
    set +a
    
    # Check if keys are set (not the placeholder values)
    local keys_ok=true
    
    if [ -z "$GROQ_API_KEY" ] || [ "$GROQ_API_KEY" = "your_groq_api_key_here" ]; then
        print_warning "GROQ_API_KEY not configured (required)"
        keys_ok=false
    else
        print_success "GROQ_API_KEY is set"
    fi
    
    if [ -z "$DEEPSEEK_API_KEY" ] || [ "$DEEPSEEK_API_KEY" = "your_deepseek_api_key_here" ]; then
        print_warning "DEEPSEEK_API_KEY not configured (optional but recommended)"
    else
        print_success "DEEPSEEK_API_KEY is set"
    fi
    
    if [ -z "$HUGGINGFACE_TOKEN" ] || [ "$HUGGINGFACE_TOKEN" = "your_huggingface_token_here" ]; then
        print_warning "HUGGINGFACE_TOKEN not configured (optional, for speaker diarization)"
    else
        print_success "HUGGINGFACE_TOKEN is set"
    fi
    
    if [ "$keys_ok" = false ]; then
        echo ""
        print_error "Required API keys are missing!"
        echo ""
        echo "Please get your API keys from:"
        echo "  - Groq: https://console.groq.com/keys"
        echo "  - DeepSeek: https://platform.deepseek.com/"
        echo "  - HuggingFace: https://huggingface.co/settings/tokens"
        echo ""
        echo "Then edit .env and add them."
        echo ""
        return 1
    fi
    
    return 0
}

start_services() {
    print_header "Starting Services"
    
    print_status "Building and starting containers..."
    docker-compose up -d --build
    
    # Wait for services to be healthy
    print_status "Waiting for services to be ready..."
    sleep 5
    
    local retries=0
    while [ $retries -lt 10 ]; do
        if docker ps | grep -q "transcription-pipeline.*healthy"; then
            print_success "Services are running"
            return 0
        fi
        sleep 2
        retries=$((retries + 1))
    done
    
    print_warning "Services may still be starting..."
    return 0
}

run_tests() {
    print_header "Running Tests"
    
    print_status "Running component tests..."
    
    # Copy tests to container
    docker exec -u root transcription-pipeline mkdir -p /app/tests 2>/dev/null || true
    docker cp tests/test_e2e_mock.py transcription-pipeline:/app/tests/ 2>/dev/null || true
    
    # Run tests
    if docker exec -e PYTHONPATH=/app/src transcription-pipeline \
        python /app/tests/test_e2e_mock.py; then
        print_success "All tests passed"
    else
        print_error "Some tests failed"
        return 1
    fi
}

check_health() {
    print_header "Health Check"
    
    if command -v python3 &> /dev/null; then
        python3 check_services.py
    else
        print_warning "Python3 not available, skipping health check"
        echo "Check API status with: curl http://localhost:8888/health"
    fi
}

show_usage() {
    print_header "Transcription Pipeline is Ready!"
    
    echo "Place audio files in the appropriate directories:"
    echo ""
    echo "  uploads/meeting/       - Meeting recordings"
    echo "  uploads/supervision/   - Clinical supervision"
    echo "  uploads/client/        - Client sessions"
    echo "  uploads/lecture/       - Lectures"
    echo "  uploads/braindump/     - Voice notes"
    echo ""
    echo "Supported formats: .mp3, .wav, .m4a, .ogg, .flac"
    echo "Max file size: 25MB (Groq limit)"
    echo ""
    echo "Useful commands:"
    echo "  docker-compose logs -f worker    # Watch processing logs"
    echo "  docker-compose ps                # Check service status"
    echo "  docker-compose down              # Stop all services"
    echo ""
    echo "Outputs will be saved to:"
    echo "  outputs/transcripts/    - Markdown files"
    echo "  outputs/docs/           - Word documents"
    echo ""
}

# Main menu
show_menu() {
    print_header "Transcription Pipeline - Quick Start"
    
    echo "What would you like to do?"
    echo ""
    echo "1) Full setup (check env, start services, run tests)"
    echo "2) Start services only"
    echo "3) Run tests only"
    echo "4) Health check"
    echo "5) Stop services"
    echo "6) View logs"
    echo "q) Quit"
    echo ""
}

main() {
    # If argument provided, run that action directly
    case "${1:-}" in
        setup)
            check_docker
            if check_env; then
                start_services
                run_tests
                check_health
                show_usage
            else
                start_services
                print_warning "Services started but API keys are missing"
                print_warning "Add your keys to .env and restart"
            fi
            exit 0
            ;;
        start)
            check_docker
            start_services
            show_usage
            exit 0
            ;;
        test)
            run_tests
            exit 0
            ;;
        health)
            check_health
            exit 0
            ;;
        stop)
            docker-compose down
            print_success "Services stopped"
            exit 0
            ;;
        logs)
            docker-compose logs -f worker
            exit 0
            ;;
    esac
    
    # Interactive menu
    while true; do
        show_menu
        read -p "Enter choice [1-6 or q]: " choice
        
        case $choice in
            1)
                check_docker
                if check_env; then
                    start_services
                    run_tests
                    check_health
                    show_usage
                else
                    read -p "Start services anyway? (y/n) " -n 1 -r
                    echo
                    if [[ $REPLY =~ ^[Yy]$ ]]; then
                        start_services
                    fi
                fi
                ;;
            2)
                check_docker
                start_services
                show_usage
                ;;
            3)
                run_tests
                ;;
            4)
                check_health
                ;;
            5)
                docker-compose down
                print_success "Services stopped"
                ;;
            6)
                docker-compose logs -f worker
                ;;
            q|Q)
                echo "Goodbye!"
                exit 0
                ;;
            *)
                print_error "Invalid choice"
                ;;
        esac
        
        echo ""
        read -p "Press Enter to continue..."
    done
}

main "$@"
