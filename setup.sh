#!/usr/bin/env bash
#
# Concordance Interactive Setup Script
# =====================================
# This script helps you configure and set up all components of Concordance:
# - Backend (Thunder) - Rust observability service
# - Engine (Quote) - Python inference server
# - Frontend - React web UI
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
# Helper Functions
# ============================================================================
print_banner() {
    printf "\n"
    printf "${MAGENTA}${BOLD}"
    printf "   ____                              _                      \n"
    printf "  / ___|___  _ __   ___ ___  _ __ __| | __ _ _ __   ___ ___ \n"
    printf " | |   / _ \| '_ \ / __/ _ \| '__/ _\` |/ _\` | '_ \ / __/ _ \\\\\n"
    printf " | |__| (_) | | | | (_| (_) | | | (_| | (_| | | | | (_|  __/\n"
    printf "  \____\___/|_| |_|\___\___/|_|  \__,_|\__,_|_| |_|\___\___|\n"
    printf "${NC}\n"
    printf "${CYAN}         Observe, Modify, and Control LLM Generation${NC}\n"
    printf "\n"
}

print_header() {
    printf "\n"
    printf "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
    printf "${WHITE}${BOLD}  %s${NC}\n" "$1"
    printf "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
    printf "\n"
}

print_subheader() {
    printf "\n"
    printf "${CYAN}▸ %s${NC}\n" "$1"
    printf "${GRAY}────────────────────────────────────────────────────────────${NC}\n"
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

# Prompt for input with a default value
prompt_with_default() {
    local prompt="$1"
    local default="$2"
    local var_name="$3"
    local is_secret="${4:-false}"

    if [ "$is_secret" = "true" ]; then
        printf "${WHITE}%s${NC}" "$prompt"
        if [ -n "$default" ]; then
            printf " ${DIM}[****hidden****]${NC}"
        fi
        printf ": "
        read -s input
        printf "\n"
    else
        printf "${WHITE}%s${NC}" "$prompt"
        if [ -n "$default" ]; then
            printf " ${DIM}[%s]${NC}" "$default"
        fi
        printf ": "
        read input
    fi

    if [ -z "$input" ]; then
        eval "$var_name='$default'"
    else
        eval "$var_name='$input'"
    fi
}

# Yes/No prompt
confirm() {
    local prompt="$1"
    local default="${2:-y}"

    if [ "$default" = "y" ]; then
        printf "${WHITE}%s${NC} ${DIM}[Y/n]${NC}: " "$prompt"
    else
        printf "${WHITE}%s${NC} ${DIM}[y/N]${NC}: " "$prompt"
    fi

    read response
    response=${response:-$default}

    case "$response" in
        [yY][eE][sS]|[yY]) return 0 ;;
        *) return 1 ;;
    esac
}

