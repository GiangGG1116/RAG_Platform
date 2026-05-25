#!/bin/bash
# Run Alembic migrations
set -e

echo "Running database migrations..."
cd /app
alembic -c migrations/alembic.ini upgrade head
echo "Migrations completed."
