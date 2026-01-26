#!/usr/bin/env bash
#
# Concordance Service Runner
# ==========================
# Start, stop, and manage Concordance services
#

set -e

# ============================================================================
# Colors and Formatting
# ============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color
BOLD='\033[1m'
DIM='\033[2m'

# ============================================================================
# Configuration
# ============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$SCRIPT_DIR/.pids"
LOG_DIR="$SCRIPT_DIR/.logs"

# Default ports (can be overridden by .env files)
BACKEND_PORT=${BACKEND_PORT:-6767}
ENGINE_PORT=${ENGINE_PORT:-8000}
FRONTEND_PORT=${FRONTEND_PORT:-3000}

# ============================================================================
# Helper Functions
# ============================================================================
print_banner() {
    printf "\n"
    printf "${MAGENTA}${BOLD}Concordance Service Runner${NC}\n"
    printf "${GRAY}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
    printf "\n"
}

print_success() {
    printf "${GREEN}✓${NC} %s\n" "$1"
}

print_error() {
    printf "${RED}✗${NC} %s\n" "$1"
}

print_warning() {
    printf "${YELLOW}⚠${NC} %s\n" "$1"
}

print_info() {
    printf "${BLUE}ℹ${NC} %s\n" "$1"
}

print_step() {
    printf "${MAGENTA}➤${NC} %s\n" "$1"
}

ensure_dirs() {
    mkdir -p "$PID_DIR"
    mkdir -p "$LOG_DIR"
}