# Check if a command exists
command_exists() {
    command -v "$1" &> /dev/null
}

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ============================================================================
# Prerequisites Check
# ============================================================================
check_prerequisites() {
    print_header "Checking Prerequisites"

    local missing_required=()
    local missing_optional=()

    # Required: uv (Python package manager)
    print_step "Checking for uv (Python package manager)..."
    if command_exists uv; then
        print_success "uv is installed ($(uv --version 2>/dev/null | head -1))"
    else
        print_error "uv is not installed"
        missing_required+=("uv")
    fi

    # Required: Rust toolchain
    print_step "Checking for Rust toolchain..."
    if command_exists cargo; then
        print_success "Rust is installed ($(rustc --version 2>/dev/null))"
    else
        print_error "Rust is not installed"
        missing_required+=("rust")
    fi

    # Required: Node.js
    print_step "Checking for Node.js..."
    if command_exists node; then
        local node_version=$(node --version 2>/dev/null | sed 's/v//')
        local node_major=$(echo "$node_version" | cut -d. -f1)
        if [ "$node_major" -ge 18 ]; then
            print_success "Node.js is installed (v$node_version)"
        else
            print_warning "Node.js version $node_version found, but 18+ is recommended"
        fi
    else
        print_error "Node.js is not installed"
        missing_required+=("node")
    fi

    # Required: npm
    print_step "Checking for npm..."
    if command_exists npm; then
        print_success "npm is installed ($(npm --version 2>/dev/null))"
    else
        print_error "npm is not installed"
        missing_required+=("npm")
    fi

    # Optional: Docker
    print_step "Checking for Docker (optional)..."
    if command_exists docker; then
        print_success "Docker is installed ($(docker --version 2>/dev/null | cut -d' ' -f3 | tr -d ','))"
    else
        print_warning "Docker is not installed (optional, needed for containerized deployment)"
        missing_optional+=("docker")
    fi

    # Optional: Modal CLI
    print_step "Checking for Modal CLI (optional)..."
    if command_exists modal; then
        print_success "Modal CLI is installed"
    else
        print_warning "Modal CLI is not installed (optional, needed for GPU deployment)"
        missing_optional+=("modal")
    fi

    printf "\n"

    # Handle missing required dependencies
    if [ ${#missing_required[@]} -gt 0 ]; then
        print_warning "Missing required dependencies: ${missing_required[*]}"
        printf "\n"

        if confirm "Would you like help installing missing dependencies?"; then
            install_dependencies "${missing_required[@]}"
        else
            print_error "Please install missing dependencies and run this script again."
            exit 1
        fi
    fi

    print_success "All required prerequisites are installed!"
}

# ============================================================================
# Dependency Installation
# ============================================================================
install_dependencies() {
    local deps=("$@")

    print_subheader "Installing Dependencies"

    for dep in "${deps[@]}"; do
        case "$dep" in
            uv)
                print_step "Installing uv..."
                printf "${GRAY}"
                if [[ "$OSTYPE" == "darwin"* ]] || [[ "$OSTYPE" == "linux-gnu"* ]]; then
                    curl -LsSf https://astral.sh/uv/install.sh | sh
                    # Source the updated PATH
                    export PATH="$HOME/.local/bin:$PATH"
                else
                    print_error "Please install uv manually: https://docs.astral.sh/uv/getting-started/installation/"
                fi
                printf "${NC}"
                ;;
            rust)
                print_step "Installing Rust via rustup..."
                printf "${GRAY}"
                curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
                source "$HOME/.cargo/env"
                printf "${NC}"
                ;;
            node)
                print_step "Installing Node.js..."
                printf "${GRAY}"
                if [[ "$OSTYPE" == "darwin"* ]]; then
                    if command_exists brew; then
                        brew install node
                    else
                        print_error "Please install Node.js manually: https://nodejs.org/"
                    fi
                elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
                    # Try to use the NodeSource repository
                    print_info "Please install Node.js 20+ from https://nodejs.org/"
                fi
                printf "${NC}"
                ;;
        esac
    done
}

