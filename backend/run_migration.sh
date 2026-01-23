#!/bin/bash

# Script to run database migration on Neon Postgres
# Usage:
#   ./run_migration.sh                         (run all migrations, reads DATABASE_URL from .env)
#   ./run_migration.sh 5                       (run only migration 5, reads DATABASE_URL from .env)
#   ./run_migration.sh "postgresql://..."      (run all migrations with provided connection string)
#   ./run_migration.sh 5 "postgresql://..."    (run only migration 5 with provided connection string)

set -e

# Color output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}Backend Schema Migration${NC}"
echo -e "${BLUE}================================${NC}"
echo

# Parse arguments
MIGRATION_NUMBER=""
DATABASE_URL=""

for arg in "$@"; do
    if [[ "$arg" =~ ^[0-9]+$ ]]; then
        # It's a number - migration number
        MIGRATION_NUMBER="$arg"
    elif [[ "$arg" =~ ^postgres ]]; then
        # It's a connection string
        DATABASE_URL="$arg"
    else
        echo -e "${RED}Error: Unknown argument: $arg${NC}"
        echo "Usage:"
        echo "  ./run_migration.sh                         (run all migrations)"
        echo "  ./run_migration.sh 5                       (run only migration 5)"
        echo "  ./run_migration.sh \"postgresql://...\"      (run all migrations with connection string)"
        echo "  ./run_migration.sh 5 \"postgresql://...\"    (run migration 5 with connection string)"
        exit 1
    fi
done

# Get DATABASE_URL from .env if not provided as argument
if [ -z "$DATABASE_URL" ]; then
    # Try to read from .env file
    if [ ! -f .env ]; then
        echo -e "${RED}Error: .env file not found${NC}"
        echo "Please either:"
        echo "  1. Create a .env file with DATABASE_URL, or"
        echo "  2. Run: ./run_migration.sh \"postgresql://user:pass@host/db?sslmode=require\""
        exit 1
    fi

    # Extract DATABASE_URL from .env (handles various formats)
    DATABASE_URL=$(grep -E "^DATABASE_URL=" .env | sed 's/^DATABASE_URL=//' | sed 's/^["'\'']//' | sed 's/["'\'']$//')

    if [ -z "$DATABASE_URL" ]; then
        echo -e "${RED}Error: DATABASE_URL not found in .env${NC}"
        echo "Make sure your .env file has a line like:"
        echo "  DATABASE_URL=postgresql://user:pass@host/db?sslmode=require"
        echo ""
        echo "Or run with the connection string directly:"
        echo "  ./run_migration.sh \"postgresql://user:pass@host/db?sslmode=require\""
        exit 1
    fi

    echo -e "${GREEN}✓ Found DATABASE_URL in .env${NC}"
else
    echo -e "${GREEN}✓ Using connection string from argument${NC}"
fi

echo

# Find and run migration files
MIGRATION_DIR="migrations"

if [ ! -d "$MIGRATION_DIR" ]; then
    echo -e "${RED}Error: Migrations directory not found: $MIGRATION_DIR${NC}"
    exit 1
fi

# Get all .sql files in migrations directory, sorted
MIGRATION_FILES=$(find "$MIGRATION_DIR" -name "*.sql" | sort)

if [ -z "$MIGRATION_FILES" ]; then
    echo -e "${RED}Error: No migration files found in $MIGRATION_DIR${NC}"
    exit 1
fi

# If a specific migration number was requested, filter to just that one
if [ -n "$MIGRATION_NUMBER" ]; then
    # Pad the number with leading zeros to match the file format (e.g., 5 -> 0005)
    PADDED_NUMBER=$(printf "%04d" "$MIGRATION_NUMBER")

    # Find the matching migration file
    MATCHING_FILE=""
    for f in $MIGRATION_FILES; do
        if [[ "$f" =~ /${PADDED_NUMBER}_ ]]; then
            MATCHING_FILE="$f"
            break
        fi
    done

    if [ -z "$MATCHING_FILE" ]; then
        echo -e "${RED}Error: Migration $MIGRATION_NUMBER not found (looking for ${PADDED_NUMBER}_*.sql)${NC}"
        echo ""
        echo "Available migrations:"
        for f in $MIGRATION_FILES; do
            echo "  $(basename $f)"
        done
        exit 1
    fi

    MIGRATION_FILES="$MATCHING_FILE"
    echo -e "${YELLOW}Running specific migration: $MIGRATION_NUMBER${NC}"
else
    echo -e "${YELLOW}Running all migrations...${NC}"
fi

echo

# Check for psql
if ! command -v psql &> /dev/null; then
    echo -e "${RED}Error: psql command not found${NC}"
    echo "Please install PostgreSQL client tools"
    exit 1
fi

for MIGRATION_FILE in $MIGRATION_FILES; do
    echo -e "${BLUE}Running migration: $MIGRATION_FILE${NC}"

    psql "$DATABASE_URL" -f "$MIGRATION_FILE"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Successfully applied $MIGRATION_FILE${NC}"
    else
        echo -e "${RED}Error applying $MIGRATION_FILE${NC}"
        exit 1
    fi
    echo
done

echo -e "${GREEN}✓ All migrations completed successfully!${NC}"

echo
echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}Verifying tables...${NC}"
echo -e "${BLUE}================================${NC}"
echo

# Verify the tables were created
psql "$DATABASE_URL" -c "\dt"

echo
echo -e "${GREEN}Migration complete!${NC}"