# Check if a process is running
is_running() {
    local pid_file="$1"
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# Get PID from file
get_pid() {
    local pid_file="$1"
    if [ -f "$pid_file" ]; then
        cat "$pid_file"
    fi
}

# Wait for a service to be healthy
wait_for_health() {
    local url="$1"
    local name="$2"
    local max_attempts="${3:-30}"
    local attempt=1

    printf "${GRAY}  Waiting for %s to be ready...${NC}" "$name"

    while [ $attempt -le $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            printf " ${GREEN}ready!${NC}\n"
            return 0
        fi
        printf "."
        sleep 1
        ((attempt++))
    done

    printf " ${RED}timeout${NC}\n"
    return 1
}

# ============================================================================
# Database Migrations
# ============================================================================
run_migrations() {
    print_step "Running database migrations..."

    # Check if .env exists
    if [ ! -f "$SCRIPT_DIR/backend/.env" ]; then
        print_error "No backend/.env file found. Run ./setup.sh first."
        return 1
    fi

    # Check for psql
    if ! command -v psql > /dev/null 2>&1; then
        print_error "psql is not installed. Please install PostgreSQL client tools."
        print_info "On macOS: brew install postgresql"
        print_info "On Ubuntu/Debian: sudo apt install postgresql-client"
        return 1
    fi

    # Run migrations
    printf "${GRAY}"
    if (cd "$SCRIPT_DIR/backend" && ./run_migration.sh); then
        printf "${NC}"
        print_success "Database migrations completed!"
    else
        printf "${NC}"
        print_error "Migration failed. Please check your DATABASE_URL and try again."
        return 1
    fi
}

# ============================================================================
# Service: Backend
# ============================================================================
start_backend() {
    local pid_file="$PID_DIR/backend.pid"
    local log_file="$LOG_DIR/backend.log"

    if is_running "$pid_file"; then
        print_warning "Backend is already running (PID: $(get_pid "$pid_file"))"
        return 0
    fi

    print_step "Starting Backend (Thunder)..."

    # Check if .env exists
    if [ ! -f "$SCRIPT_DIR/backend/.env" ]; then
        print_warning "No backend/.env file found. Run ./setup.sh first."
        return 1
    fi

    # Check if migrations might be needed (look for a marker or just warn)
    print_info "Make sure database migrations have been run: cd backend && ./run_migration.sh"

    # Build if needed
    if [ ! -f "$SCRIPT_DIR/backend/target/release/thunder" ] && [ ! -f "$SCRIPT_DIR/backend/target/debug/thunder" ]; then
        print_info "Building backend..."
        (cd "$SCRIPT_DIR/backend" && cargo build --release) >> "$log_file" 2>&1
    fi

    # Start the service
    (cd "$SCRIPT_DIR/backend" && cargo run --release >> "$log_file" 2>&1) &
    local pid=$!
    echo "$pid" > "$pid_file"

    # Wait for health
    if wait_for_health "http://localhost:$BACKEND_PORT/healthz" "Backend" 60; then
        print_success "Backend started on port $BACKEND_PORT (PID: $pid)"
        print_info "Logs: $log_file"
    else
        print_error "Backend failed to start. Check logs: $log_file"
        return 1
    fi
}

stop_backend() {
    local pid_file="$PID_DIR/backend.pid"

    if ! is_running "$pid_file"; then
        print_info "Backend is not running"
        return 0
    fi

    local pid=$(get_pid "$pid_file")
    print_step "Stopping Backend (PID: $pid)..."

    kill "$pid" 2>/dev/null || true
    rm -f "$pid_file"

    print_success "Backend stopped"
}

# ============================================================================
# Service: Engine
# ============================================================================
start_engine() {
    local pid_file="$PID_DIR/engine.pid"
    local log_file="$LOG_DIR/engine.log"

    if is_running "$pid_file"; then
        print_warning "Engine is already running (PID: $(get_pid "$pid_file"))"
        return 0
    fi

    print_step "Starting Engine (Quote)..."

    # Check if .env exists
    if [ ! -f "$SCRIPT_DIR/engine/inference/.env" ]; then
        print_warning "No engine/inference/.env file found. Run ./setup.sh first."
    fi

    # Load environment
    if [ -f "$SCRIPT_DIR/engine/inference/.env" ]; then
        set -a
        source "$SCRIPT_DIR/engine/inference/.env"
        set +a
    fi

    # Also load from engine/.env if it exists
    if [ -f "$SCRIPT_DIR/engine/.env" ]; then
        set -a
        source "$SCRIPT_DIR/engine/.env"
        set +a
    fi

    local host="${HOST:-0.0.0.0}"
    local port="${PORT:-8000}"

    # Ensure dependencies are installed (inference package must be installed as editable)
    print_info "Checking engine dependencies..."
    if ! (cd "$SCRIPT_DIR/engine" && uv run python -c "import quote" 2>/dev/null); then
        print_info "Installing engine dependencies..."
        (cd "$SCRIPT_DIR/engine" && uv sync --all-packages && uv pip install -e inference) >> "$log_file" 2>&1
    fi

    # Start the service
    print_info "Starting inference server (this may take a few minutes on first run)..."
    (cd "$SCRIPT_DIR/engine" && uv run -m quote.server.openai.local --host "$host" --port "$port" >> "$log_file" 2>&1) &
    local pid=$!
    echo "$pid" > "$pid_file"

    # Wait for health (longer timeout for model loading)
    if wait_for_health "http://localhost:$port/v1/models" "Engine" 300; then
        print_success "Engine started on port $port (PID: $pid)"
        print_info "Logs: $log_file"
    else
        print_warning "Engine may still be loading the model. Check logs: $log_file"
        print_info "You can monitor progress with: tail -f $log_file"
    fi
}

stop_engine() {
    local pid_file="$PID_DIR/engine.pid"

    if ! is_running "$pid_file"; then
        print_info "Engine is not running"
        return 0
    fi

    local pid=$(get_pid "$pid_file")
    print_step "Stopping Engine (PID: $pid)..."

    kill "$pid" 2>/dev/null || true
    rm -f "$pid_file"

    print_success "Engine stopped"
}

# ============================================================================
# Service: Frontend
# ============================================================================
start_frontend() {
    local pid_file="$PID_DIR/frontend.pid"
    local log_file="$LOG_DIR/frontend.log"

    if is_running "$pid_file"; then
        print_warning "Frontend is already running (PID: $(get_pid "$pid_file"))"
        return 0
    fi

    print_step "Starting Frontend..."

    # Check if node_modules exists
    if [ ! -d "$SCRIPT_DIR/frontend/node_modules" ]; then
        print_info "Installing frontend dependencies..."
        (cd "$SCRIPT_DIR/frontend" && npm install) >> "$log_file" 2>&1
    fi

    # Start the service
    (cd "$SCRIPT_DIR/frontend" && npm run dev >> "$log_file" 2>&1) &
    local pid=$!
    echo "$pid" > "$pid_file"

    # Wait for health
    sleep 3
    if is_running "$pid_file"; then
        print_success "Frontend started on port $FRONTEND_PORT (PID: $pid)"
        print_info "Logs: $log_file"
        printf "${BLUE}ℹ${NC} Open: ${CYAN}http://localhost:%s${NC}\n" "$FRONTEND_PORT"
    else
        print_error "Frontend failed to start. Check logs: $log_file"
        return 1
    fi
}

stop_frontend() {
    local pid_file="$PID_DIR/frontend.pid"

    if ! is_running "$pid_file"; then
        print_info "Frontend is not running"
        return 0
    fi

    local pid=$(get_pid "$pid_file")
    print_step "Stopping Frontend (PID: $pid)..."

    # Kill the npm process and its children
    pkill -P "$pid" 2>/dev/null || true
    kill "$pid" 2>/dev/null || true
    rm -f "$pid_file"

    print_success "Frontend stopped"
}

# ============================================================================
# Aggregate Commands
# ============================================================================
start_all() {
    print_step "Starting all services..."
    printf "\n"
    start_backend
    printf "\n"
    start_engine
    printf "\n"
    start_frontend
    printf "\n"
    print_success "All services started!"
}

stop_all() {
    print_step "Stopping all services..."
    printf "\n"
    stop_frontend
    stop_engine
    stop_backend
    printf "\n"
    print_success "All services stopped!"
}

restart_all() {
    stop_all
    printf "\n"
    start_all
}

# ============================================================================
# Status
# ============================================================================
show_status() {
    printf "\n"
    printf "${WHITE}${BOLD}Service Status${NC}\n"
    printf "${GRAY}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
    printf "\n"

    # Backend
    local backend_pid_file="$PID_DIR/backend.pid"
    if is_running "$backend_pid_file"; then
        printf "  ${GREEN}●${NC} Backend    ${GREEN}running${NC} (PID: %s, port: %s)\n" "$(get_pid "$backend_pid_file")" "$BACKEND_PORT"
        if curl -s "http://localhost:$BACKEND_PORT/healthz" > /dev/null 2>&1; then
            printf "               ${DIM}Health: OK${NC}\n"
        else
            printf "               ${YELLOW}Health: Not responding${NC}\n"
        fi
    else
        printf "  ${RED}●${NC} Backend    ${DIM}stopped${NC}\n"
    fi

    # Engine
    local engine_pid_file="$PID_DIR/engine.pid"
    if is_running "$engine_pid_file"; then
        printf "  ${GREEN}●${NC} Engine     ${GREEN}running${NC} (PID: %s, port: %s)\n" "$(get_pid "$engine_pid_file")" "$ENGINE_PORT"
        if curl -s "http://localhost:$ENGINE_PORT/v1/models" > /dev/null 2>&1; then
            printf "               ${DIM}Health: OK${NC}\n"
        else
            printf "               ${YELLOW}Health: Loading model...${NC}\n"
        fi
    else
        printf "  ${RED}●${NC} Engine     ${DIM}stopped${NC}\n"
    fi

    # Frontend
    local frontend_pid_file="$PID_DIR/frontend.pid"
    if is_running "$frontend_pid_file"; then
        printf "  ${GREEN}●${NC} Frontend   ${GREEN}running${NC} (PID: %s, port: %s)\n" "$(get_pid "$frontend_pid_file")" "$FRONTEND_PORT"
    else
        printf "  ${RED}●${NC} Frontend   ${DIM}stopped${NC}\n"
    fi

    printf "\n"
}

# ============================================================================
# Logs
# ============================================================================
show_logs() {
    local service="$1"
    local log_file=""

    case "$service" in
        backend)
            log_file="$LOG_DIR/backend.log"
            ;;
        engine)
            log_file="$LOG_DIR/engine.log"
            ;;
        frontend)
            log_file="$LOG_DIR/frontend.log"
            ;;
        *)
            print_error "Unknown service: $service"
            printf "Usage: %s logs <backend|engine|frontend>\n" "$0"
            exit 1
            ;;
    esac

    if [ -f "$log_file" ]; then
        tail -f "$log_file"
    else
        print_error "Log file not found: $log_file"
        exit 1
    fi
}