# ============================================================================
# Backend Setup
# ============================================================================
setup_backend() {
    print_header "Backend (Thunder) Setup"

    local backend_dir="$SCRIPT_DIR/backend"
    local env_file="$backend_dir/.env"

    print_info "The backend requires a PostgreSQL database."
    print_info "We recommend Neon (https://neon.tech) for a free, serverless Postgres."
    printf "\n"

    # Database URL
    print_subheader "Database Configuration"
    printf "${DIM}Format: postgresql://user:password@host/database?sslmode=require${NC}\n"
    printf "${DIM}Example: postgresql://user:pass@ep-xxx.region.aws.neon.tech/dbname?sslmode=require${NC}\n"
    printf "\n"

    local db_url=""
    prompt_with_default "PostgreSQL connection string" "" "db_url" "true"

    if [ -z "$db_url" ]; then
        print_warning "No database URL provided. You'll need to set DATABASE_URL later."
        db_url="postgresql://user:password@localhost:5432/concordance"
    fi

    # Server configuration
    print_subheader "Server Configuration"

    local app_host=""
    local app_port=""
    prompt_with_default "Host to bind to" "127.0.0.1" "app_host"
    prompt_with_default "Port to bind to" "6767" "app_port"

    # Bootstrap secret for admin key creation
    print_subheader "Security Configuration"
    printf "${DIM}The bootstrap secret is used to create the initial admin API key.${NC}\n"
    printf "${DIM}Leave empty to disable bootstrap endpoint (recommended for production).${NC}\n"
    printf "\n"

    local bootstrap_secret=""
    prompt_with_default "Bootstrap secret (optional)" "" "bootstrap_secret" "true"

    # Playground configuration (optional)
    print_subheader "Playground Configuration (Optional)"
    printf "${DIM}The playground feature allows users to test mods in a web interface.${NC}\n"
    printf "${DIM}Skip these if you're not using the playground feature.${NC}\n"
    printf "\n"

    local playground_admin_key=""
    local playground_llama_70b_url=""
    local playground_qwen_14b_url=""
    local playground_llama_8b_url=""

    if confirm "Would you like to configure the playground feature?" "n"; then
        prompt_with_default "Playground admin key" "" "playground_admin_key" "true"
        printf "\n"
        printf "${DIM}Enter Modal deployment URLs for model servers (leave empty to skip):${NC}\n"
        prompt_with_default "Llama 70B URL" "" "playground_llama_70b_url"
        prompt_with_default "Qwen 14B URL" "" "playground_qwen_14b_url"
        prompt_with_default "Llama 8B URL" "" "playground_llama_8b_url"
    fi

    # Write .env file
    print_step "Writing backend/.env file..."
    cat > "$env_file" << EOF
# Concordance Backend Configuration
# Generated by setup.sh on $(date)

# Server configuration
APP_HOST=$app_host
APP_PORT=$app_port

# Database connection
DATABASE_URL=$db_url

# Logging (debug, info, warn, error)
RUST_LOG=info

# Bootstrap secret for creating initial admin API key
# Remove or leave empty in production after initial setup
BOOTSTRAP_SECRET=$bootstrap_secret

# Playground configuration (optional - only needed if using the playground feature)
# Admin key for adding users to model servers
PLAYGROUND_ADMIN_KEY=$playground_admin_key

# Model server endpoints - configure these to point to your inference deployments
# See engine/inference/README.md for inference deployment instructions
PLAYGROUND_LLAMA_70B_URL=$playground_llama_70b_url
PLAYGROUND_QWEN_14B_URL=$playground_qwen_14b_url
PLAYGROUND_LLAMA_8B_URL=$playground_llama_8b_url
EOF

    print_success "Backend configuration saved to backend/.env"

    # Ask about running migrations
    printf "\n"
    print_subheader "Database Migrations"
    printf "${DIM}The backend requires database tables to be created via migrations.${NC}\n"
    printf "${DIM}This requires 'psql' (PostgreSQL client) to be installed.${NC}\n"
    printf "\n"

    if confirm "Would you like to run database migrations now?"; then
        # Check for psql
        if ! command_exists psql; then
            print_warning "psql is not installed. Please install PostgreSQL client tools."
            print_info "On macOS: brew install postgresql"
            print_info "On Ubuntu/Debian: sudo apt install postgresql-client"
            print_info "You can run migrations later with: cd backend && ./run_migration.sh"
        else
            print_step "Running database migrations..."
            printf "${GRAY}"
            if (cd "$backend_dir" && ./run_migration.sh); then
                printf "${NC}"
                print_success "Database migrations completed!"
            else
                printf "${NC}"
                print_error "Migration failed. Please check your DATABASE_URL and try again."
                print_info "You can run migrations manually with: cd backend && ./run_migration.sh"
            fi
        fi
    else
        print_info "You can run migrations later with: cd backend && ./run_migration.sh"
    fi

    # Ask about building
    printf "\n"
    if confirm "Would you like to build the backend now?"; then
        print_step "Building backend..."
        printf "${GRAY}"
        (cd "$backend_dir" && cargo build --release)
        printf "${NC}"
        print_success "Backend built successfully!"
    fi
}

# ============================================================================
# Engine Setup
# ============================================================================
setup_engine() {
    print_header "Engine (Quote) Setup"

    local engine_dir="$SCRIPT_DIR/engine/inference"
    local env_file="$engine_dir/.env"

    print_info "The engine runs LLM inference and requires a Hugging Face token."
    print_info "Get your token at: https://huggingface.co/settings/tokens"
    printf "\n"

    # Hugging Face Token
    print_subheader "Hugging Face Configuration"

    local hf_token=""
    prompt_with_default "Hugging Face token (hf_...)" "" "hf_token" "true"

    if [ -z "$hf_token" ]; then
        print_warning "No HF token provided. You may not be able to download gated models."
    fi

    # Admin Key
    print_subheader "Admin Configuration"
    printf "${DIM}The admin key is used for authenticating admin operations.${NC}\n"
    printf "\n"

    local admin_key=""
    prompt_with_default "Admin key" "" "admin_key" "true"

    # Deployment mode
    print_subheader "Deployment Mode"
    printf "${DIM}Choose your deployment mode to set appropriate paths for users and mods.${NC}\n"
    printf "${DIM}  • Local: Uses ./users/users.json and ./mods${NC}\n"
    printf "${DIM}  • Remote (Modal): Uses /users/users.json and /mods${NC}\n"
    printf "\n"

    local users_path=""
    local mods_base=""
    if confirm "Are you deploying to Modal (remote)?" "n"; then
        users_path="/users/users.json"
        mods_base="/mods"
        print_info "Using remote paths: USERS_PATH=$users_path, MODS_BASE=$mods_base"
    else
        users_path="./users/users.json"
        mods_base="./mods"
        print_info "Using local paths: USERS_PATH=$users_path, MODS_BASE=$mods_base"
    fi

    # Model configuration
    print_subheader "Model Configuration"
    printf "${DIM}Available models:${NC}\n"
    printf "${DIM}  • modularai/Llama-3.1-8B-Instruct-GGUF (default)${NC}\n"
    printf "${DIM}  • Any Hugging Face model compatible with MAX${NC}\n"
    printf "\n"

    local model_id=""
    prompt_with_default "Model ID" "modularai/Llama-3.1-8B-Instruct-GGUF" "model_id"

    # Server configuration
    print_subheader "Server Configuration"

    local engine_host=""
    local engine_port=""
    prompt_with_default "Host to bind to" "0.0.0.0" "engine_host"
    prompt_with_default "Port to bind to" "8000" "engine_port"

    # Backend integration
    print_subheader "Backend Integration"
    printf "${DIM}The engine can send inference logs to the backend for observability.${NC}\n"
    printf "\n"

    local log_ingest_url=""
    prompt_with_default "Backend ingest URL" "http://localhost:6767/v1/ingest" "log_ingest_url"

    # Write .env file
    print_step "Writing engine/inference/.env file..."
    cat > "$env_file" << EOF
# Concordance Engine Configuration
# Generated by setup.sh on $(date)

# Hugging Face token for model downloads
HF_TOKEN=$hf_token

# Admin key for authenticated operations
ADMIN_KEY=$admin_key

# Model to load
MODEL_ID=$model_id

# Server configuration
HOST=$engine_host
PORT=$engine_port

# Backend integration for logging
QUOTE_LOG_INGEST_URL=$log_ingest_url

# User and mod storage paths
# Local: ./users/users.json and ./mods
# Remote (Modal): /users/users.json and /mods
USERS_PATH=$users_path
MODS_BASE=$mods_base

# Optional: Maximum batch size for inference
# MAX_BATCH_SIZE=10

# Optional: Custom weight path (for local models)
# WEIGHT_PATH=/path/to/weights
EOF

    print_success "Engine configuration saved to engine/inference/.env"

    # Install dependencies
    printf "\n"
    if confirm "Would you like to install engine dependencies now?"; then
        print_step "Installing engine dependencies with uv..."
        printf "${GRAY}"
        (cd "$SCRIPT_DIR/engine" && uv sync --all-packages && uv pip install -e inference)
        printf "${NC}"
        print_success "Engine dependencies installed!"
    fi
}