# ============================================================================
# Help
# ============================================================================
show_help() {
    printf "Concordance Service Runner\n"
    printf "\n"
    printf "Usage: %s <command> [service]\n" "$0"
    printf "\n"
    printf "Commands:\n"
    printf "  start [service]    Start services (default: all)\n"
    printf "  stop [service]     Stop services (default: all)\n"
    printf "  restart [service]  Restart services (default: all)\n"
    printf "  status             Show status of all services\n"
    printf "  logs <service>     Follow logs for a service\n"
    printf "  migrate            Run database migrations\n"
    printf "  help               Show this help message\n"
    printf "\n"
    printf "Services:\n"
    printf "  all                All services (default)\n"
    printf "  backend            Backend (Thunder) - Rust observability service\n"
    printf "  engine             Engine (Quote) - Python inference server\n"
    printf "  frontend           Frontend - React web UI\n"
    printf "\n"
    printf "Examples:\n"
    printf "  %s start           Start all services\n" "$0"
    printf "  %s start backend   Start only the backend\n" "$0"
    printf "  %s stop            Stop all services\n" "$0"
    printf "  %s status          Check status of all services\n" "$0"
    printf "  %s logs engine     Follow engine logs\n" "$0"
    printf "  %s migrate         Run database migrations\n" "$0"
    printf "\n"
}

# ============================================================================
# Main
# ============================================================================
main() {
    ensure_dirs

    local command="${1:-help}"
    local service="${2:-all}"

    case "$command" in
        start)
            print_banner
            case "$service" in
                all) start_all ;;
                backend) start_backend ;;
                engine) start_engine ;;
                frontend) start_frontend ;;
                *) print_error "Unknown service: $service"; exit 1 ;;
            esac
            ;;
        stop)
            print_banner
            case "$service" in
                all) stop_all ;;
                backend) stop_backend ;;
                engine) stop_engine ;;
                frontend) stop_frontend ;;
                *) print_error "Unknown service: $service"; exit 1 ;;
            esac
            ;;
        restart)
            print_banner
            case "$service" in
                all) restart_all ;;
                backend) stop_backend; printf "\n"; start_backend ;;
                engine) stop_engine; printf "\n"; start_engine ;;
                frontend) stop_frontend; printf "\n"; start_frontend ;;
                *) print_error "Unknown service: $service"; exit 1 ;;
            esac
            ;;
        status)
            print_banner
            show_status
            ;;
        migrate)
            print_banner
            run_migrations
            ;;
        logs)
            if [ -z "$2" ]; then
                print_error "Please specify a service: backend, engine, or frontend"
                exit 1
            fi
            show_logs "$2"
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "Unknown command: $command"
            printf "\n"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