# ============================================================================
# Frontend Setup
# ============================================================================
setup_frontend() {
    print_header "Frontend Setup"

    local frontend_dir="$SCRIPT_DIR/frontend"
    local env_file="$frontend_dir/.env"

    print_info "The frontend connects to the backend for data and real-time updates."
    printf "\n"

    # API Configuration
    print_subheader "API Configuration"

    local api_url=""
    local ws_url=""

    prompt_with_default "Backend API URL" "http://localhost:6767" "api_url"
    prompt_with_default "Backend WebSocket URL" "ws://localhost:6767" "ws_url"

    # Write .env file
    print_step "Writing frontend/.env file..."
    cat > "$env_file" << EOF
# Concordance Frontend Configuration
# Generated by setup.sh on $(date)

# Backend API URL
VITE_API_URL=$api_url

# WebSocket URL for real-time log streaming
VITE_WS_URL=$ws_url
EOF

    print_success "Frontend configuration saved to frontend/.env"

    # Install dependencies
    printf "\n"
    if confirm "Would you like to install frontend dependencies now?"; then
        print_step "Installing frontend dependencies with npm..."
        printf "${GRAY}"
        (cd "$frontend_dir" && npm install)
        printf "${NC}"
        print_success "Frontend dependencies installed!"
    fi
}

# ============================================================================
# Full Setup
# ============================================================================
setup_all() {
    setup_backend
    setup_engine
    setup_frontend
}

# ============================================================================
# Post-Setup Instructions
# ============================================================================
print_next_steps() {
    print_header "Setup Complete! 🎉"

    printf "${WHITE}${BOLD}Next Steps:${NC}\n"
    printf "\n"

    printf "${CYAN}1. Start the Backend:${NC}\n"
    printf "   ${DIM}cd backend && cargo run${NC}\n"
    printf "   ${DIM}(Make sure migrations have been run: ./run_migration.sh)${NC}\n"
    printf "\n"

    printf "${CYAN}2. Start the Engine:${NC}\n"
    printf "   ${DIM}cd engine${NC}\n"
    printf "   ${DIM}uv run -m quote.server.openai.local --host 0.0.0.0 --port 8000${NC}\n"
    printf "   ${DIM}(First run will download and compile the model - this takes a few minutes)${NC}\n"
    printf "\n"

    printf "${CYAN}3. Start the Frontend:${NC}\n"
    printf "   ${DIM}cd frontend && npm run dev${NC}\n"
    printf "\n"

    printf "${CYAN}4. Open the UI:${NC}\n"
    printf "   ${DIM}http://localhost:3000${NC}\n"
    printf "\n"

    printf "${CYAN}5. Test the Engine:${NC}\n"
    printf "   ${DIM}curl http://localhost:8000/v1/models${NC}\n"
    printf "\n"

    printf "${WHITE}${BOLD}Useful Commands:${NC}\n"
    printf "\n"
    printf "  ${YELLOW}Health Checks:${NC}\n"
    printf "    ${DIM}curl http://localhost:6767/healthz  # Backend${NC}\n"
    printf "    ${DIM}curl http://localhost:8000/v1/models  # Engine${NC}\n"
    printf "\n"

    printf "  ${YELLOW}Chat Completion:${NC}\n"
    printf "    ${DIM}curl -X POST http://localhost:8000/v1/chat/completions \\\\${NC}\n"
    printf "    ${DIM}  -H 'Content-Type: application/json' \\\\${NC}\n"
    printf "    ${DIM}  -d '{\"model\": \"modularai/Llama-3.1-8B-Instruct-GGUF\",${NC}\n"
    printf "    ${DIM}       \"messages\": [{\"role\": \"user\", \"content\": \"Hello!\"}]}'${NC}\n"
    printf "\n"

    printf "${WHITE}${BOLD}Documentation:${NC}\n"
    printf "  • README: ${BLUE}https://github.com/concordance-co/quote${NC}\n"
    printf "  • Mod SDK: ${BLUE}engine/sdk/README.md${NC}\n"
    printf "  • Backend API: ${BLUE}backend/docs/API.md${NC}\n"
    printf "\n"

    printf "${WHITE}${BOLD}Build Your First Mod:${NC}\n"
    printf "  Visit ${CYAN}https://docs.concordance.co${NC} to learn how to build your first mod!\n"
    printf "\n"

    print_info "Run ${CYAN}./setup.sh${NC} again anytime to reconfigure."
}

# ============================================================================
# Component Selection Menu
# ============================================================================
show_menu() {
    printf "\n"
    printf "${WHITE}${BOLD}What would you like to set up?${NC}\n"
    printf "\n"
    printf "  ${CYAN}1)${NC} All components (recommended)\n"
    printf "  ${CYAN}2)${NC} Backend only\n"
    printf "  ${CYAN}3)${NC} Engine only\n"
    printf "  ${CYAN}4)${NC} Frontend only\n"
    printf "  ${CYAN}5)${NC} Check prerequisites only\n"
    printf "  ${CYAN}q)${NC} Quit\n"
    printf "\n"
    printf "${WHITE}Enter your choice [1-5, q]: ${NC}"
    read choice

    case "$choice" in
        1)
            check_prerequisites
            setup_all
            print_next_steps
            ;;
        2)
            check_prerequisites
            setup_backend
            print_next_steps
            ;;
        3)
            check_prerequisites
            setup_engine
            print_next_steps
            ;;
        4)
            check_prerequisites
            setup_frontend
            print_next_steps
            ;;
        5)
            check_prerequisites
            ;;
        q|Q)
            printf "${GREEN}Goodbye!${NC}\n"
            exit 0
            ;;
        *)
            print_error "Invalid choice. Please try again."
            show_menu
            ;;
    esac
}

# ============================================================================
# Quick Setup Mode (Non-Interactive)
# ============================================================================
quick_setup() {
    local component="$1"

    case "$component" in
        backend)
            check_prerequisites
            setup_backend
            ;;
        engine)
            check_prerequisites
            setup_engine
            ;;
        frontend)
            check_prerequisites
            setup_frontend
            ;;
        all)
            check_prerequisites
            setup_all
            print_next_steps
            ;;
        *)
            print_error "Unknown component: $component"
            printf "Usage: %s [--quick backend|engine|frontend|all]\n" "$0"
            exit 1
            ;;
    esac
}

# ============================================================================
# Main Entry Point
# ============================================================================
main() {
    print_banner

    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --quick|-q)
                if [ -n "$2" ]; then
                    quick_setup "$2"
                    exit 0
                else
                    print_error "--quick requires a component name (backend, engine, frontend, all)"
                    exit 1
                fi
                ;;
            --help|-h)
                printf "Concordance Setup Script\n"
                printf "\n"
                printf "Usage: %s [OPTIONS]\n" "$0"
                printf "\n"
                printf "Options:\n"
                printf "  --quick, -q <component>  Quick setup for specific component\n"
                printf "                           Components: backend, engine, frontend, all\n"
                printf "  --help, -h               Show this help message\n"
                printf "\n"
                printf "Examples:\n"
                printf "  %s                       Interactive setup\n" "$0"
                printf "  %s --quick all           Set up all components\n" "$0"
                printf "  %s --quick backend       Set up only the backend\n" "$0"
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                printf "Use --help for usage information.\n"
                exit 1
                ;;
        esac
        shift
    done

    # Interactive mode
    show_menu
}

# Run main function
main "$@"
